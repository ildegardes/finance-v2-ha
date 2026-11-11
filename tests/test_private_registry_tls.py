from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection, HTTPSConnection
from ipaddress import ip_address
import json
from pathlib import Path
import ssl
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from wsgiref.simple_server import make_server

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from finance_v2.__main__ import SafeRequestHandler, make_private_server
from finance_v2.api import Application
from finance_v2.config import Settings
from finance_v2.http_runtime import ConcurrentWSGIServer
from finance_v2.migrations import migrate
from finance_v2.open_finance_registry_admin import RegistryAdmin
from finance_v2.pluggy_credential_protection import CredentialProtector


class PrivateRegistryTLSTests(unittest.TestCase):
    def test_real_tls_cookie_and_origin_protect_registry_from_http_and_proxy(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "fixture.sqlite3"
            migrate(database)
            certificate, key_file = root / "test-cert.pem", root / "test-key.pem"
            key = ec.generate_private_key(ec.SECP256R1())
            identity = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "Synthetic Finance lab")])
            now = datetime.now(timezone.utc)
            certificate.write_bytes(
                x509.CertificateBuilder().subject_name(identity).issuer_name(identity)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]), critical=False)
                .sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)
            )
            key_file.write_bytes(key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
            ))
            owner = "synthetic-owner"
            settings = Settings(database, "UTC", "127.0.0.1", 8766, 5000, ui_token=owner)
            with make_private_server("127.0.0.1", None, certificate, key_file, port=0) as private:
                origin = f"https://127.0.0.1:{private.server_port}"
                app = Application(replace(settings, pluggy_admin_origin=origin))
                private.set_app(app)
                with make_server("127.0.0.1", 0, app, server_class=ConcurrentWSGIServer,
                                 handler_class=SafeRequestHandler) as public:
                    self._exercise(private, public, origin, certificate, owner)

    def _exercise(self, private, public, origin, certificate, owner):
        servers = (private, public)
        threads = [Thread(target=server.serve_forever, kwargs={"poll_interval": .05}) for server in servers]
        for thread in threads:
            thread.start()
        trusted = ssl.create_default_context(cafile=str(certificate))
        tls = HTTPSConnection("127.0.0.1", private.server_port, context=trusted, timeout=3)
        http = HTTPConnection("127.0.0.1", public.server_port, timeout=3)
        try:
            tls.request("POST", "/app/session", f"token={owner}", {"Content-Type": "application/x-www-form-urlencoded"})
            response = tls.getresponse()
            self.assertEqual(response.status, 303)
            attributes = response.getheader("Set-Cookie")
            self.assertIn("; Secure", attributes)
            self.assertIn("; HttpOnly", attributes)
            self.assertIn("; SameSite=Strict", attributes)
            response.read()
            cookie = attributes.split(";", 1)[0]
            tls.request("GET", "/api/v2/context", headers={"Cookie": cookie})
            csrf = json.loads(tls.getresponse().read())["csrf_token"]
            url = "/api/v2/open-finance/registry/drafts"
            body = json.dumps({
                "label": "Synthetic", "environment": "STRICT", "client_id": "synthetic-client",
                "client_secret": "synthetic-secret", "item_id": "synthetic-item",
            })
            headers = {"Cookie": cookie, "Origin": origin, "X-CSRF-Token": csrf, "Content-Type": "application/json"}
            for connection, extra in ((http, {"Host": origin.removeprefix("https://")}),
                                      (tls, {"X-Forwarded-Proto": "https"}),
                                      (tls, {"Origin": "https://example.invalid"}),
                                      (tls, {"X-CSRF-Token": "invalid"})):
                connection.request("POST", url, body, {**headers, **extra})
                response = connection.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
            with patch.object(RegistryAdmin, "_keyring", return_value=CredentialProtector("test", {"test": bytes(32)})):
                tls.request("POST", url, body, headers)
                response = tls.getresponse()
                self.assertEqual(response.status, 201)
                sanitized = response.read()
                self.assertNotIn(b"synthetic-secret", sanitized)
                self.assertEqual(json.loads(sanitized)["lifecycle"], "DRAFT")
        finally:
            tls.close()
            http.close()
            for server, thread in zip(servers, threads):
                server.shutdown()
                thread.join(3)
                self.assertFalse(thread.is_alive())
