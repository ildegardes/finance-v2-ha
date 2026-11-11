const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const {chromium}=require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const web=path.resolve('finance-v17/src/finance_v2/web');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  await page.route('http://synthetic.local/**',async route=>{
   const pathname=new URL(route.request().url()).pathname;
   if(pathname==='/')return route.fulfill({contentType:'text/html',body:'<!doctype html><html><head><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/open-finance.css"></head><body><button id="money-privacy-toggle"></button><section id="host"><section id="of-panel-overview"></section></section></body></html>'});
   const filename=path.join(web,path.basename(pathname));if(!fs.existsSync(filename))return route.fulfill({status:404});
   return route.fulfill({contentType:pathname.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync(filename,'utf8')});
  });
  await page.goto('http://synthetic.local/');
  await page.evaluate(async()=>{
   const {installPrivacy}=await import('/privacy.js'); installPrivacy();
   const {mountAnalyticsOverview}=await import('/open-finance.js');
   window.testCalls=[]; const mock={positions:{accounts:{value:'12.34',coverage_state:'PARTIAL',items:[{institution:'Teste',name:'Conta',value:'12.34',reference_date:null}]},investments:{value:null,coverage_state:'NOT_ESTABLISHED',items:[]}},flow:{BANK:{incoming:'2.00',outgoing:'3.00'}},series:[{product:'BANK',date:'2026-10-01',direction:'outgoing',value:'3.00'}],category_ranking:{BANK:[{name:'Categoria sintética',value:'3.00'}]}};
   const esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
   mountAnalyticsOverview({host:document.querySelector('#host'),catalog:{connections:[]},state:{start:'2026-10-01',end:'2026-10-31'},esc,api:async url=>{window.testCalls.push(url);return mock}});
  });
  await page.getByText('Saldo informado das contas').waitFor();
  assert.equal(await page.locator('.of-metric').count(),4);
  assert.equal(await page.locator('.of-series li').count(),1);
  assert.equal(await page.locator('.of-series strong').innerText(),'R$ ••••••');
  assert.equal(await page.locator('.of-metric').first().locator('strong').innerText(),'R$ ••••••');
  assert.equal(await page.locator('.of-metric').nth(1).locator('strong').innerText(),'Indisponível');
  await page.locator('#money-privacy-toggle').click();
  assert.equal(await page.locator('.of-metric').first().locator('strong').innerText(),'R$ 12,34');
  await page.locator('input[name=start]').fill('2026-09-01');await page.getByRole('button',{name:'Aplicar'}).click();
  await page.waitForFunction(()=>window.testCalls.length===2);
  assert.match(await page.evaluate(()=>window.testCalls[1]),/start=2026-09-01/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.evaluate(async()=>{const {mountAnalyticsOverview}=await import('/open-finance.js');const host=document.createElement('section');host.id='history-host';host.innerHTML='<section id="of-panel-overview"></section>';document.body.append(host);window.historyCalls=[];const state={start:'2026-10-01',end:'2026-10-31',currency:'BRL',connection_id:'archived',history:'1'};mountAnalyticsOverview({host,catalog:{connections:[{id:'archived',institution:'Histórica',enabled:false,historical:true}]},state,esc:String,api:async u=>{window.historyCalls.push(u);return {positions:{accounts:{value:null,coverage_state:'PARTIAL',items:[]},investments:{value:null,coverage_state:'PARTIAL',items:[]}},flow:{BANK:{incoming:'0',outgoing:'0'}},series:[],category_ranking:{BANK:[]},coverage:[]}}})});
  await page.waitForFunction(()=>window.historyCalls?.length>0);assert(!new URL('http://synthetic.local/'+await page.evaluate(()=>window.historyCalls[0])).searchParams.has('connection_id'));assert.equal(await page.locator('#history-host select[name=connection_id]').inputValue(),'');
  process.stdout.write('PASS: overview, synthetic data, filters, privacy, 390px\n');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
