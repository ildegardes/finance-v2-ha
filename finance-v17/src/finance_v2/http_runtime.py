"""Bounded concurrent WSGI service; slow provider requests cannot monopolize HTTP."""
import signal
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


def serve(server, settings):
    """Main-thread TERM/INT handler; no shutdown() deadlock inside a signal handler."""
    stop = threading.Event()
    previous = {}
    workers = CoverageWorkers(settings)
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.signal(signum, lambda *_: stop.set())
    server.timeout = .25
    try:
        workers.start()
        while not stop.is_set():
            server.handle_request()
    finally:
        stopped = workers.stop()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if not stopped:
            # Never claim graceful shutdown when an in-flight worker is left.
            raise RuntimeError('OPEN_FINANCE_WORKER_STOP_PENDING')
