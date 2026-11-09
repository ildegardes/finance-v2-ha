"""Synthetic-only policy integration; no credentials or external networking."""
import json
from dataclasses import replace
from contextlib import closing
import unittest
import test_full_coverage as base
from finance_v2.pluggy_client import PluggyClient
from finance_v2.open_finance import OpenFinanceService
from finance_v2.open_finance_coverage import sync_full
from finance_v2.db import connect
from finance_v2.ha_pluggy_options import registry_from_options
from finance_v2.pluggy_config import connections_from_json, PluggyConfigurationError

A='abc00000-0000-4000-8000-000000000001'
B='def00000-0000-4000-8000-000000000002'

class PersonalProxyTests(unittest.TestCase):
    def setUp(self):
        self.fixture=base.CoverageTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.config=replace(self.fixture.config,item_id=A,access_mode='meupluggy_personal')
        self.connector={'id':200,'isSandbox':False,'isOpenFinance':False}
        self.consents=[{'id':'consent-synthetic','itemId':B,'expiresAt':None}]
        self.consent_status=200
        self.financial_foreign=False

    def send(self,method,path,headers,body,timeout):
        if path.startswith('/consents'):
            return self.consent_status,base.collection(self.consents)
        status,data=self.fixture.provider.send(method,path.replace(A,'item-test'),headers,body,timeout)
        data=json.loads(json.dumps(data).replace('item-test',A))
        if path.startswith('/items/') and not path.endswith('/resources'):
            data['connector']=self.connector
        if path.startswith('/accounts?') and self.financial_foreign:
            for row in data['results']:row['itemId']=B
        return status,data

    def service(self):
        settings=replace(self.fixture.settings,pluggy_connections=(self.config,))
        return OpenFinanceService(settings,client_factory=lambda c:PluggyClient(c,send=self.send,max_attempts=1))

    def run_sync(self):return sync_full(self.service(),self.config.id,actor='UI:local')

    def test_foreign_audit_not_financial_block(self):
        before=self.fixture.financial()
        result=self.run_sync()
        self.assertEqual(result['financial_collection_state'],'COMPLETED')
        self.assertEqual(result['consent_audit_state'],'FAILED')
        self.assertEqual(result['warnings'],['ITEM_ID_DIFFERENT'])
        with closing(connect(self.fixture.db)) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM of_resource_records WHERE resource='consents'").fetchone()[0],0)
            self.assertGreater(c.execute("SELECT count(*) FROM of_resource_records WHERE resource='accounts'").fetchone()[0],0)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(before,self.fixture.financial())

    def test_strict_still_rejects(self):
        self.config=replace(self.config,access_mode='strict')
        result=self.run_sync()
        self.assertEqual(result['financial_collection_state'],'FAILED')

    def test_real_context_rejects_sandbox(self):
        self.connector['isSandbox']=True
        self.assertEqual(self.run_sync()['financial_collection_state'],'FAILED')

    def test_wrong_connector_rejected(self):
        self.connector['id']=601
        self.assertEqual(self.run_sync()['financial_collection_state'],'FAILED')

    def test_missing_metadata_rejected(self):
        self.connector={}
        self.assertEqual(self.run_sync()['financial_collection_state'],'FAILED')

    def test_financial_foreign_still_rejected(self):
        self.financial_foreign=True
        self.assertEqual(self.run_sync()['financial_collection_state'],'FAILED')

    def test_valid_consent(self):
        self.consents[0]['itemId']=A
        self.assertEqual(self.run_sync()['consent_audit_state'],'AVAILABLE')

    def test_mixed_revoked_blocks_regardless_order(self):
        self.consents.append({'id':'local-synthetic','itemId':A,'revokedAt':'2026-01-01T00:00:00Z'})
        self.assertEqual(self.run_sync()['financial_collection_state'],'FAILED')

    def test_missing_association_blocks(self):
        self.consents=[{'id':'missing-association'}]
        self.assertEqual(self.run_sync()['financial_collection_state'],'FAILED')

    def test_matching_expired_blocks(self):
        self.consents=[{'id':'expired','itemId':A,'expiresAt':'2000-01-01T00:00:00Z'}]
        self.assertEqual(self.run_sync()['financial_collection_state'],'FAILED')

    def test_case_equivalent_revocation_cannot_be_ignored(self):
        self.consents=[{'id':'case-equivalent','itemId':A.upper(),'revokedAt':'2026-01-01T00:00:00Z'}]
        self.assertEqual(self.run_sync()['financial_collection_state'],'FAILED')

    def test_case_equivalent_not_automatically_accepted(self):
        self.consents=[{'id':'case-equivalent','itemId':A.upper()}]
        self.assertEqual(self.run_sync()['financial_collection_state'],'FAILED')

    def test_invalid_later_expiry_not_hidden(self):
        self.consents=[{'id':'active','itemId':A,'expiresAt':None},
                       {'id':'invalid','itemId':B,'expiresAt':'invalid'}]
        self.assertEqual(self.run_sync()['financial_collection_state'],'FAILED')

    def test_sandbox_profile_rejects_real(self):
        self.config=replace(self.config,access_mode='sandbox')
        self.assertEqual(self.run_sync()['financial_collection_state'],'FAILED')

    def test_legacy_personal_entry_cannot_bypass_policy(self):
        self.connector['isSandbox']=True
        result=self.service().sync_one(self.config.id,actor='UI:local')
        self.assertEqual(result['financial_collection_state'],'FAILED')

    def test_invalid_profile_rejected(self):
        with self.assertRaises(PluggyConfigurationError):
            replace(self.config,access_mode='untrusted')

    def test_audit_unavailable_not_approval(self):
        self.consent_status=404
        self.assertEqual(self.run_sync()['consent_audit_state'],'NOT_AVAILABLE')

    def test_empty_not_authorized_claim(self):
        self.consents=[]
        result=self.run_sync()
        self.assertEqual(result['financial_collection_state'],'COMPLETED')
        with closing(connect(self.fixture.db)) as c:
            self.assertEqual(c.execute("SELECT state FROM of_collection_checkpoints WHERE resource='consents'").fetchone()[0],'EMPTY')

    def test_denied_audit_not_approval(self):
        self.consent_status=403
        self.assertEqual(self.run_sync()['consent_audit_state'],'NOT_AUTHORIZED')

    def test_replay_idempotent(self):
        self.run_sync()
        with closing(connect(self.fixture.db)) as c:
            count=c.execute('SELECT count(*) FROM of_resource_revisions').fetchone()[0]
        self.run_sync()
        with closing(connect(self.fixture.db)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM of_resource_revisions').fetchone()[0],count)

    def test_domains_expose_failed_audit_separately(self):
        from finance_v2.open_finance_domain import query_domain
        service=self.service()
        sync_full(service,self.config.id,actor='UI:local')
        settings=replace(self.fixture.settings,pluggy_connections=(self.config,))
        for resource in ('accounts','transactions','bills','investments','investment_transactions','loans','statements'):
            with closing(connect(self.fixture.db)) as c:
                result=query_domain(c,settings,{'resource':[resource]})
            audit=result['consent_diagnostics'][0]
            self.assertEqual(audit['state'],'ASSOCIATION_INCONSISTENT')
            self.assertEqual(audit['access_mode'],'meupluggy_personal')

    def test_options_and_default(self):
        options={'open_finance_enabled':True,'pluggy_itau_enabled':True,
            'pluggy_itau_client_id':'synthetic','pluggy_itau_client_secret':'synthetic',
            'pluggy_itau_item_id':A,'pluggy_itau_access_mode':'meupluggy_personal'}
        self.assertEqual(connections_from_json(registry_from_options(options))[0].access_mode,'meupluggy_personal')
        del options['pluggy_itau_access_mode']
        self.assertEqual(connections_from_json(registry_from_options(options))[0].access_mode,'strict')

if __name__=='__main__':unittest.main(verbosity=2)
