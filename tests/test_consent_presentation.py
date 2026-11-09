"""Presentation-only synthetic regression; no real provider credentials or database."""
import unittest
from contextlib import closing
from dataclasses import replace
import test_personal_proxy as personal
from finance_v2.open_finance_presentation import present_run,present_payload
from finance_v2.db import connect
A=personal.A
PersonalProxyTests=personal.PersonalProxyTests
class PresentationTests(unittest.TestCase):
 setUp=PersonalProxyTests.setUp
 send=PersonalProxyTests.send
 service=PersonalProxyTests.service
 run_sync=PersonalProxyTests.run_sync
 def classified(self):return self.run_sync()['operational_presentation']
 def test_partial_preserves_raw(self):
  r=self.run_sync();self.assertEqual((r['state'],r['consent_audit_state'],r['financial_collection_state']),('SUCCEEDED','FAILED','COMPLETED'))
  p=r['operational_presentation'];self.assertEqual((p['overall_state'],p['consent_state'],p['raw_consent_error_code']),('PARTIAL','UNVERIFIED','ITEM_ID_DIFFERENT'))
 def test_valid_observation_not_current_permission(self):
  self.consents[0]['itemId']=A;p=self.classified();self.assertEqual(p['consent_state'],'VALIDATED_AT_OBSERVATION');self.assertEqual(p['overall_state'],'COMPLETED');self.assertEqual(p['authorization_state'],'NOT_ESTABLISHED_BY_PRESENTATION')
 def test_empty_unverified(self):
  self.consents=[];p=self.classified();self.assertEqual((p['overall_state'],p['consent_state']),('PARTIAL','UNVERIFIED'))
 def test_403_unverified(self):
  self.consent_status=403;self.assertEqual(self.classified()['overall_state'],'PARTIAL')
 def test_404_unverified(self):
  self.consent_status=404;self.assertEqual(self.classified()['overall_state'],'PARTIAL')
 def test_failed_finance_not_completed(self):
  self.financial_foreign=True;self.assertEqual(self.classified()['financial_collection_state'],'FAILED')
 def test_revoked_not_completed(self):
  self.consents=[{'id':'synthetic','itemId':A,'revokedAt':'2026-01-01T00:00:00Z'}];self.assertEqual(self.classified()['overall_state'],'FAILED')
 def test_expired_not_completed(self):
  self.consents=[{'id':'synthetic','itemId':A,'expiresAt':'2000-01-01T00:00:00Z'}];self.assertEqual(self.classified()['overall_state'],'FAILED')
 def test_history_same_run_evidence_only_no_writes(self):
  self.consents[0]['itemId']=A;r=self.run_sync()
  with closing(connect(self.fixture.db)) as c:
   before=list(c.iterdump());old={**r,'id':'old-synthetic-run'}
   p=present_run(c,self.config,old)['operational_presentation'];self.assertEqual((p['consent_state'],p['evidence_basis']),('UNVERIFIED','NOT_AVAILABLE_FOR_THIS_RUN'))
   self.assertEqual(before,list(c.iterdump()))
 def test_other_profiles_identical(self):
  with closing(connect(self.fixture.db)) as c:
   for profile in ('strict','sandbox'):
    r={'id':'synthetic','state':'SUCCEEDED'};self.assertIs(present_run(c,replace(self.config,access_mode=profile),r),r)
 def test_payload_mixed_profiles(self):
  r=self.run_sync();settings=replace(self.fixture.settings,pluggy_connections=(self.config,replace(self.config,id='other',access_mode='strict')))
  with closing(connect(self.fixture.db)) as c:
   out=present_payload(c,settings,{'items':[r,{'connection_id':'other','state':'SUCCEEDED'}]},'open_finance_runs')
   self.assertIn('operational_presentation',out['items'][0]);self.assertNotIn('operational_presentation',out['items'][1])
class HttpPresentationTests(unittest.TestCase):
 setUp=PersonalProxyTests.setUp
 send=PersonalProxyTests.send
 service=PersonalProxyTests.service
 run_sync=PersonalProxyTests.run_sync
 def test_read_paths_and_raw_preservation(self):
  r=self.run_sync()
  self.fixture.settings=replace(self.fixture.settings,pluggy_connections=(self.config,))
  for path in ('catalogs','connections','coverage','sync-runs'):
   status,out=self.fixture.request('/api/v2/open-finance/'+path)
   self.assertEqual(status,200)
   if path=='catalogs':rows=out['runs']
   elif path=='connections':rows=[out['connections'][0]['last_run']]
   elif path=='coverage':rows=out['runs']
   else:rows=out['items']
   self.assertEqual(rows[0]['operational_presentation']['overall_state'],'PARTIAL')
  status,out=self.fixture.request('/api/v2/open-finance/sync-run?run_id='+r['id'])
  self.assertEqual(status,200);self.assertEqual(out['run']['state'],'SUCCEEDED')
 def test_schema_extension_optional(self):
  from finance_v2.open_finance_http import openapi_paths
  paths=openapi_paths()
  schema=paths['/api/v2/open-finance/coverage']['get']['responses']['200']['content']['application/json']['schema']['properties']['runs']['items']
  self.assertIn('operational_presentation',schema['properties'])
  self.assertNotIn('operational_presentation',schema['required'])

del PersonalProxyTests
