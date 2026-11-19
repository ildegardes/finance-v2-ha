"""Card association diagnostics over synthetic Pluggy imports."""
from contextlib import closing
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from finance_v2.db import connect
from finance_v2.open_finance_analytics import analytics
from finance_v2.pluggy_client import PluggyClient
from finance_v2.pluggy_credential_protection import CredentialProtector
import test_full_coverage as fixture


class CardAssociation(unittest.TestCase):
    def setUp(self):
        self.case=fixture.CoverageTests('test_all_products_projection_history_and_financial_preservation')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.consent={'id':'consent-synthetic-040','itemId':'item-test','products':['CREDIT_CARDS'],
                      'openFinancePermissionsGranted':['CREDIT_CARDS_ALL']}
        self.accounts=[]
        for index,balance in enumerate((125,0)):
            self.accounts.append({'id':'card-synthetic-'+str(index),'itemId':'item-test','type':'CREDIT','balance':balance,
                'name':'Cartão de teste '+str(index),'number':'xxxx'+str(9400+index),'currencyCode':'BRL',
                'updatedAt':'2026-10-20T18:00:00Z','creditData':{
                    'status':'ACTIVE','holderType':'MAIN','disaggregatedCreditLimits':[{
                        'creditLineLimitType':'LIMITE_CREDITO_TOTAL','consolidationType':'INDIVIDUAL',
                        'identificationNumber':str(9400+index),'limitAmount':1000,'limitAmountCurrencyCode':'BRL',
                        'isLimitFlexible':False}]}})
        self.late_mismatch=False
        self.item={'id':'item-test','status':'UPDATED','connector':{'id':600,'isOpenFinance':True}}
        self.case.service.client_factory=lambda config: PluggyClient(config,send=self.send,sleep=lambda _:None)

    def send(self,method,path,headers,body,timeout):
        base=urlsplit(path).path
        if base=='/items/item-test':
            return 200,self.item
        if base=='/consents':
            return 200,fixture.collection([self.consent])
        if base=='/accounts':
            return 200,fixture.collection(self.accounts)
        if base=='/loans' and self.late_mismatch:
            return 200,fixture.collection([{'id':'foreign-loan-synthetic','itemId':'foreign-synthetic'}])
        return self.case.provider.send(method,path,headers,body,timeout)

    def read(self,**kwargs):
        fields={'presentation':['BRL'],'start':['2026-10-01'],'end':['2026-10-20'],**kwargs}
        with closing(connect(self.case.db)) as db:
            return analytics(db,self.case.settings,fields,'2026-10-20')['presentation_view']['cards']

    def mutate(self,sql,params=()):
        with closing(connect(self.case.db)) as db:
            return db.execute(sql,params).fetchall()

    def codes(self,**kwargs):
        return {entry['usage'] for entry in self.read(**kwargs)['diagnostics']}

    def test_real_collection_scope_after_unrelated_failure_and_recovery(self):
        self.late_mismatch=True
        self.assertEqual(self.case.sync()['error_code'],'ACCOUNT_SCOPE_MISMATCH')
        cards=self.read()
        self.assertEqual(cards['metric']['amounts'],{'BRL':'125'})
        self.assertEqual(cards['limit_metric']['amounts'],{'BRL':'2000'})
        self.assertEqual(cards['utilization_by_currency'],{'BRL':'0.0625'})
        self.assertEqual({card['used'] for card in cards['items']},{'0','125'})
        self.late_mismatch=False
        self.accounts[0]['itemId']='foreign-synthetic'
        self.assertEqual(self.case.sync()['error_code'],'ACCOUNT_SCOPE_MISMATCH')
        self.assertEqual(self.codes(),{'PRIOR_SCOPE_FAILURE'})
        self.assertEqual(self.read()['metric']['amounts'],{})
        self.accounts[0]['itemId']='item-test'
        self.assertEqual(self.case.sync()['state'],'SUCCEEDED')
        self.assertEqual(self.codes(),{'INCLUDED'})
        self.assertEqual(self.case.sync()['state'],'SUCCEEDED')
        self.assertEqual(self.read()['metric']['amounts'],{'BRL':'125'})
        self.assertEqual(len(self.mutate("SELECT 1 FROM of_resource_records WHERE resource='accounts' AND state='PRESENT'")),2)

    def test_consent_different_from_revocation_and_optional_grants(self):
        self.assertEqual(self.case.sync()['state'],'SUCCEEDED')
        self.consent['itemId']='foreign-synthetic'
        self.assertEqual(self.case.sync()['state'],'FAILED')
        self.assertEqual(self.codes(),{'CONSENT_ITEM_MISMATCH'})
        self.consent.update(itemId='item-test',revokedAt='2020-10-01T00:00:00Z')
        self.assertEqual(self.case.sync()['error_code'],'CONSENT_NOT_ACTIVE')
        self.assertEqual(self.codes(),{'CONSENT_NOT_ACTIVE'})
        del self.consent['revokedAt']
        del self.consent['openFinancePermissionsGranted']
        self.assertEqual(self.case.sync()['state'],'SUCCEEDED')
        self.assertEqual(self.codes(),{'CONSENT_GRANTS_UNREPORTED'})
        self.assertEqual(self.read()['metric']['amounts'],{})

    def test_item_and_binding_are_distinct_including_legacy_without_registry(self):
        self.assertEqual(self.case.sync()['state'],'SUCCEEDED')
        self.mutate("DELETE FROM of_connection_registry WHERE connection_id='bank-test'")
        self.assertEqual(self.codes(),{'INCLUDED'})
        self.mutate("UPDATE of_resource_records SET payload_json=json_remove(payload_json,'$.status') WHERE resource='item'")
        self.assertEqual(self.codes(),{'ITEM_METADATA_INCOMPLETE'})
        self.mutate("UPDATE of_resource_records SET state='NOT_SEEN' WHERE resource='item'")
        self.assertEqual(self.codes(),{'ITEM_RECORD_MISSING'})
        self.assertEqual(self.case.sync()['state'],'SUCCEEDED')
        self.assertEqual(self.codes(),{'INCLUDED'})
        self.mutate("UPDATE of_connections SET binding_hash=? WHERE id='bank-test'",('d'*64,))
        self.assertEqual(self.codes(),{'LOCAL_BINDING_MISMATCH'})

    def test_managed_binding_is_verified_against_protected_credential(self):
        self.assertEqual(self.case.sync()['state'],'SUCCEEDED')
        config=self.case.config
        protector=CredentialProtector('test',{'test':bytes(range(32))})
        protected=protector.seal('application-synthetic',1,config.client_id,config.client_secret)
        self.mutate("UPDATE of_connection_registry SET source='MANAGED' WHERE connection_id='bank-test'")
        self.mutate("INSERT INTO of_pluggy_applications VALUES ('application-synthetic','Synthetic','STRICT')")
        self.mutate("INSERT INTO of_connection_credentials VALUES ('application-synthetic',1,?,?,?,'2026-10-20')",
                    (protected.key_id,protected.nonce,protected.ciphertext))
        self.mutate("INSERT INTO of_managed_pluggy_items VALUES ('bank-test','application-synthetic',1,'item-test',0)")
        with patch('finance_v2.open_finance_card_usage.load_keyring',return_value=protector):
            self.assertEqual(self.codes(),{'INCLUDED'})
            serialized=json.dumps(self.read()['diagnostics'])
            for secret in ('application-synthetic','item-test','9400',config.client_id,config.client_secret,'card-synthetic'):
                self.assertNotIn(secret,serialized)
            self.mutate("UPDATE of_managed_pluggy_items SET item_id='different-synthetic'")
            self.assertEqual(self.codes(),{'LOCAL_BINDING_MISMATCH'})

    def test_partial_and_preserved_accounts_do_not_enter_current_aggregation(self):
        first=self.case.sync()
        self.assertEqual(first['state'],'SUCCEEDED')
        self.assertEqual(self.case.sync()['state'],'SUCCEEDED')
        self.mutate("UPDATE of_resource_records SET last_run_id=? WHERE resource='accounts' AND external_id='card-synthetic-0'",(first['id'],))
        self.assertEqual(self.codes(),{'ACCOUNT_PRESERVED','INCLUDED'})
        self.mutate("UPDATE of_collection_checkpoints SET state='RUNNING',page_count=1 WHERE resource='accounts'")
        self.assertEqual(self.codes(),{'ACCOUNT_COLLECTION_UNVERIFIED'})
        self.assertEqual(self.read()['metric']['amounts'],{})
        self.mutate("UPDATE of_connection_registry SET lifecycle='ARCHIVED' WHERE connection_id='bank-test'")
        self.assertEqual(self.codes(history=['1']),{'HISTORICAL_CONNECTION'})


if __name__=='__main__':
    unittest.main()
