// Re-materialize ONLY unchanged baseline inputs. Never updates a hash or normalizes protected data.
const fs=require('node:fs'),cp=require('node:child_process'),crypto=require('node:crypto'),path=require('node:path');
const root=path.resolve(__dirname,'..'),git=(...args)=>cp.execFileSync('git',['-c','safe.directory='+root.replaceAll('\\','/'),...args],{cwd:root});
const lock=JSON.parse(fs.readFileSync(path.join(root,'docs/open-finance/BUILD_LOCK.json')));
const names=[...Object.keys(lock.protected_files),...git('ls-tree','-r','--name-only','HEAD','--','finance-v17/migrations').toString().trim().split('\n')];
const blobs=names.map(file=>{
  const baseline=git('show','HEAD:'+file),index=git('show',':'+file);
  if(!baseline.equals(index))throw Error('STAGED_BASELINE_INPUT_CHANGED '+file);
  const expected=lock.protected_files[file];
  if(expected&&crypto.createHash('sha256').update(baseline).digest('hex').toUpperCase()!==expected)throw Error('BASELINE_HASH_MISMATCH '+file);
  return [file,baseline];
});
for(const [file,bytes]of blobs)fs.writeFileSync(path.join(root,file),bytes);
console.log(JSON.stringify({materialized:blobs.length,source:'Exact HEAD Git blobs',protected:Object.keys(lock.protected_files).length,hashes_changed:false}));
