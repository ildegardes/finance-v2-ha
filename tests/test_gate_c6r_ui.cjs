// Real candidate browser modules; synthetic read responses, no external requests.
const {test,before,after,beforeEach,afterEach}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const web=path.resolve(__dirname,'../finance-v17/src/finance_v2/web');
const snapshot=JSON.parse(fs.readFileSync(process.env.GATE_B_UI_FIXTURE,'utf8'));
let server,browser,origin,page,context,requests,errors,mode,latencies;
function analytics(url){
 const page=+(url.searchParams.get('page')||1),total=mode==='volume'?5000:mode==='empty'?0:1;
 const items=Array.from({length:Math.min(25,Math.max(0,total-(page-1)*25))},(_,i)=>({date:'2026-10-29',description:'Synthetic row '+((page-1)*25+i),institution:'Synthetic',account_name:'Synthetic',category:{name:'Synthetic'},direction:'outgoing',status:'POSTED',product:'BANK',amount:'10.00'}));
 return {positions:{accounts:{value:'10',coverage_state:'COMPLETE',items:[]},investments:{value:null,coverage_state:'PARTIAL',items:[],by_class:[]}},flow:{BANK:{incoming:'0',outgoing:'10'},CREDIT:{incoming:'0',outgoing:'0'}},category_ranking:{BANK:[]},series:[],coverage:[{resource:'transactions',state:'AVAILABLE'}],items,total,page,has_more:page*25<total};
}
function dto(url){
 const source=structuredClone(snapshot.responses[url.searchParams.get('resource')||'accounts']);
 if(mode==='empty'){source.items=[];source.total=0;source.has_more=false;source.checkpoints=source.checkpoints.map(x=>({...x,state:'EMPTY',record_count:0}));}
 if(mode==='volume'){
  const template=source.items[0];assert(template);
  const total=5000,page=+(url.searchParams.get('page')||1);
  source.items=Array.from({length:25},(_,n)=>({...structuredClone(template),name:'Synthetic row '+((page-1)*25+n),identity:{...template.identity,external_id:'synthetic-row-'+((page-1)*25+n)}}));
  source.total=total;source.page=page;source.has_more=page*25<total;
 }
 if(mode==='running')for(const row of source.items)row.temporal.current_sync={state:'RUNNING'};
 return source;
}
before(async()=>{
 server=http.createServer((req,res)=>{const p=new URL(req.url,'http://localhost').pathname,f=path.resolve(web,p==='/app/'?'index.html':p.replace('/app/assets/',''));if(!f.startsWith(web+path.sep)||!fs.existsSync(f)){res.writeHead(404);return res.end()}res.setHeader('Content-Type',f.endsWith('.js')?'text/javascript':f.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(f))});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));origin='http://127.0.0.1:'+server.address().port;
 browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
});
after(async()=>{await browser.close();await new Promise(r=>server.close(r))});
beforeEach(async()=>{
 mode='normal';requests=[];errors=[];latencies=[];context=await browser.newContext();context.setDefaultTimeout(5000);
 await context.route('**/*',async route=>{
  const req=route.request(),u=new URL(req.url());assert.equal(u.origin,origin);
  if(!u.pathname.startsWith('/api/v2/'))return route.continue();
  assert.equal(req.method(),'GET');requests.push(u.pathname);const start=Date.now(),p=u.pathname.replace('/api/v2','');
  let data=p==='/context'?{system_date:'2026-10-29',csrf_token:'synthetic'}:p==='/catalogs'?{accounts:[],cards:[],tags:[],categories:[]}:p==='/open-finance/catalogs'?snapshot.catalog:p==='/open-finance/domain'?dto(u):p==='/open-finance/analytics'?analytics(u):p==='/open-finance/transactions'?{items:[],has_more:false,query_meta:{counts:{after_f04:{state:'EXACT',value:0}},query_completeness:'COMPLETE',coverage:{direction:{state:'COMPLETE'}},warnings:[]}}:null;
  assert(data,'UNEXPECTED_ROUTE');if(mode==='running'&&p==='/open-finance/analytics')await new Promise(r=>setTimeout(r,150));
  if(mode==='error'&&p==='/open-finance/analytics')await route.fulfill({status:503,json:{error:{code:'STORAGE_UNAVAILABLE'}}});else await route.fulfill({json:data});
  latencies.push({path:u.pathname,ms:Date.now()-start});
 });
 page=await context.newPage();page.on('pageerror',e=>errors.push(e.name));await page.goto(origin+'/app/#open-finance');await visible();
});
afterEach(async(t)=>{t.diagnostic(JSON.stringify({case:t.name,latencies,wait_limit_ms:5000,real_bank_requests:0}));await context.close();assert.deepEqual(errors,[]);assert(!requests.some(x=>x.includes('sync')))});
async function visible(){await page.locator('#of-panel-overview .of-metric').first().waitFor();assert.equal(await page.locator('#view h1').innerText(),'Open Finance')}
async function returnToOF(){await page.goto(origin+'/app/#catalogs');await page.locator('#view h1').filter({hasText:'Cadastros'}).waitFor();await page.goto(origin+'/app/#open-finance');}

test('C6R repeated navigation preserves current OF view',async()=>{for(let i=0;i<8;i++){await returnToOF();await visible()}});
test('C6R return after completed synthetic collection remains read-only',async()=>{await returnToOF();await visible();assert(requests.includes('/api/v2/open-finance/analytics'))});
test('C6R return while synthetic collection is running does not block navigation',async()=>{mode='running';await returnToOF();await visible();assert(latencies.some(x=>x.ms>=140))});
test('C6R return after backend error recovers without changing scope guards',async()=>{mode='error';await returnToOF();await page.locator('#of-panel-overview [role=alert]').waitFor();mode='normal';await returnToOF();await visible()});
test('C6R large collection remains paginated and private',async()=>{mode='volume';await returnToOF();await visible();await page.getByRole('tab',{name:'Movimentações'}).click();await page.locator('#of-panel-flow .of-flow-item').first().waitFor();assert.equal(await page.locator('#of-panel-flow .of-flow-item').count(),25);await page.locator('#of-panel-flow [data-flow-next]').click();await page.getByText('Synthetic row 25',{exact:true}).waitFor();assert((await page.locator('#of-panel-flow [data-private-financial]').allTextContents()).every(s=>s==='R$ ••••••'))});
test('C6R empty collection is explicit rather than a rendering timeout',async()=>{mode='empty';await returnToOF();await visible();await page.getByRole('tab',{name:'Movimentações'}).click();await page.locator('#of-panel-flow .empty').waitFor();assert.equal(await page.locator('#of-panel-flow .of-flow-item').count(),0)});
test('C6R browser reload preserves hidden values and active OF route',async()=>{await page.reload();await visible();assert((await page.locator('#of-panel-overview [data-private-financial]').allTextContents()).every(s=>s==='R$ ••••••'))});
