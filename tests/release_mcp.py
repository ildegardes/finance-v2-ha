"""Real WSGI MCP metadata/auth checks; no server, database or provider access."""
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'finance-v17' / 'src'))


def deny_external_state(event, args):
    if event in {'sqlite3.connect', 'socket.connect', 'socket.bind', 'subprocess.Popen'}:
        raise AssertionError('External state forbidden in metadata test: ' + event)


sys.addaudithook(deny_external_state)
from finance_v2 import __version__
from finance_v2.api import Application
from finance_v2.config import ExternalClientCredential, Settings


class ReleaseMcpTests(unittest.TestCase):
    def setUp(self):
        self.app = Application(Settings(
            database_path=ROOT / 'DO_NOT_CREATE_RELEASE_TEST.sqlite3', timezone='UTC',
            host='127.0.0.1', port=8766, busy_timeout_ms=0,
            ui_token='synthetic-owner-only-token', external_clients=(
                ExternalClientCredential('synthetic', 'synthetic-external-only-token', frozenset({'finance:read'})),)))

    def request(self, method='initialize', token='synthetic-external-only-token', accept='application/json'):
        raw = json.dumps({'jsonrpc':'2.0', 'id':7, 'method':method, 'params':{}}).encode()
        env = {'PATH_INFO':'/mcp', 'REQUEST_METHOD':'POST', 'CONTENT_LENGTH':str(len(raw)),
               'CONTENT_TYPE':'application/json', 'wsgi.input':io.BytesIO(raw), 'HTTP_ACCEPT':accept}
        if token is not None:
            env['HTTP_AUTHORIZATION'] = 'Bearer ' + token
        captured = {}
        def start(status, headers):
            captured.update(status=int(status.split()[0]), headers=dict(headers))
        body = b''.join(self.app(env, start)).decode()
        payload = json.loads(body.split('data: ',1)[1].strip() if accept=='text/event-stream' else body)
        return captured, payload

    def test_initialize_exact_release_and_protocol(self):
        captured, payload = self.request()
        self.assertEqual(captured['status'], 200)
        self.assertEqual(__version__, '0.1.25-open-finance.1')
        self.assertEqual(payload, {'jsonrpc':'2.0','id':7,'result':{
            'protocolVersion':'2025-03-26','capabilities':{'tools':{'listChanged':False}},
            'serverInfo':{'name':'Finance V2','version':'0.1.25-open-finance.1'}}})

    def test_sse_transport_preserves_initialize(self):
        captured, payload = self.request(accept='text/event-stream')
        self.assertEqual(captured['status'], 200)
        self.assertEqual(captured['headers']['Content-Type'], 'text/event-stream')
        self.assertEqual(payload['result']['serverInfo']['version'], '0.1.25-open-finance.1')

    def test_tools_contract_unchanged(self):
        captured, payload = self.request('tools/list')
        self.assertEqual(captured['status'], 200)
        self.assertEqual(payload['result'], {'tools':self.app.mcp_tools()})
        self.assertIn('finance_list_expenses', [t['name'] for t in payload['result']['tools']])

    def test_missing_token_stays_unauthenticated(self):
        captured, payload = self.request(token=None)
        self.assertEqual(captured['status'], 401)
        self.assertEqual(payload['error']['code'], 'UNAUTHENTICATED')

    def test_owner_cannot_use_external_mcp(self):
        captured, payload = self.request(token='synthetic-owner-only-token')
        self.assertEqual(captured['status'], 403)
        self.assertEqual(payload['error']['code'], 'FORBIDDEN')

    def test_unknown_method_still_rejected(self):
        captured, payload = self.request('synthetic/unknown')
        self.assertEqual(captured['status'], 400)
        self.assertEqual(payload['error']['code'], 'MCP_METHOD_NOT_FOUND')


if __name__ == '__main__':
    unittest.main(verbosity=2)
