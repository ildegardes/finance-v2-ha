"""Post-ingestion HTTP privacy regression, synthetic credentials only."""
import io,json,unittest
from contextlib import closing
from dataclasses import replace
from copy import deepcopy
import test_personal_proxy as personal
from finance_v2.db import connect
from finance_v2.open_finance_output_privacy import public_payload
class OutputPrivacyTests(unittest.TestCase):
 setUp=personal.PersonalProxyTests.setUp
 send=personal.PersonalProxyTests.send
 service=personal.PersonalProxyTests.service
 run_sync=personal.PersonalProxyTests.run_sync
 def test_all_resource_views_after_ingestion_hide_configuration_values(self):
  self.consents[0]['itemId']=self.config.item_id;self.run_sync()
  self.fixture.settings=replace(self.fixture.settings,pluggy_connections=(self.config,))
  for family in ('resources','domain'):
   for resource in ('item','resources','consents','accounts','transactions','investments','investment_transactions','loans','bills','statements'):
    for history in ('0','1'):
     status,data=self.fixture.request('/api/v2/open-finance/'+family+'?resource='+resource+'&history='+history)
     self.assertEqual(status,200);encoded=json.dumps(data)
     for value in (self.config.client_id,self.config.client_secret,self.config.item_id):self.assertNotIn(value,encoded)
     if resource=='item':
      for row in data['items']:
       self.assertEqual(row.get('external_id',row.get('identity',{}).get('external_id')),'')
 def test_projection_is_non_mutating_and_does_not_write_sqlite(self):
  r=self.run_sync()
  with closing(connect(self.fixture.db)) as c:
   before=list(c.iterdump());payload={'resource':'accounts','items':[{'data':{'itemId':self.config.item_id,'balance':'125.50'},'external_id':'synthetic-account'}]};original=deepcopy(payload)
   result=public_payload(payload,self.fixture.settings)
   self.assertEqual(original,payload);self.assertEqual(before,list(c.iterdump()));self.assertEqual(result['items'][0]['data']['balance'],'125.50');self.assertEqual(result['items'][0]['external_id'],'synthetic-account')
 def test_echoed_credentials_and_item_case_are_redacted(self):
  settings=replace(self.fixture.settings,pluggy_connections=(self.config,))
  data={'message':'prefix '+self.config.client_secret+' suffix','nested':[{'ClientSecret':self.config.client_secret,'itemId':self.config.item_id,'note':self.config.item_id.upper()}]}
  encoded=json.dumps(public_payload(data,settings))
  for value in (self.config.client_secret,self.config.item_id,self.config.item_id.upper()):self.assertNotIn(value,encoded)
 def test_other_profiles_keep_policy_and_financial_state(self):
  for profile in ('strict','sandbox'):
   config=replace(self.config,access_mode=profile);settings=replace(self.fixture.settings,pluggy_connections=(config,));data={'run':{'state':'FAILED','error_code':'ACCOUNT_SCOPE_MISMATCH'},'data':{'itemId':config.item_id,'amount':50}}
   result=public_payload(data,settings);self.assertEqual(result['run'],data['run']);self.assertEqual(result['data']['amount'],50)
 def test_failure_and_audit_codes_are_preserved(self):
  settings=replace(self.fixture.settings,pluggy_connections=(self.config,));r=self.run_sync();out=public_payload({'run':r},settings)['run']
  self.assertEqual(out['consent_audit_state'],'FAILED');self.assertEqual(out['warnings'],['ITEM_ID_DIFFERENT']);self.assertEqual(out['operational_presentation']['overall_state'],'PARTIAL')

 def test_redaction_marker_cannot_itself_echo_an_opaque_credential(self):
  config=replace(self.config,client_secret='PRIVATE_CONFIG');settings=replace(self.fixture.settings,pluggy_connections=(config,))
  result=public_payload({'note':'prefix '+config.client_secret+' suffix'},settings)
  self.assertEqual(result['note'],'');self.assertNotIn(config.client_secret,json.dumps(result))
