// Execute the actual validator with read-only captured Git responses.
// Negative controls mutate only in-memory responses, never product files/index.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),cp=require('node:child_process'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..'),source=fs.readFileSync(path.join(__dirname,'verify_phase_a.cjs'),'utf8'),cache=new Map();
function run({gitChange,workingChange}={}){
  const child={execFileSync(exe,args){
    assert.equal(exe,'git');const key=JSON.stringify(args);
    if(!cache.has(key))cache.set(key,cp.execFileSync(exe,args,{cwd:root,maxBuffer:20*1024*1024}));
    const original=cache.get(key);return gitChange?gitChange(args,original):original;
  }};
  const file={readFileSync(file,...args){const original=fs.readFileSync(file,...args);return workingChange?workingChange(file,original):original;}};
  vm.runInNewContext(source,{require(name){if(name==='node:child_process')return child;if(name==='node:fs')return file;return require(name);},__dirname,process:{argv:['node','validator']},console:{log(){}},Buffer},{timeout:30000});
}
test('actual staged validator accepts exact authorized release',()=>run());
test('validator rejects non-version configuration edits',()=>assert.throws(()=>run({gitChange:(a,b)=>a[0]==='show'&&a[1]===':finance-v17/config.yaml'?Buffer.from(b.toString().replace('open_finance_auto_sync_enabled: false','open_finance_auto_sync_enabled: true')):b}),/version-only change/));
test('validator rejects Docker base edits',()=>assert.throws(()=>run({gitChange:(a,b)=>a[0]==='show'&&a[1]===':finance-v17/Dockerfile'?Buffer.from(b.toString().replace('python:3.12.7','python:3.12.8')):b}),/version-only change/));
test('validator rejects additional functional changes',()=>assert.throws(()=>run({gitChange:(a,b)=>a[0]==='show'&&a[1]===':finance-v17/src/finance_v2/api.py'?Buffer.concat([b,Buffer.from('\n# alteration\n')]):b}),/Preserve exact Phase A product bytes/));
test('validator rejects altered protected working bytes',()=>assert.throws(()=>run({workingChange:(f,b)=>String(f).endsWith('run.sh')?Buffer.concat([b,Buffer.from('\n')]):b}),/Expected values to be strictly equal/));
test('validator rejects modified release documentation',()=>assert.throws(()=>run({gitChange:(a,b)=>a[0]==='show'&&a[1]===':finance-v17/DOCS.md'?Buffer.concat([b,Buffer.from('\n')]):b}),/Exact authorized release documentation/));
test('validator rejects tampered independent manifest',()=>assert.throws(()=>run({gitChange:(a,b)=>a[0]==='show'&&a[1]===':docs/open-finance/RELEASE_0.1.22_MANIFEST.json'?Buffer.from(b.toString().replace('0.1.22-open-finance.1','0.1.99-open-finance.1')):b}),/Exact independent release manifest/));
