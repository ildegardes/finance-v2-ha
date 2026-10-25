"""Opt-in cached coverage workers. No Item refresh, consent renewal or official writes."""
import logging
import threading
import time

from .open_finance import OpenFinanceService, SyncError
from .open_finance_coverage import sync_full_automatic
from .pluggy_client import PluggyClient, PluggyError, transport

LOGGER = logging.getLogger(__name__)


class CoverageWorkers:
    INTERVAL_SECONDS = 3600
    RUN_BUDGET_SECONDS = 120
    SOCKET_TIMEOUT_SECONDS = 2

    def __init__(self, settings, *, send=transport, now=time.monotonic):
        self.settings = settings
        self.send, self.now = send, now
        self.stop_event = threading.Event()
        self.threads = []
        self._io_lock = threading.Lock()
        self._inflight = {}

    def start(self):
        if self.threads or self.stop_event.is_set():
            raise RuntimeError('COVERAGE_WORKERS_ALREADY_STARTED_OR_STOPPED')
        for config in self.settings.pluggy_connections:
            if config.enabled and config.auto_sync_enabled:
                worker = threading.Thread(target=self._loop, args=(config,),
                    name='coverage-' + config.id, daemon=True)
                self.threads.append(worker)
                worker.start()

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

        service = OpenFinanceService(self.settings, client_factory=lambda connection:
            PluggyClient(connection, send=bounded_send, max_attempts=1,
                timeout=self.SOCKET_TIMEOUT_SECONDS))
        return sync_full_automatic(service, config.id, check=check,
            minimum_interval=self.INTERVAL_SECONDS if respect_schedule else 0)

    def _loop(self, config):
        while not self.stop_event.is_set():
            delay=self.INTERVAL_SECONDS
            try:
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
            if self.stop_event.wait(delay):
                break

    def stop(self):
        self.stop_event.set()
        deadline = self.now() + 1
        for worker in self.threads:
            worker.join(max(0, deadline - self.now()))
        remaining = sum(worker.is_alive() for worker in self.threads)
        with self._io_lock:
            pending_io = len(self._inflight)
        if pending_io:
            # This is not an assertion of cancellation delivery to the provider.
            # Results have no path back to persistence after check() rejects them.
            LOGGER.warning('coverage IO_DETACHED count=%d', pending_io)
        if remaining:
            LOGGER.warning('coverage STOP_PENDING count=%d', remaining)
        return remaining == 0
