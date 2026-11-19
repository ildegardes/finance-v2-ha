"""Maintain public PTAX coverage for the eligible financial references on disk."""
from contextlib import closing
from datetime import date, timedelta
import json
import logging
import threading

from .open_finance import OpenFinanceService, SyncError
from .open_finance_registry import connection_views
from .portfolio_fx import FX, fetch, refresh
from .snaptrade_normalize import day


LOGGER=logging.getLogger(__name__)
POLL_SECONDS=300
RETRY_SECONDS=1800
WINDOW_DAYS=35
MAX_REQUESTS=2


def _references(db,settings):
    dates=set()
    pluggy=json.dumps([cid for cid,view in connection_views(db,settings).items() if view.enabled and not view.historical])
    for row in db.execute("""SELECT DISTINCT CASE resource
                        WHEN 'accounts' THEN coalesce(json_extract(payload_json,'$.date'),json_extract(payload_json,'$.updatedAt'))
                        ELSE json_extract(payload_json,'$.date') END AS reference
        FROM of_resource_records WHERE state='PRESENT'
        AND resource IN ('accounts','investments','transactions')
        AND connection_id IN (SELECT value FROM json_each(?))
        AND json_extract(payload_json,'$.currencyCode') IN ('BRL','USD')
        AND CASE WHEN resource='transactions' THEN json_extract(payload_json,'$.amount') IS NOT NULL
            ELSE json_extract(payload_json,'$.balance') IS NOT NULL END""",(pluggy,)):
        dates.add(day(row['reference']))
    for row in db.execute("""SELECT DISTINCT reference_date FROM of_portfolio_snapshots
        WHERE connection_id IN (SELECT value FROM json_each(?)) AND currency IN ('BRL','USD')""",(pluggy,)):
        dates.add(day(row['reference_date']))
    if settings.snaptrade_enabled:
        for table,field,restriction in (('st_positions','reference_at','f.cash_equivalent=0 AND f.market_value IS NOT NULL'),
                                         ('st_balances','reference_at','f.cash IS NOT NULL'),
                                         ('st_activities','date','f.amount IS NOT NULL'),
                                         ('st_snapshots','reference_date','f.market_value IS NOT NULL')):
            # The table, date column and clause are all fixed above.
            for row in db.execute(f"""SELECT DISTINCT f.{field} AS reference
                FROM {table} f JOIN st_accounts a ON a.id=f.account_id
                JOIN st_connections c ON c.id=a.connection_id WHERE c.archived=0 AND c.excluded=0
                AND c.provider_state='AVAILABLE' AND a.state='AVAILABLE' AND f.currency IN ('BRL','USD')
                AND {restriction}"""):
                dates.add(day(row['reference']))
    dates.discard(None)
    return dates


class PortfolioFXWorker:
    def __init__(self,settings,*,clock=None,transport=fetch):
        self.service=OpenFinanceService(settings,clock)
        self.transport=transport
        self.stop_event=threading.Event()
        self.thread=None
        self.retry_at={}
        self.rate_limit_until=0

    def tick(self):
        today=self.service.clock.today()
        now=self.service._time()[0]
        if now<self.rate_limit_until or self.stop_event.is_set():
            return
        with closing(self.service._db()) as db:
            fx=FX(db)
            references=_references(db,self.service.settings)
        self.retry_at={key:until for key,until in self.retry_at.items() if until>now and key in references}
        pending=sorted((ref for ref in references if ref<=today.isoformat()
                       and ref not in fx.rates and ref not in self.retry_at),reverse=True)
        for _ in range(MAX_REQUESTS):
            if not pending or self.stop_event.is_set():
                break
            end=date.fromisoformat(pending[0])
            covered=[ref for ref in pending if (end-date.fromisoformat(ref)).days<WINDOW_DAYS-7]
            start=max(date.min+timedelta(days=7),date.fromisoformat(covered[-1]))-timedelta(days=7)
            try:
                refresh(self.service,start,end,transport=self._fetch)
            except SyncError:
                self.rate_limit_until=now+RETRY_SECONDS
                if not self.stop_event.is_set():
                    LOGGER.warning('portfolio FX refresh deferred')
                break
            for ref in covered:
                self.retry_at[ref]=now+(3600 if ref==today.isoformat() else 86400)
            pending=pending[len(covered):]

    def _fetch(self,start,end):
        result=self.transport(start,end)
        if self.stop_event.is_set():
            raise SyncError('PTAX_UNAVAILABLE',502)
        return result

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                LOGGER.warning('portfolio FX cache inspection deferred')
            self.stop_event.wait(POLL_SECONDS)

    def start(self):
        self.thread=threading.Thread(target=self._loop,name='portfolio-ptax',daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)
