"""Supervisor options integration, all identifiers/keys are synthetic and in memory."""
from pathlib import Path
from contextlib import redirect_stderr
from unittest.mock import patch
import io,json,os,tempfile,unittest
import test_personal_proxy as personal
from finance_v2.ha_pluggy_options import registry_from_options,load_registry
from finance_v2.config import Settings
from finance_v2.pluggy_client import PluggyClient
from finance_v2.open_finance_auto import CoverageWorkers
class AddonConfigTests(unittest.TestCase):
 def options(self):
  o={'timezone':'UTC','ui_token':'synthetic-ui-only','open_finance_enabled':True,'open_finance_auto_sync_enabled':False}
  for bank,item in (('itau',personal.A),('santander',personal.B)):
   o.update({'pluggy_'+bank+'_enabled':True,'pluggy_'+bank+'_access_mode':'meupluggy_personal','pluggy_'+bank+'_client_id':'synthetic-client-'+bank,'pluggy_'+bank+'_client_secret':'synthetic-secret-'+bank,'pluggy_'+bank+'_item_id':item})
  return o
 def settings(self,o):
  with patch.dict(os.environ,{'APP_TIMEZONE':'UTC','FINANCE_V2_PLUGGY_CONNECTIONS_JSON':registry_from_options(o)},clear=True):return Settings.from_env()
 def test_supervisor_options_file_to_runtime_independent_auth_and_item(self):
  o=self.options()
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'options.json';p.write_text(json.dumps(o))
   with patch.dict(os.environ,{'APP_TIMEZONE':'UTC','FINANCE_V2_PLUGGY_CONNECTIONS_JSON':load_registry(p)},clear=True):cfg=Settings.from_env()
  self.assertEqual(len(cfg.pluggy_connections),2)
  for c in cfg.pluggy_connections:
   calls=[]
   def send(method,path,headers,body,timeout):
    calls.append(method)
    if method=='POST':
     self.assertEqual(path,'/auth');self.assertEqual(json.loads(body),{'clientId':o['pluggy_'+c.id+'_client_id'],'clientSecret':o['pluggy_'+c.id+'_client_secret']});return 200,{'apiKey':'synthetic-key-'+c.id}
    self.assertEqual(headers['X-API-KEY'],'synthetic-key-'+c.id);self.assertEqual(path,'/items/'+o['pluggy_'+c.id+'_item_id']);return 200,{'id':c.item_id}
   client=PluggyClient(c,send=send,max_attempts=1)
   self.assertEqual(client.coverage_get('/items/'+c.item_id)[0]['id'],c.item_id);self.assertEqual(calls,['POST','GET'])
 def test_absent_credentials_no_workers_and_static_error(self):
  o={'open_finance_enabled':True,'pluggy_itau_enabled':True};log=io.StringIO()
  with redirect_stderr(log):cfg=self.settings(o)
  self.assertEqual(cfg.pluggy_connections,());self.assertEqual(log.getvalue().strip(),'OPEN_FINANCE_CONNECTION_INVALID_ITAU')
 def test_incomplete_peer_does_not_contaminate_valid_bank(self):
  o=self.options();o['pluggy_itau_client_secret']='';log=io.StringIO()
  with redirect_stderr(log):cfg=self.settings(o)
  self.assertEqual([c.id for c in cfg.pluggy_connections],['santander']);self.assertNotIn('synthetic-secret',log.getvalue());self.assertNotIn(personal.A,log.getvalue())
 def test_auto_sync_off_even_with_complete_credentials(self):
  cfg=self.settings(self.options());workers=CoverageWorkers(cfg,send=lambda *a: self.fail('UNEXPECTED_AUTH'))
  workers.start();self.assertEqual(workers.threads,[]);workers.stop()
 def test_missing_new_profile_defaults_strict_and_preserves_existing_values(self):
  o=self.options()
  for bank in ('itau','santander'):del o['pluggy_'+bank+'_access_mode']
  cfg=self.settings(o)
  for c in cfg.pluggy_connections:
   self.assertEqual(c.access_mode,'strict')
   for field in ('client_id','client_secret','item_id'):self.assertEqual(getattr(c,field),o['pluggy_'+c.id+'_'+field])
 def test_runtime_sources_have_no_pc01_dependency(self):
  root=Path(__file__).resolve().parents[1]/'finance-v17'
  for p in (root/'src/finance_v2').rglob('*.py'):
   text=p.read_text(encoding='utf-8')
   for forbidden in ('FinancePluggyPrivateStaging','AppData/Local','CredReadW','win32cred','FinancePluggyVault'):self.assertNotIn(forbidden,text)
 def test_preserved_option_names_and_sensitive_types(self):
  import re
  root=Path(__file__).resolve().parents[1]
  manifest=Path(os.environ.get('ADDON_MANIFEST_PATH',str(root/'finance-v17/config.yaml')))
  if not manifest.is_file() and 'ADDON_MANIFEST_PATH' not in os.environ:manifest=root.parent/'metadata/config.yaml'
  new=manifest.read_text();old=(root.parent/'baseline/finance-v17/config.yaml').read_text()
  for bank in ('itau','santander'):
   for field,kind in (('client_id','str'),('client_secret','password'),('item_id','str')):
    line='  pluggy_'+bank+'_'+field+': '+kind
    self.assertIn(line,old.split('schema:')[1]);self.assertIn(line,new.split('schema:')[1])
  self.assertIn('  open_finance_auto_sync_enabled: false',new)

 def test_public_read_api_never_returns_configuration_values(self):
  from dataclasses import replace
  from test_full_coverage import CoverageTests
  fixture=CoverageTests();fixture.setUp()
  try:
   options=self.options();cfg=self.settings(options)
   fixture.settings=replace(cfg,database_path=fixture.db,ui_token=fixture.settings.ui_token)
   for endpoint in ('connections','catalogs','coverage','sync-runs'):
    status,response=fixture.request('/api/v2/open-finance/'+endpoint)
    self.assertEqual(status,200)
    encoded=json.dumps(response)
    for bank in ('itau','santander'):
     for field in ('client_id','client_secret','item_id'):self.assertNotIn(options['pluggy_'+bank+'_'+field],encoded)
  finally:fixture.doCleanups()
