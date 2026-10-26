"""Only synthetic fixtures, provider responses and loopback requests."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import threading
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
CANDIDATE = ROOT.parents[1]
sys.path.insert(0, str(CANDIDATE / 'finance-v17/src'))
FIXTURES = Path(os.environ.get('VALIDATION_FIXTURE_ROOT', str(ROOT / 'fixtures'))).resolve()
FIXTURES.mkdir(parents=True, exist_ok=True)

def audit(event, args):
    if event == 'sqlite3.connect':
        raw = os.fsdecode(args[0])
        if raw == ':memory:':
            return
        path = Path(unquote(urlsplit(raw).path).lstrip('/') if os.name == 'nt' else unquote(urlsplit(raw).path)) if raw.startswith('file:') else Path(raw)
        if not path.resolve().is_relative_to(FIXTURES):
            raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
    if event == 'socket.connect':
        address = args[1]
        if not isinstance(address, tuple) or address[0] != '127.0.0.1':
            raise AssertionError('EXTERNAL_NETWORK_FORBIDDEN')
    if event == 'socket.getaddrinfo' and args[0] not in ('127.0.0.1', 'localhost', None):
        raise AssertionError('EXTERNAL_DNS_FORBIDDEN')
sys.addaudithook(audit)

from finance_v2.api import Application
from finance_v2.config import Settings, ExternalClientCredential
from finance_v2.db import connect
from finance_v2.domain.clock import FixedClock
from finance_v2.pluggy_config import PluggyConnection
from finance_v2.pluggy_client import PluggyClient

spec = importlib.util.spec_from_file_location('stock_coverage', CANDIDATE / 'tests/test_full_coverage.py')
STOCK = importlib.util.module_from_spec(spec)
spec.loader.exec_module(STOCK)
CLOCK = FixedClock(datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc), 'UTC')

def settings(path, automatic=True):
    connections = tuple(PluggyConnection(bank, name, 'synthetic-client-'+bank,
        'synthetic-secret-'+bank, 'synthetic-item-'+bank, True, automatic)
        for bank, name in (('itau','Itaú sintético'), ('santander','Santander sintético')))
    return Settings(database_path=Path(path), timezone='UTC', host='127.0.0.1', port=8766,
        busy_timeout_ms=300, ui_token='synthetic-owner-only-token', pluggy_connections=connections,
        external_clients=(ExternalClientCredential('fixture','synthetic-external-only-token',frozenset({'finance:read'})),))

def request(app, path, body=None, method='GET', key=None):
    raw = json.dumps(body).encode() if body is not None else b''
    url = urlsplit(path)
    env = {'PATH_INFO':url.path, 'QUERY_STRING':url.query, 'REQUEST_METHOD':method,
        'CONTENT_TYPE':'application/json', 'CONTENT_LENGTH':str(len(raw)), 'wsgi.input':io.BytesIO(raw),
        'HTTP_AUTHORIZATION':'Bearer synthetic-owner-only-token'}
    if key:
        env['HTTP_IDEMPOTENCY_KEY'] = key
    status = []
    payload = b''.join(app(env, lambda value, headers: status.append(int(value.split()[0]))))
    return status[0], json.loads(payload)

def seed_official(config):
    app = Application(config, CLOCK)
    def create(path, body, expected=201, key=None):
        status, result = request(app, '/api/v2/'+path, body, 'POST', key)
        assert status == expected, (path, status, result.get('error'))
        return result
    account = create('accounts', {'name':'Conta oficial artificial'})['id']
    category = create('categories', {'name':'Categoria oficial artificial'})['id']
    tag = create('tags', {'name':'Etiqueta artificial'})['id']
    expense = create('expenses', {'description':'Despesa oficial artificial','amount_cents':12345,
        'expense_date':'2026-10-20','due_date':'2026-10-25','planned_payment_method':'PIX',
        'category_id':category,'account_id':account,'tag_ids':[tag]})['id']
    create('expenses/'+str(expense)+'/pay', {'paid_on':'2026-10-25','payment_method':'PIX','account_id':account}, 200, 'synthetic-pay-fixture-0001')
    revenue = create('revenues', {'description':'Receita artificial','amount_cents':76543,
        'competence_date':'2026-10-20','expected_on':'2026-10-25','category_id':category,'account_id':account}, key='synthetic-revenue-fixture-0001')['id']
    create('revenues/'+str(revenue)+'/receive', {'received_on':'2026-10-25','account_id':account}, 200, 'synthetic-receipt-fixture-0001')
    card = create('cards', {'name':'Cartão oficial artificial','payment_mode':'MANUAL',
        'payment_account_id':None,'effective_from':'2026-01-01','closing_day':10,'due_day':20})['id']
    create('expenses', {'description':'Compra oficial artificial','amount_cents':1999,
        'expense_date':'2026-10-20','category_id':category,'planned_payment_method':'CREDIT_CARD','card_id':card})
    return {'account':account,'category':category,'expense':expense,'revenue':revenue,'card':card}

def fingerprint(path):
    """All pre-existing non-OF tables, full typed rows and schema; not just counts."""
    with closing(connect(path)) as c:
        names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'of_%' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        result = {}
        for name in names:
            rows = [tuple(row) for row in c.execute('SELECT * FROM "'+name+'"')]
            encoded_rows = sorted(json.dumps(row, ensure_ascii=True, separators=(',',':'), default=lambda x:{'bytes':x.hex()}) for row in rows)
            structure = [tuple(row) for row in c.execute('SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name=? ORDER BY type,name', (name,))]
            content = json.dumps([structure, encoded_rows], separators=(',',':')).encode()
            result[name] = {'rows':len(rows),'sha256':sha256(content).hexdigest()}
        has_sequences = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'").fetchone()
        sequences = [tuple(row) for row in c.execute("SELECT name,seq FROM sqlite_sequence WHERE name NOT LIKE 'of_%' ORDER BY name")] if has_sequences else None
        result['__official_sequences__'] = {'sha256':sha256(json.dumps(sequences).encode()).hexdigest()}
        return result

class Provider(STOCK.Provider):
    def __init__(self, connection, mode='ok'):
        super().__init__()
        self.connection, self.mode = connection, mode
        self.entered, self.release = threading.Event(), threading.Event()
        self.visited = []
    def send(self, method, path, headers, body, timeout):
        self.visited.append((method, path))
        if self.mode == 'timeout':
            raise TimeoutError('synthetic timeout')
        if self.mode == 'unavailable':
            return 503, None
        if method == 'POST':
            assert path == '/auth'
            assert json.loads(body) == {'clientId':self.connection.client_id,'clientSecret':self.connection.client_secret}
            if self.mode == 'auth-failed':
                return 401, None
            return 200, {'apiKey':'synthetic-key-'+self.connection.id}
        assert headers['X-API-KEY'] == 'synthetic-key-'+self.connection.id
        base = urlsplit(path).path
        if base == '/loans' and self.mode == 'hold':
            self.entered.set()
            assert self.release.wait(5), 'SYNTHETIC_HOLD_LIMIT'
        translated = path.replace(self.connection.item_id, 'item-test')
        status, data = super().send(method, translated, headers, body, timeout)
        def remap(value):
            if isinstance(value, dict): return {k:remap(v) for k,v in value.items()}
            if isinstance(value, list): return [remap(v) for v in value]
            return self.connection.item_id if value == 'item-test' else value
        return status, remap(data)

class Providers:
    def __init__(self, config, modes=None):
        self.banks = {c.id:Provider(c,(modes or {}).get(c.id,'ok')) for c in config.pluggy_connections}
    def send(self, method, path, headers, body, timeout):
        bank = json.loads(body)['clientId'].removeprefix('synthetic-client-') if method == 'POST' else headers['X-API-KEY'].removeprefix('synthetic-key-')
        return self.banks[bank].send(method, path, headers, body, timeout)
    def factory(self, connection):
        return PluggyClient(connection, send=self.banks[connection.id].send, sleep=lambda _:None, max_attempts=1)
