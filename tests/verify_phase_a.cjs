// Audit the staged product tree against the exact published baseline.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..'),baseline='f634d2b7ff9b6616ef2f02624027efb1ac066a99';
const git=(...args)=>cp.execFileSync('git',args,{cwd:root,maxBuffer:20*1024*1024});
const hash=b=>crypto.createHash('sha256').update(b).digest('hex').toUpperCase();
const prefix='finance-v17/src/finance_v2/web/';
const allowed=['app.js','completion.js','index.html','open-finance.css','open-finance.js','revenues.js','privacy.css','privacy.js'].map(f=>prefix+f).sort();
const changed=git('diff','--cached','--name-only',baseline,'--','finance-v17').toString().trim().split('\n').filter(Boolean).sort();
assert.deepEqual(changed,allowed,'Only the eight frontend files may differ');
git('diff','--cached','--check');
const lock=JSON.parse(git('show',':docs/open-finance/BUILD_LOCK.json'));
const protectedFiles={};
for(const [file,expected] of Object.entries(lock.protected_files)){
  assert.equal(hash(git('show',baseline+':'+file)),expected);
  assert.equal(hash(git('show',':'+file)),expected);
  assert.equal(hash(fs.readFileSync(path.join(root,file))),expected);
  protectedFiles[file]=expected;
}
const product=git('ls-files','--','finance-v17').toString().trim().split('\n');
const canonicalProduct=Object.fromEntries(product.map(f=>[f,hash(git('show',':'+f))]));
assert.match(git('show',':finance-v17/config.yaml').toString(),/open_finance_auto_sync_enabled: false/);
const report={baseline,product_files:product.length,allowed_product_changes:changed,canonical_staged_product_sha256:canonicalProduct,protected_files:protectedFiles,protected_count:Object.keys(protectedFiles).length,backend_api_migrations_auth_scheduler_and_configuration:'UNCHANGED',diff_check:'PASS',scope:'No database access or migration execution; staged Git objects plus working protected-file hashes only'};
if(process.argv[2]){assert(path.isAbsolute(process.argv[2]));assert(!fs.existsSync(process.argv[2]));fs.writeFileSync(process.argv[2],JSON.stringify(report,null,2)+'\n')}
console.log(JSON.stringify({status:'PASS',product_files:product.length,protected:Object.keys(protectedFiles).length,frontend_changes:changed.length}));
