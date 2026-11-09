// Actual candidate DTOs, real browser, synthetic API responses; zero external connections.
const {test,before,after,beforeEach,afterEach}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const root=path.resolve(__dirname,'../..'),web=path.resolve(__dirname,'../finance-v17/src/finance_v2/web');
const snapshot=JSON.parse(fs.readFileSync(process.env.GATE_B_UI_FIXTURE||path.join(root,'evidence/DOMAIN_UI_FIXTURE.json'),'utf8'));
let server,browser,origin,context,page,requests,errors;
function dto(url){
 const source=structuredClone(snapshot.responses[url.searchParams.get('resource')||'accounts']);
 let items=source.items;
 for(const key of ['connection_id','parent_id'])if(url.searchParams.has(key))items=items.filter(r=>r.identity[key]===url.searchParams.get(key));
 for(const key of ['type','currency'])if(url.searchParams.has(key))items=items.filter(r=>r.fields.some(f=>f.key===(key==='currency'?'currencyCode':'type')&&f.value===url.searchParams.get(key)));
 const current=+(url.searchParams.get('page')||1),size=+(url.searchParams.get('page_size')||25);
 return {...source,total:items.length,items:items.slice((current-1)*size,current*size),page:current,page_size:size,has_more:current*size<items.length};
}
before(async()=>{
 server=http.createServer((req,res)=>{const p=new URL(req.url,'http://localhost').pathname,file=path.resolve(web,p==='/app/'?'index.html':p.replace('/app/assets/',''));if(!file.startsWith(web+path.sep)||!fs.existsSync(file)){res.writeHead(404);return res.end()}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file))});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin='http://127.0.0.1:'+server.address().port;
 browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
});
after(async()=>{await browser?.close();await new Promise(resolve=>server?.close(resolve))});
beforeEach(async()=>{
 requests=[];errors=[];context=await browser.newContext({viewport:{width:1280,height:960}});context.setDefaultTimeout(5000);
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());
  if(url.origin!==origin){errors.push('EXTERNAL_NETWORK_ATTEMPT');return route.abort()}
  if(!url.pathname.startsWith('/api/v2/'))return route.continue();
  requests.push({method:req.method(),path:url.pathname,query:Object.fromEntries(url.searchParams)});
  if(req.method()!=='GET'){errors.push('UNAUTHORIZED_WRITE');return route.abort()}
  const p=url.pathname.replace('/api/v2','');
  const response=p==='/context'?{system_date:'2026-10-29',csrf_token:'synthetic'}:p==='/catalogs'?{accounts:[],cards:[],tags:[],categories:[]}:
   p==='/open-finance/catalogs'?snapshot.catalog:p==='/open-finance/domain'?dto(url):p==='/open-finance/transactions'?{items:[],has_more:false,query_meta:{counts:{after_f04:{state:'EXACT',value:0}},query_completeness:'COMPLETE',coverage:{direction:{state:'COMPLETE'}},warnings:[]}}:null;
  if(!response){errors.push('UNEXPECTED_API:'+p);return route.abort()}
  return route.fulfill({json:response});
 });
 page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
 await page.goto(origin+'/app/#open-finance');await page.locator('#of-panel-overview .of-resource-card').first().waitFor();
});
afterEach(async()=>{await context.close();assert.deepEqual(errors,[]);assert(!requests.some(r=>r.method!=='GET'))});
async function select(area,resource){
 await page.getByRole('tab',{name:{overview:'Visão geral',cards:'Cartões',assets:'Ativos',credit:'Crédito',connections:'Conexões'}[area],exact:true}).click();
 const form=page.locator('#of-panel-'+area+' .of-resource-filter');await form.locator('[name=resource]').selectOption(resource);await form.locator('[type=submit]').click();await page.locator('#of-panel-'+area+' .of-resource-card').first().waitFor();
 return page.locator('#of-panel-'+area);
}
test('all domains use typed components, private by default, no JSON dump or identifiers',async()=>{
 for(const [resource,area]of Object.entries({accounts:'overview',transactions:'cards',bills:'cards',investments:'assets',investment_transactions:'assets',loans:'credit',statements:'overview',item:'connections',consents:'connections',resources:'connections'})){
  const panel=await select(area,resource);const text=await panel.innerText();
  assert.doesNotMatch(text,/item-test|account-BANK|account-CREDIT|consent-test|private-signed-url|payload_json/);
  assert.equal(await panel.locator('.of-resource-card [data-domain-kind]').count(),0); // cards themselves carry their kind
  assert(await panel.locator('[data-domain-kind]').count()>0);
  if(await panel.locator('[data-private-financial]').count())assert.equal(await panel.locator('[data-private-financial]').first().innerText(),'R$ ••••••');
 }
});
test('17 positions show stale cache, quantities/rates hidden and navigation scopes movements',async()=>{
 const panel=await select('assets','investments');assert.equal(await panel.locator('.of-resource-card').count(),17);
 assert.match(await panel.innerText(),/Desatualização informada na coleta de origem deste conteúdo/);assert.match(await panel.innerText(),/Execução parcial/);
 await page.locator('#money-privacy-toggle').click();assert.match(await panel.innerText(),/2,123456/);assert.match(await panel.innerText(),/R\$ 1\.000,00/);
 await page.locator('#money-privacy-toggle').click();await panel.getByRole('button',{name:'Ver Movimentos de investimentos'}).first().click();
 await panel.locator('[data-domain-kind=INVESTMENT_MOVEMENT]').waitFor();
 const last=requests.filter(r=>r.path.endsWith('/domain')).at(-1);assert.equal(last.query.parent_id,'position-0');assert.equal(last.query.connection_id,'bank-test');assert.equal(last.query.resource,'investment_transactions');
 assert.equal(await panel.locator('[data-private-financial]').first().innerText(),'R$ ••••••');
});
test('cards navigate bills, exact relationships distinguish pending without bill',async()=>{
 const panel=await select('cards','accounts');assert.equal(await panel.locator('[data-domain-kind=CREDIT_CARD]').count(),1);
 await panel.getByRole('button',{name:'Ver Faturas e pagamentos registrados'}).click();await panel.locator('[data-domain-kind=CREDIT_BILL]').waitFor();
 assert.equal(requests.filter(r=>r.path.endsWith('/domain')).at(-1).query.parent_id,'account-CREDIT');
 await select('cards','transactions');assert.match(await panel.innerText(),/Vínculo com fatura comprovado/);assert.match(await panel.innerText(),/Sem vínculo de fatura informado/);
});
test('statements are metadata only; loan and consent fields use provider data without new writes',async()=>{
 const statements=await select('overview','statements');assert.match(await statements.innerText(),/download de documento não habilitado/);assert.equal(await statements.locator('a[download]').count(),0);
 const credit=await select('credit','loans');await page.locator('#money-privacy-toggle').click();assert.match(await credit.innerText(),/R\$ 500,00/);assert.match(await credit.innerText(),/2 \(unidade informada pelo provedor\)/);
 const connection=await select('connections','consents');assert.match(await connection.innerText(),/Associação validada na última consulta/);assert.match(await connection.innerText(),/não comprova autorização atual/);
});
test('empty, unsupported, failed, interrupted and unqueried collections remain distinguishable',async()=>{
 const cases=[['EMPTY','Consulta concluída sem registros'],['NOT_AVAILABLE','Recurso não disponível'],['FAILED','Leitura falhou'],['INTERRUPTED','Leitura interrompida'],['NOT_QUERIED','Consulta não realizada']];
 for(const [state,text]of cases){
  await page.route('**/api/v2/open-finance/domain?*',route=>route.fulfill({json:{...snapshot.responses.statements,items:[],total:0,checkpoints:state==='NOT_QUERIED'?[]:[{state,record_count:0,page_count:1}]}}));
  const form=page.locator('#of-panel-overview form');await form.locator('[name=resource]').selectOption('statements');await form.locator('[type=submit]').click();await page.getByText(text,{exact:false}).first().waitFor();
 }
});
test('mobile and desktop domain components remain keyboard accessible without overflow',async()=>{
 const panel=await select('assets','investments');for(const width of [360,390,768,1440]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'overflow '+width)}
 const button=panel.getByRole('button',{name:'Ver Movimentos de investimentos'}).first();await button.focus();assert(await button.evaluate(e=>document.activeElement===e));
 if(process.env.GATE_B_UI_SCREENSHOTS){fs.mkdirSync(process.env.GATE_B_UI_SCREENSHOTS,{recursive:true});await page.setViewportSize({width:390,height:844});await page.evaluate(()=>window.scrollTo(0,0));await page.waitForFunction(()=>document.querySelector('nav').getBoundingClientRect().right<=0);await page.screenshot({path:path.join(process.env.GATE_B_UI_SCREENSHOTS,'assets-mobile-hidden.png')});await page.setViewportSize({width:1440,height:1000});await page.waitForFunction(()=>document.querySelector('nav').getBoundingClientRect().left>=0);await page.screenshot({path:path.join(process.env.GATE_B_UI_SCREENSHOTS,'assets-desktop-hidden.png')})}
});
test('adversarial provider text is escaped and delayed sensitive values remain masked',async()=>{
 const response=structuredClone(snapshot.responses.investments);response.items=[response.items[0]];response.total=1;
 response.items[0].name='<img src=x onerror=alert(1)>';
 response.items[0].fields.push({key:'description',label:'<script>bad</script>',state:'VALUE',kind:'TEXT',value:'<svg onload=alert(1)>'});
 await page.route('**/api/v2/open-finance/domain?*',async route=>{await new Promise(r=>setTimeout(r,75));return route.fulfill({json:response})});
 const panel=await select('assets','investments');await page.evaluate(()=>new Promise(requestAnimationFrame));
 assert.equal(await panel.locator('img,script,svg[onload]').count(),0);assert.match(await panel.innerText(),/<img src=x/);
 assert.equal(await panel.locator('[data-private-financial]').first().innerText(),'R$ ••••••');
});

// C1: timestamps describe their actual provenance, never the mutable Item as history.
test('C1 temporal provenance is explicit and never claims current data from recent collection',async()=>{
 const panel=await select('assets','investment_transactions');
 await panel.locator('details').filter({has:page.locator('summary', {hasText:'Proveniência'})}).first().locator('summary').click();
 assert.match(await panel.innerText(),/Data financeira informada/);
 assert.match(await panel.innerText(),/20\/10\/2026/);
 assert.match(await panel.innerText(),/Coleta da revisão/);
 assert.match(await panel.innerText(),/Atualização deste registro no provedor/);
 assert.match(await panel.innerText(),/Sincronização atual \(contexto separado\)/);
 assert.match(await panel.innerText(),/Não estabelecido; coleta recente não comprova data financeira recente/);
 assert.doesNotMatch(await panel.innerText(),/Atualizado na última execução do provedor/);
});
