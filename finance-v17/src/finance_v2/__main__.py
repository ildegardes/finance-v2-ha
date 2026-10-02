from __future__ import annotations

import argparse
import logging
from wsgiref.simple_server import make_server, WSGIRequestHandler

from .api import create_app
from .config import Settings
from .migrations import migrate, require_current_schema
from .domain.clock import SystemClock
from .scheduler import SchedulerService


class SafeRequestHandler(WSGIRequestHandler):
    """Keep OAuth state/codes and credential-like query inputs out of access logs."""

    def log_request(self, code="-", size="-"):
        self.log_message('"%s %s" %s %s', self.command, self.path.split("?", 1)[0], code, size)


def main() -> None:
    parser = argparse.ArgumentParser(description="Finance V2 foundation")
    parser.add_argument("command", choices=("migrate", "serve", "bootstrap", "scheduler"))
    args = parser.parse_args()
    settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.command == "scheduler":
        require_current_schema(settings.database_path)
        service = SchedulerService(database_path=settings.database_path, clock=SystemClock(settings.timezone), busy_timeout_ms=settings.busy_timeout_ms)
        print(f"Finance V2 scheduler database={settings.database_path} timezone={settings.timezone} interval={settings.scheduler_interval_seconds}s")
        try:
            service.serve_forever(interval_seconds=settings.scheduler_interval_seconds)
        except KeyboardInterrupt:
            print("Finance V2 scheduler stopped")
        return
    if args.command in {"migrate", "bootstrap"}:
        applied = migrate(settings.database_path, settings.busy_timeout_ms)
        print(f"database={settings.database_path} applied={applied}")
        if args.command == "migrate":
            return
    require_current_schema(settings.database_path)
    with make_server(settings.host, settings.port, create_app(settings), handler_class=SafeRequestHandler) as server:
        print(f"Finance V2 listening on http://{settings.host}:{settings.port}/api/v2/health")
        server.serve_forever()


if __name__ == "__main__":
    main()
