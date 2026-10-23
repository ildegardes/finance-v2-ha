// Local reproducible evidence generator. Writes only to an explicit new evidence directory.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),cp=require('node:child_process');
const root=path.resolve(__dirname,'..'),target=process.argv[2];
if(!target||!path.isAbsolute(target)||fs.existsSync(target))throw Error('NEW_ABSOLUTE_EVIDENCE_DIRECTORY_REQUIRED');
fs.mkdirSync(target,{recursive:false});
const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex').toUpperCase();
function files(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(path.join(dir,e.name)):[path.join(dir,e.name)])}
const product=files(path.join(root,'finance-v17')),before=Object.fromEntries(product.map(f=>[path.relative(root,f).replaceAll('\\','/'),hash(f)]));
const result=cp.spawnSync(process.execPath,['--test','--test-reporter=tap','tests/phase_a_ui.cjs'],{cwd:root,env:{...process.env,FINANCE_UI_EVIDENCE:target},encoding:'utf8',timeout:180000,windowsHide:true});
fs.writeFileSync(path.join(target,'browser-tests.tap'),result.stdout||'');fs.writeFileSync(path.join(target,'browser-tests.stderr.txt'),result.stderr||'');
const changed=product.filter(f=>hash(f)!==before[path.relative(root,f).replaceAll('\\','/')]);
const report={exit_code:result.status,signal:result.signal,error:result.error?.message||null,pass:+(result.stdout?.match(/^# pass (\d+)/m)?.[1]||0),fail:+(result.stdout?.match(/^# fail (\d+)/m)?.[1]||0),skipped:+(result.stdout?.match(/^# skipped (\d+)/m)?.[1]||0),cancelled:+(result.stdout?.match(/^# cancelled (\d+)/m)?.[1]||0),product_files:before,product_changed_during_tests:changed.map(f=>path.relative(root,f)),scope:'Browser frontend with synthetic API interception; no database, migrations, HA, banks or production credentials. Not backend/Supervisor/ARM64 homologation.'};
fs.writeFileSync(path.join(target,'RESULTS.json'),JSON.stringify(report,null,2)+'\n');
const evidence=Object.fromEntries(files(target).map(f=>[path.relative(target,f).replaceAll('\\','/'),hash(f)]));
fs.writeFileSync(path.join(target,'EVIDENCE_MANIFEST.json'),JSON.stringify(evidence,null,2)+'\n');
console.log(JSON.stringify({evidence:target,...Object.fromEntries(Object.entries(report).filter(([k])=>k!=='product_files'))},null,2));
process.exitCode=result.status===0&&!changed.length?0:1;
