from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import logging
import sqlite3
import threading
import time
from typing import Callable

from ..db import connect
from ..domain.auto_debit import execute_expense_auto_debit, execute_invoice_auto_debit
from ..domain.automation import create_settlement, record_execution
from ..domain.clock import Clock
from ..domain.recurrence import materialize
from ..domain.revenue_recurrence import materialize_revenue_series


LOGGER = logging.getLogger("finance_v2.scheduler")


class TransientSchedulerError(RuntimeError):
    """A retryable failure raised by an adapter or an injected test seam."""


@dataclass
class TickSummary:
    kind: str
    series: int = 0
    candidates: int = 0
    success: int = 0
    retryable: int = 0
    attention: int = 0
    skipped: int = 0
    failures: int = 0

    def result(self, value: str) -> None:
        field = {"SUCCESS": "success", "RETRYABLE_FAILURE": "retryable", "REQUIRES_ATTENTION": "attention", "SKIPPED": "skipped"}[value]
        setattr(self, field, getattr(self, field) + 1)


class SchedulerService:
    """Local V16 scheduler; discovery is read-only and financial rules stay in domain services."""

    def __init__(self, *, database_path, clock: Clock, busy_timeout_ms: int = 5000,
                 batch_size: int = 100, expense_executor: Callable = execute_expense_auto_debit,
                 invoice_executor: Callable = execute_invoice_auto_debit):
        self.database_path = database_path
        self.clock = clock
        self.busy_timeout_ms = busy_timeout_ms
        self.batch_size = batch_size
        self.expense_executor = expense_executor
        self.invoice_executor = invoice_executor

    def _connect(self):
        return connect(self.database_path, self.busy_timeout_ms)

    def _year_end(self) -> date:
        return date(self.clock.today().year, 12, 31)

    def run_startup(self) -> TickSummary:
        return self.run_tick(kind="startup")

    def _materialize_expenses(self, summary: TickSummary) -> None:
        connection = self._connect()
        try:
            series_ids = [row[0] for row in connection.execute("SELECT id FROM recurring_series ORDER BY id")]
        finally:
            connection.close()
        for series_id in series_ids:
            connection = self._connect()
            try:
                materialize(connection, series_id=series_id, through=self._year_end(), actor="SCHEDULER:internal", correlation_id=f"scheduler:{summary.kind}:{self.clock.today().isoformat()}:series:{series_id}", clock=self.clock)
                summary.series += 1
            except Exception:
                summary.failures += 1
                LOGGER.exception("scheduler expense catch-up failed series_id=%s", series_id)
            finally:
                connection.close()

    def _candidates(self):
        today = self.clock.today().isoformat()
        connection = self._connect()
        try:
            expenses = [("EXPENSE", row["id"], row["account_id"], row["due_date"])
                for row in connection.execute("SELECT e.id,e.account_id,e.due_date FROM expenses e WHERE e.lifecycle_state='ACTIVE' AND e.planned_payment_method='AUTO_DEBIT' AND e.due_date<=? AND NOT EXISTS(SELECT 1 FROM expense_payments p WHERE p.expense_id=e.id AND p.reversed_at IS NULL) ORDER BY e.id LIMIT ?", (today, self.batch_size))]
            invoices = [("INVOICE", row["id"], row["payment_account_id"], row["due_date"])
                for row in connection.execute("SELECT id,payment_account_id,due_date FROM invoices WHERE state IN('OPEN','CLOSED') AND payment_mode='AUTO_DEBIT' AND due_date<=? ORDER BY id LIMIT ?", (today, self.batch_size))]
            return expenses + invoices
        finally:
            connection.close()

    @staticmethod
    def _settlement_key(kind: str, obligation_id: int, due_date: str | None) -> str:
        return f"expense:{obligation_id}:auto-settlement" if kind == "EXPENSE" else f"invoice:{obligation_id}:due:{due_date}:auto-settlement"

    def _attempt(self, kind: str, obligation_id: int, account_id: int | None, due_date: str | None):
        key = self._settlement_key(kind, obligation_id, due_date)
        group = f"scheduled:{kind.lower()}:{obligation_id}:account:{account_id or 'none'}:due:{due_date or 'none'}"
        connection = self._connect()
        try:
            settlement = connection.execute("SELECT id FROM settlements WHERE settlement_key=?", (key,)).fetchone()
            if not settlement:
                try:
                    settlement_id = create_settlement(connection, settlement_key=key, obligation_type=kind, obligation_id=obligation_id, actor="SCHEDULER:internal", clock=self.clock)
                except sqlite3.IntegrityError:
                    settlement_id = connection.execute("SELECT id FROM settlements WHERE settlement_key=?", (key,)).fetchone()[0]
            else:
                settlement_id = settlement[0]
            terminal = connection.execute("SELECT 1 FROM automation_executions WHERE settlement_id=? AND result='REQUIRES_ATTENTION' LIMIT 1", (settlement_id,)).fetchone()
            if terminal:
                return settlement_id, f"terminal-check:{settlement_id}", 1
            last = connection.execute("SELECT attempt_number,result FROM automation_executions WHERE settlement_id=? AND attempt_group_key=? ORDER BY id DESC LIMIT 1", (settlement_id, group)).fetchone()
            number = last[0] + 1 if last and last[1] == "RETRYABLE_FAILURE" else 1
            return settlement_id, group, min(number, 3)
        finally:
            connection.close()

    @staticmethod
    def _transient(exc: BaseException) -> bool:
        return isinstance(exc, TransientSchedulerError) or (isinstance(exc, sqlite3.OperationalError) and any(word in str(exc).casefold() for word in ("locked", "busy", "tempor")))

    def _execute(self, candidate) -> str:
        kind, obligation_id, account_id, due_date = candidate
        settlement_id, group, number = self._attempt(kind, obligation_id, account_id, due_date)
        connection = self._connect()
        try:
            executor = self.expense_executor if kind == "EXPENSE" else self.invoice_executor
            return executor(connection, **({"expense_id": obligation_id} if kind == "EXPENSE" else {"invoice_id": obligation_id}), attempt_group_key=group, attempt_number=number, clock=self.clock)
        except Exception as exc:
            if not self._transient(exc):
                raise
            connection.close()
            recording = self._connect()
            try:
                record_execution(recording, settlement_id=settlement_id, attempt_group_key=group, attempt_number=number, result="RETRYABLE_FAILURE", error_code="TRANSIENT_FAILURE", clock=self.clock)
                return "REQUIRES_ATTENTION" if number == 3 else "RETRYABLE_FAILURE"
            finally:
                recording.close()
        finally:
            if connection:
                connection.close()

    def run_tick(self, *, kind: str = "hourly") -> TickSummary:
        summary = TickSummary(kind)
        self._materialize_expenses(summary)
        connection = self._connect()
        try:
            revenue_series_ids = [row[0] for row in connection.execute(
                "SELECT id FROM revenue_recurring_series WHERE active=1 ORDER BY id"
            )]
        finally:
            connection.close()
        for series_id in revenue_series_ids:
            connection = self._connect()
            try:
                materialize_revenue_series(
                    connection, series_id=series_id, through=self._year_end(),
                    actor="SCHEDULER:internal",
                    correlation_id=f"scheduler:{kind}:{self.clock.today().isoformat()}:revenue-series:{series_id}",
                    clock=self.clock,
                )
                summary.series += 1
            except Exception:
                summary.failures += 1
                LOGGER.exception("scheduler revenue catch-up failed series_id=%s", series_id)
            finally:
                connection.close()
        candidates = self._candidates()
        summary.candidates = len(candidates)
        for candidate in candidates:
            try:
                summary.result(self._execute(candidate))
            except Exception:
                summary.failures += 1
                LOGGER.exception("scheduler candidate failed obligation_type=%s obligation_id=%s", candidate[0], candidate[1])
        self._log(summary)
        return summary

    def _log(self, summary: TickSummary) -> None:
        LOGGER.info("scheduler_tick %s", asdict(summary))

    def serve_forever(self, *, interval_seconds: float = 3600.0, stop_event=None) -> None:
        stop_event = stop_event or threading.Event()
        self.run_startup()
        while not stop_event.wait(interval_seconds):
            started = time.monotonic()
            self.run_tick()
            LOGGER.info("scheduler_tick_duration_seconds=%.3f", time.monotonic() - started)
