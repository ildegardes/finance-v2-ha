"""Bounded concurrent WSGI service; slow provider requests cannot monopolize HTTP."""
import signal
import selectors
import ssl
import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer

from .open_finance_auto import CoverageWorkers


class ConcurrentWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, *args, **kwargs):
        self._slots = threading.BoundedSemaphore(16)
        super().__init__(*args, **kwargs)

    def set_app(self, application):
        def threaded_application(environ, start_response):
            # The stdlib simple_server handler otherwise advertises False.
            environ['wsgi.multithread'] = True
            return application(environ, start_response)
        super().set_app(threaded_application)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                request.settimeout(.1)
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            except OSError:
                pass  # A disconnected peer has no application response to receive.
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class PrivateTLSWSGIServer(ConcurrentWSGIServer):
    """Perform the TLS handshake inside a bounded worker slot."""
    def finish_request(self, request, client_address):
        request.settimeout(5)
        try:
            with self.tls_context.wrap_socket(request, server_side=True) as encrypted:
                encrypted.settimeout(15)
                try:
                    super().finish_request(encrypted, client_address)
                finally:
                    encrypted.settimeout(.25)
                    try:
                        # Send close_notify after the response, including when an
                        # authorization rejection deliberately leaves the body unread.
                        encrypted.unwrap().close()
                    except OSError:
                        pass
        except (ssl.SSLError, TimeoutError, ConnectionError):
            return


def serve(server, settings, private_server=None):
    """Main-thread TERM/INT handler; no shutdown() deadlock inside a signal handler."""
    stop = threading.Event()
    previous = {}
    workers = CoverageWorkers(settings)
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.signal(signum, lambda *_: stop.set())
    try:
        workers.start()
        with selectors.DefaultSelector() as listeners:
            for listener in (server, private_server):
                if listener is not None:
                    listeners.register(listener, selectors.EVENT_READ)
                    listener.timeout = .25
            while not stop.is_set():
                for ready, _ in listeners.select(timeout=.25):
                    if not stop.is_set():
                        ready.fileobj.handle_request()
    finally:
        stopped = workers.stop()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if not stopped:
            # Never claim graceful shutdown when an in-flight worker is left.
            raise RuntimeError('OPEN_FINANCE_WORKER_STOP_PENDING')
