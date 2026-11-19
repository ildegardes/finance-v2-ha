"""Opt-in cached coverage workers. No Item refresh, consent renewal or official writes."""
from contextlib import closing
import logging
import threading
import time

from .open_finance import OpenFinanceService, SyncError
from .open_finance_coverage import sync_full_automatic
from .open_finance_registry import connection_views
from .open_finance_schedule import allowed, preferences, claim_delay, _datetime, legacy_binding_mismatches
from .pluggy_client import PluggyClient, PluggyError, transport

LOGGER = logging.getLogger(__name__)


class CoverageWorkers:
    INTERVAL_SECONDS = 86400
    CONFIG_CHECK_SECONDS = 15
    RUN_BUDGET_SECONDS = 120
    SOCKET_TIMEOUT_SECONDS = 2

    def __init__(self, settings, *, send=transport, now=time.monotonic, clock=None):
        self.settings = settings
        self.send, self.now, self.clock = send, now, clock
        self.stop_event = threading.Event()
        self.threads = []
        self._monitor=None
        self._planned=set()
        self._io_lock = threading.Lock()
        self._inflight = {}

    def start(self):
        if self._monitor or self.threads or self.stop_event.is_set():
            raise RuntimeError('COVERAGE_WORKERS_ALREADY_STARTED_OR_STOPPED')
        self._start_eligible()
        if self.settings.open_finance_auto_sync_allowed is not False:
            self._monitor=threading.Thread(target=self._monitor_registry,name='coverage-registry',daemon=True)
            self._monitor.start()

    def _start_eligible(self):
        service=OpenFinanceService(self.settings,self.clock)
        with closing(service._db()) as db:
            mismatched=legacy_binding_mismatches(db,self.settings)
            planned=[view for view in connection_views(db,self.settings).values()
                     if allowed(self.settings,view) and view.id not in mismatched]
        for view in planned:
            if self.stop_event.is_set():
                break
            if view.id in self._planned:
                continue
            self._planned.add(view.id)
            worker=threading.Thread(target=self._loop,args=(view,),name='coverage-'+view.id,daemon=True)
            self.threads.append(worker)
            worker.start()

    def _monitor_registry(self):
        while not self.stop_event.wait(self.CONFIG_CHECK_SECONDS):
            try:
                self._start_eligible()
            except Exception:
                LOGGER.warning('coverage registry refresh deferred')

    def _run_one(self, config, *, respect_schedule=False):
        deadline = self.now() + self.RUN_BUDGET_SECONDS

        def check():
            if self.stop_event.is_set():
                raise PluggyError('AUTO_SYNC_CANCELLED')
            if self.now() >= deadline:
                raise PluggyError('AUTO_SYNC_DEADLINE')

        def bounded_send(method, path, headers, body, timeout):
            check()
            # Only this pure transport call may outlive cancellation. It has no
            # database, lease token, persistence callback or result consumer.
            # At most one unresolved call per institution may exist.
            done = threading.Event()
            outcome = {}
            with self._io_lock:
                check()
                if config.id in self._inflight:
                    raise PluggyError('AUTO_SYNC_IO_BUSY')
                self._inflight[config.id] = done

            def invoke():
                try:
                    outcome['result'] = self.send(method, path, headers, body,
                        min(timeout, self.SOCKET_TIMEOUT_SECONDS, max(.001, deadline - self.now())))
                except Exception as error:
                    outcome['error'] = error
                finally:
                    with self._io_lock:
                        if self._inflight.get(config.id) is done:
                            del self._inflight[config.id]
                    done.set()

            io_thread = threading.Thread(target=invoke, name='coverage-io-' + config.id, daemon=True)
            try:
                io_thread.start()
            except BaseException:
                with self._io_lock:
                    if self._inflight.get(config.id) is done:
                        del self._inflight[config.id]
                raise
            while not done.wait(.05):
                check()
            check()
            if 'error' in outcome:
                raise outcome['error']
            if 'result' not in outcome:
                raise PluggyError('TRANSPORT_FAILURE')
            return outcome['result']

        service = OpenFinanceService(self.settings, self.clock, client_factory=lambda connection:
            PluggyClient(connection, send=bounded_send, max_attempts=1,
                timeout=self.SOCKET_TIMEOUT_SECONDS))
        return sync_full_automatic(service, config.id, check=check,
            minimum_interval=None if respect_schedule else 0)

    def _loop(self, config):
        while not self.stop_event.is_set():
            delay=self.INTERVAL_SECONDS
            try:
                service=OpenFinanceService(self.settings,self.clock)
                with closing(service._db()) as db:
                    enabled,hours,_=preferences(db,self.settings)
                    current=connection_views(db,self.settings).get(config.id)
                    effective=(enabled and current is not None and allowed(self.settings,current)
                               and config.id not in legacy_binding_mismatches(db,self.settings))
                    _,remaining=claim_delay(db,config.id,hours,_datetime(service._time()[1])) if effective else (None,0)
                if not effective or remaining:
                    if self.stop_event.wait(min(self.CONFIG_CHECK_SECONDS,remaining or self.CONFIG_CHECK_SECONDS)):
                        break
                    continue
                result = self._run_one(config, respect_schedule=True)
                # Only a local slug and fixed outcome; never log provider bodies.
                LOGGER.info('coverage %s %s', config.id, result['state'])
            except Exception as error:
                # Includes binding/lease/storage failures before run creation.
                # The next attempt is delayed; peers and API keep running.
                if isinstance(error,SyncError) and error.code in ('AUTO_SYNC_RECENT','AUTO_SYNC_BACKOFF'):
                    delay=min(self.INTERVAL_SECONDS,max(1,error.retry_after))
                    LOGGER.info('coverage %s %s',config.id,error.code)
                else:
                    code = ('CANCELLATION_FINALIZATION_DEFERRED' if isinstance(error, SyncError)
                        and error.code == 'CANCELLATION_FINALIZATION_DEFERRED' else 'ATTEMPT_FAILED')
                    LOGGER.warning('coverage %s %s', config.id, code)
            if self.stop_event.wait(min(delay,self.CONFIG_CHECK_SECONDS)):
                break

    def stop(self):
        self.stop_event.set()
        deadline = self.now() + 1
        if self._monitor:
            self._monitor.join(max(0,deadline-self.now()))
        for worker in self.threads:
            worker.join(max(0, deadline - self.now()))
        remaining = sum(worker.is_alive() for worker in self.threads)+int(bool(self._monitor and self._monitor.is_alive()))
        with self._io_lock:
            pending_io = len(self._inflight)
        if pending_io:
            # This is not an assertion of cancellation delivery to the provider.
            # Results have no path back to persistence after check() rejects them.
            LOGGER.warning('coverage IO_DETACHED count=%d', pending_io)
        if remaining:
            LOGGER.warning('coverage STOP_PENDING count=%d', remaining)
        return remaining == 0
