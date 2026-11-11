from __future__ import annotations

import argparse
from contextlib import ExitStack
import logging
from pathlib import Path
import ssl
from wsgiref.simple_server import make_server, WSGIRequestHandler

from .api import create_app
from .config import Settings
from .migrations import migrate, require_current_schema
from .domain.clock import SystemClock
from .scheduler import SchedulerService
from .http_runtime import ConcurrentWSGIServer, PrivateTLSWSGIServer, serve


class SafeRequestHandler(WSGIRequestHandler):
    """Keep OAuth state/codes and credential-like query inputs out of access logs."""

    def log_request(self, code="-", size="-"):
        self.log_message('"%s %s" %s %s', self.command, self.path.split("?", 1)[0], code, size)


class PrivateRequestHandler(SafeRequestHandler):
    def get_environ(self):
        environ = super().get_environ()
        environ["HTTPS"] = "on"
        environ["finance_v2.private_tls"] = True
        return environ


def make_private_server(host, application, certificate, key, *, port=8767):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, key, password=lambda: "")
    server = make_server(
        host, port, application, server_class=PrivateTLSWSGIServer, handler_class=PrivateRequestHandler,
    )
    server.tls_context = context
    return server


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
    from .pluggy_keyring import provision
    from .pluggy_credential_protection import CredentialProtectionError
    try:
        provision(settings)
    except CredentialProtectionError as exc:
        logging.getLogger(__name__).warning("%s", exc)
    with ExitStack() as resources:
        app = create_app(settings)
        server = resources.enter_context(make_server(
            settings.host, settings.port, app, server_class=ConcurrentWSGIServer, handler_class=SafeRequestHandler,
        ))
        private_server = None
        if settings.pluggy_admin_origin and settings.pluggy_admin_origin.startswith("https://"):
            try:
                private_server = resources.enter_context(make_private_server(
                    settings.host, app, Path("/ssl/finance-v17-admin.pem"), Path("/ssl/finance-v17-admin-key.pem"),
                ))
            except (OSError, ValueError):
                logging.getLogger(__name__).warning("PLUGGY_PRIVATE_TLS_UNAVAILABLE")
        print(f"Finance V2 listening on http://{settings.host}:{settings.port}/api/v2/health")
        serve(server, settings, private_server)


if __name__ == "__main__":
    main()
