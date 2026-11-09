"""Fair admission to short staging writes; never covers provider I/O or reads.

SQLite still provides cross-process locking, transactions and durability. Admission
shares its existing busy-time budget and prevents in-process writers repeatedly
reacquiring SQLite ahead of an already waiting peer.
"""
from collections import deque
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
import time
from weakref import WeakValueDictionary

from .db import immediate_transaction


class _WriterQueue:
    def __init__(self):
        self.condition = threading.Condition()
        self.waiters = deque()
        self.active = False

    @contextmanager
    def turn(self, timeout_ms, check):
        deadline = time.monotonic() + timeout_ms / 1000
        ticket = object()
        with self.condition:
            self.waiters.append(ticket)
            try:
                while self.active or self.waiters[0] is not ticket:
                    check()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise sqlite3.OperationalError('database is locked')
                    self.condition.wait(min(.05, remaining))
                check()
                self.waiters.popleft()
                self.active = True
            except BaseException:
                self.waiters.remove(ticket)
                self.condition.notify_all()
                raise
        try:
            yield deadline
        finally:
            with self.condition:
                self.active = False
                self.condition.notify_all()


_queues = WeakValueDictionary()
_registry_lock = threading.Lock()


def _queue_for(path):
    key = Path(path).resolve()
    with _registry_lock:
        queue = _queues.get(key)
        if queue is None:
            queue = _WriterQueue()
            _queues[key] = queue
        return queue


@contextmanager
def staging_transaction(connection, path, *, timeout_ms, check=lambda: None):
    queue = _queue_for(path)
    with queue.turn(timeout_ms, check) as deadline:
        previous = connection.execute('PRAGMA busy_timeout').fetchone()[0]
        remaining = max(0, min(previous, int((deadline - time.monotonic()) * 1000)))
        connection.execute(f'PRAGMA busy_timeout={remaining:d}')
        try:
            with immediate_transaction(connection):
                yield
        finally:
            connection.execute(f'PRAGMA busy_timeout={previous:d}')
