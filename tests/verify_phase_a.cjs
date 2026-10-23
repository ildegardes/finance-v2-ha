// Audit staged Phase A assets plus the five explicitly authorized release metadata files.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..'),baseline='f634d2b7ff9b6616ef2f02624027efb1ac066a99';
const phase='5fd21c75443891e13202c56bb79700dd1da730ea',version='0.1.22-open-finance.1',previous='0.1.21-open-finance.1';
const git=(...args)=>cp.execFileSync('git',args,{cwd:root,maxBuffer:20*1024*1024});
const hash=b=>crypto.createHash('sha256').update(b).digest('hex').toUpperCase();
const prefix='finance-v17/src/finance_v2/web/';
const allowed=['app.js','completion.js','index.html','open-finance.css','open-finance.js','revenues.js','privacy.css','privacy.js'].map(f=>prefix+f).sort();
const metadata=['finance-v17/config.yaml','finance-v17/Dockerfile','finance-v17/src/finance_v2/__init__.py','finance-v17/CHANGELOG.md','finance-v17/DOCS.md'].sort();
const changed=git('diff','--cached','--name-only',baseline,'--','finance-v17').toString().trim().split('\n').filter(Boolean).sort();
assert.deepEqual(changed,[...allowed,...metadata].sort(),'Only eight Phase A assets and five authorized release metadata files may differ');
assert.deepEqual(git('diff','--cached','--name-only',phase,'--','finance-v17').toString().trim().split('\n').filter(Boolean).sort(),metadata,'No release-time functional changes');
for(const [file,marker] of [
  ['finance-v17/config.yaml',`version: "${previous}"`],
  ['finance-v17/Dockerfile',`io.hass.version="${previous}"`],
  ['finance-v17/src/finance_v2/__init__.py',`__version__ = "${previous}"`]]){
  const original=git('show',phase+':'+file).toString();
  assert.equal(original.split(marker).length,2,'Exactly one original version marker');
  assert.equal(git('show',':'+file).toString(),original.replace(marker,marker.replace(previous,version)),file+': version-only change');
}
for(const [file,expected] of Object.entries({
  'finance-v17/CHANGELOG.md':'2AAA1394D67477A1E227480BAB59FD98792396D647A298654DD551C2AE6CB02E',
  'finance-v17/DOCS.md':'A185EACDDDB4F5ACFE861D819F899662FAAFA7095F3F358997C4D0CEA078B167'}))assert.equal(hash(git('show',':'+file)),expected,'Exact authorized release documentation: '+file);
git('diff','--cached','--check');
const lock=JSON.parse(git('show',':docs/open-finance/BUILD_LOCK.json'));
assert.deepEqual(git('show',':docs/open-finance/BUILD_LOCK.json'),git('show',baseline+':docs/open-finance/BUILD_LOCK.json'),'Historical BUILD_LOCK is immutable');
assert.equal(Object.keys(lock.protected_files).length,8);
const protectedFiles={};
for(const [file,expected] of Object.entries(lock.protected_files)){
  assert.equal(hash(git('show',baseline+':'+file)),expected);
  assert.equal(hash(git('show',':'+file)),expected);
  assert.equal(hash(fs.readFileSync(path.join(root,file))),expected);
  protectedFiles[file]=expected;
}
const product=git('ls-files','--','finance-v17').toString().trim().split('\n');
assert.deepEqual(product,git('ls-tree','-r','--name-only',phase,'--','finance-v17').toString().trim().split('\n'),'No added or removed product files');
for(const file of product)if(!metadata.includes(file))assert.deepEqual(git('show',':'+file),git('show',phase+':'+file),'Preserve exact Phase A product bytes: '+file);
const canonicalProduct=Object.fromEntries(product.map(f=>[f,hash(git('show',':'+f))]));
assert.match(git('show',':finance-v17/config.yaml').toString(),/open_finance_auto_sync_enabled: false/);
const releaseManifest={contract:'FINANCE-PHASE-A-RELEASE/1',version,published_baseline:baseline,phase_a_commit:phase,sqlite_schema:9,new_migrations:[],historical_build_lock_sha256:hash(git('show',':docs/open-finance/BUILD_LOCK.json')),product_hash_representation:'Canonical Git blobs; protected files additionally require identical working bytes.',product_files_sha256:canonicalProduct,protected_files:protectedFiles};
assert.deepEqual(JSON.parse(git('show',':docs/open-finance/RELEASE_0.1.22_MANIFEST.json')),releaseManifest,'Exact independent release manifest');
const report={baseline,phase,version,product_files:product.length,allowed_product_changes:changed,canonical_staged_product_sha256:canonicalProduct,protected_files:protectedFiles,protected_count:Object.keys(protectedFiles).length,backend_api_migrations_auth_scheduler_and_configuration:'UNCHANGED_EXCEPT_VERSION_METADATA',diff_check:'PASS',scope:'No database access or migration execution; staged Git objects plus working protected-file hashes only'};
if(process.argv[2]){assert(path.isAbsolute(process.argv[2]));assert(!fs.existsSync(process.argv[2]));fs.writeFileSync(process.argv[2],JSON.stringify(report,null,2)+'\n')}
console.log(JSON.stringify({status:'PASS',version,product_files:product.length,protected:Object.keys(protectedFiles).length,frontend_changes:allowed.length,release_metadata_changes:metadata.length}));
