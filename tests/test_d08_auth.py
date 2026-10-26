"""Deterministic synthetic authentication regressions; never use real transport."""
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'finance-v17/src'))
from finance_v2.pluggy_client import PluggyClient, PluggyError
from finance_v2.pluggy_config import PluggyConnection


def deny_network(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo', 'sqlite3.connect'):
        raise AssertionError('D08_EXTERNAL_STATE_FORBIDDEN')
sys.addaudithook(deny_network)


def config(bank='itau'):
    return PluggyConnection(bank, bank, 'synthetic-client-'+bank,
                            'synthetic-secret-'+bank, 'synthetic-item-'+bank, True)


class AuthTests(unittest.TestCase):
    def test_late_coverage_401_does_not_discard_new_key(self):
        clock = [0]
        waiting, release = threading.Event(), threading.Event()
        auth, results, failures = [], [], []
        def send(method, path, headers, body, timeout):
            if method == 'POST':
                auth.append(json.loads(body))
                return 200, {'apiKey': 'synthetic-key-'+str(len(auth))}
            if threading.current_thread().name == 'd08-old-request' and headers['X-API-KEY'] == 'synthetic-key-1':
                waiting.set()
                if not release.wait(3): raise AssertionError('TEST_BARRIER_TIMEOUT')
                return 401, None
            return 200, {'results': []}
        client = PluggyClient(config(), send=send, now=lambda: clock[0], max_attempts=1)
        def old_request():
            try: results.append(client.coverage_get('/accounts?itemId=synthetic-item-itau'))
            except BaseException as error: failures.append(type(error).__name__)
        thread = threading.Thread(target=old_request, name='d08-old-request')
        thread.start()
        try:
            self.assertTrue(waiting.wait(3))
            clock[0] = 6900
            self.assertEqual(client.coverage_get('/accounts?itemId=synthetic-item-itau')[1], 'AVAILABLE')
        finally:
            release.set(); thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 1)
        self.assertEqual(len(auth), 2, 'A stale 401 must not trigger a third authentication')
        self.assertEqual(client._key, 'synthetic-key-2')

    def test_cache_expiry_boundary_and_request_body(self):
        clock, calls = [0], []
        def send(method, path, headers, body, timeout):
            calls.append((method, path, json.loads(body)))
            return 200, {'apiKey': 'synthetic-key-'+str(len(calls))}
        client = PluggyClient(config(), send=send, now=lambda: clock[0])
        self.assertEqual(client._api_key(), 'synthetic-key-1')
        clock[0] = 6899
        self.assertEqual(client._api_key(), 'synthetic-key-1')
        clock[0] = 6900
        self.assertEqual(client._api_key(), 'synthetic-key-2')
        self.assertEqual(calls, [('POST','/auth',{'clientId':'synthetic-client-itau','clientSecret':'synthetic-secret-itau'})]*2)

    def test_auth_401_never_retries_or_exposes_provider_body(self):
        calls = []
        def send(*args):
            calls.append(1)
            return 401, {'message': 'D08_PRIVATE_CANARY', 'clientSecret': 'D08_PRIVATE_CANARY'}
        client = PluggyClient(config(), send=send)
        with self.assertRaises(PluggyError) as failure: client._api_key()
        self.assertEqual(failure.exception.code, 'AUTH_FAILED')
        self.assertNotIn('D08_PRIVATE_CANARY', repr(vars(failure.exception)))
        self.assertEqual(len(calls), 1)
        self.assertIsNone(client._key)

    def test_one_renewal_then_stop_on_repeated_401(self):
        calls = []
        def send(method, *args):
            calls.append(method)
            return (200, {'apiKey':'synthetic-token'}) if method == 'POST' else (401, None)
        client = PluggyClient(config(), send=send)
        with self.assertRaises(PluggyError) as failure: client.coverage_get('/accounts?itemId=synthetic-item-itau')
        self.assertEqual(failure.exception.code, 'AUTH_FAILED')
        self.assertEqual(calls, ['POST','GET','POST','GET'])
        self.assertIsNone(client._key)

    def test_optional_403_does_not_authenticate_again(self):
        calls = []
        def send(method, *args):
            calls.append(method)
            return (200, {'apiKey':'synthetic-token'}) if method == 'POST' else (403, None)
        client = PluggyClient(config(), send=send)
        self.assertEqual(client.coverage_get('/consents?itemId=synthetic-item-itau', optional=True), ({}, 'NOT_AUTHORIZED'))
        self.assertEqual(calls, ['POST','GET'])

    def test_concurrent_cache_acquisition_is_single_flight(self):
        calls, keys = [], []
        gate = threading.Barrier(5)
        def send(*args): calls.append(1); return 200, {'apiKey':'synthetic-shared-token'}
        client = PluggyClient(config(), send=send)
        def worker(): gate.wait(timeout=3); keys.append(client._api_key())
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads: thread.start()
        gate.wait(timeout=3)
        for thread in threads: thread.join(3); self.assertFalse(thread.is_alive())
        self.assertEqual(keys, ['synthetic-shared-token']*4)
        self.assertEqual(len(calls), 1)

    def test_bank_context_and_cache_are_not_shared(self):
        calls=[]
        def send(method,path,headers,body,timeout):
            data=json.loads(body);calls.append(data)
            return 200, {'apiKey':'synthetic-key-'+data['clientId']}
        a=PluggyClient(config(),send=send);b=PluggyClient(config('santander'),send=send)
        self.assertNotEqual(a._api_key(),b._api_key())
        self.assertEqual([r['clientId'] for r in calls],['synthetic-client-itau','synthetic-client-santander'])

    def test_invalid_auth_response_does_not_enter_cache(self):
        for value in (None, '', 123, 'synthetic\nkey'):
            with self.subTest(type=type(value).__name__):
                client=PluggyClient(config(),send=lambda *args:(200,{'apiKey':value}))
                with self.assertRaisesRegex(PluggyError,'INVALID_AUTH_RESPONSE'):client._api_key()
                self.assertIsNone(client._key)


if __name__ == '__main__': unittest.main(verbosity=2)
