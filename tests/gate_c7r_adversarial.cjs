// Actual frontend and loopback API; only failure/order/sync transport is simulated.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve}};
async function main(){
 const [origin,out]=process.argv.slice(2),results=[],allRequests=[];let external=0;
 const timeout=Number(process.env.C7R_BROWSER_TIMEOUT||5000);assert([5000,60000].includes(timeout));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 async function scenario(name,body,{ignoreAbort=true}={}){
  const context=await browser.newContext({viewport:{width:1440,height:1000}});context.setDefaultTimeout(timeout);
  if(ignoreAbort)await context.addInitScript(()=>{const native=window.fetch.bind(window);window.fetch=(input,options={})=>native(input,{...options,signal:undefined})});
  const handlers=[],pending=[],errors=[],requests=[];let page;
  await context.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());if(url.origin!==origin){external++;return route.abort()}
   if(url.pathname.startsWith('/api/v2/')){
    const row={path:url.pathname,query:Object.fromEntries(url.searchParams),method:req.method()};requests.push(row);allRequests.push(row);
    const index=handlers.findIndex(h=>h.match(url,req));
    if(index>=0){const h=handlers.splice(index,1)[0];return h.handle(route)}
    assert.equal(req.method(),'GET','UNEXPECTED_REAL_WRITE');
   }
   return route.continue();
  });
  const hold=(pathname,{status=null,abort=null,syntheticWrite=false,match=null}={})=>{
   const held=deferred(),gate=deferred(),done=deferred();pending.push(gate);
   handlers.push({match:match||((u)=>u.pathname===pathname),handle:async route=>{
    try{const response=syntheticWrite?null:await route.fetch();held.resolve();await gate.promise;
     if(abort)await route.abort(abort);else if(syntheticWrite)await route.fulfill({json:{run:{state:'SUCCEEDED'}}});
     else if(status!==null)await route.fulfill({status,json:{error:{code:status===401?'UNAUTHORIZED':'STORAGE_UNAVAILABLE'}}});
     else await route.fulfill({response});
    }catch(e){if(ignoreAbort)throw e;/* Native browser cancellation has already discarded this request. */}
    finally{done.resolve()}
   }});
   return{held:held.promise,release:async()=>{gate.resolve();await done.promise;await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))}};
  };
  const observe=()=>page.evaluate(()=>({hash:location.hash,heading:document.querySelector('#view h1')?.textContent,ofHostPresent:!!document.querySelector('.of-screen'),selected:document.querySelector('[data-of-tab][aria-selected=true]')?.dataset.ofTab,status:document.querySelector('#status')?.textContent,dialogs:document.querySelectorAll('dialog').length}));
  const navigate=hash=>page.evaluate(h=>location.hash=h,'#'+hash);
  const overview=async()=>{await page.locator('#of-tab-overview').waitFor();await page.locator('#of-tab-overview').click();await page.locator('#of-panel-overview .of-resource-card').first().waitFor()};
  const assertOF=async()=>{const o=await observe();assert.equal(o.hash,'#open-finance');assert.equal(o.heading,'Open Finance');assert(o.ofHostPresent);assert(!o.status);return o};
  try{
   page=await context.newPage();page.on('pageerror',e=>errors.push(e.name));
   await page.goto(origin+'/app/unlock');await page.locator('[name=token]').fill('synthetic-owner-only-token');await page.locator('button').click();await page.waitForURL('**/app/');
   await navigate('open-finance');await overview();
   await body({page,requests,handlers,hold,navigate,overview,assertOF,observe});
   assert.deepEqual(errors,[]);results.push({name,status:'PASS',final:await observe(),requests:requests.length});
  }catch(e){results.push({name,status:'FAIL',failure:{type:e.name,message:String(e.message).slice(0,1200)},final:page?await observe().catch(()=>null):null,errors});}
  finally{for(const gate of pending)gate.resolve();await context.close()}
  fs.writeFileSync(path.join(out,'ADVERSARIAL_PROGRESS.json'),JSON.stringify({results},null,2));
 }
 try{
  for(const [name,hash,endpoint] of [['catalogs','catalogs','catalogs'],['cards','cards','cards'],['invoices','invoices','invoices'],['dashboard','dashboard','dashboard'],['revenues','revenues','revenues'],['expenses','expenses','expenses'],['recurring','recurring','recurring-series'],['installments','installments','installment-series']]){
   await scenario('late_'+name+'_cannot_replace_open_finance',async({hold,navigate,overview,assertOF})=>{const h=hold('/api/v2/'+endpoint);await navigate(hash);await h.held;await navigate('open-finance');await overview();await h.release();await assertOF()});
  }
  await scenario('rapid_multiple_routes_reverse_response_order',async({hold,navigate,overview,assertOF})=>{const a=hold('/api/v2/cards');await navigate('cards');await a.held;const b=hold('/api/v2/invoices');await navigate('invoices');await b.held;await navigate('open-finance');await overview();await b.release();await assertOF();await a.release();await assertOF()});
  for(const [name,options]of [['old_http_503',{status:503}],['old_http_401_no_redirect',{status:401}],['old_timeout',{abort:'timedout'}]])
   await scenario(name,async({hold,navigate,overview,assertOF})=>{const h=hold('/api/v2/cards',options);await navigate('cards');await h.held;await navigate('open-finance');await overview();await h.release();await assertOF()});
  await scenario('native_abort_read_does_not_leave_loading',async({hold,navigate,overview,assertOF})=>{const h=hold('/api/v2/cards');await navigate('cards');await h.held;await navigate('open-finance');await overview();await h.release();await assertOF()},{ignoreAbort:false});
  await scenario('active_error_clears_loading_and_reentry_recovers',async({page,hold,navigate,overview,assertOF})=>{const h=hold('/api/v2/cards',{status:503});await navigate('cards');await h.held;await h.release();await page.locator('#status .attention').waitFor();assert.equal(await page.locator('[data-navigation-loading]').count(),0);await navigate('open-finance');await overview();await assertOF()});
  for(const [tab,resource,selector]of [['assets','investments','.of-resource-card'],['cards','accounts','.of-resource-card'],['credit','loans','.of-resource-card'],['connections','item','.of-resource-card'],['flow',null,'.of-results .of-table']]){
   await scenario('return_to_selected_'+tab+'_loads_once',async({page,requests,navigate,assertOF})=>{await page.locator('#of-tab-'+tab).click();await page.locator('#of-panel-'+tab+' '+selector).first().waitFor();await navigate('catalogs');await page.locator('#view h1').filter({hasText:'Cadastros'}).waitFor();const offset=requests.length;await navigate('open-finance');await page.locator('#of-panel-'+tab+' '+selector).first().waitFor();assert.equal(await page.locator('#of-tab-'+tab).getAttribute('aria-selected'),'true');assert.equal(requests.slice(offset).filter(x=>resource?x.path==='/api/v2/open-finance/domain'&&x.query.resource===resource:x.path==='/api/v2/open-finance/transactions').length,1);await assertOF()});
  }
  await scenario('incomplete_assets_load_reentry_ignores_old_result',async({page,hold,navigate,assertOF})=>{const h=hold('/api/v2/open-finance/domain',{match:u=>u.pathname==='/api/v2/open-finance/domain'&&u.searchParams.get('resource')==='investments'});await page.locator('#of-tab-assets').click();await h.held;await navigate('catalogs');await page.locator('#view h1').filter({hasText:'Cadastros'}).waitFor();await navigate('open-finance');await page.locator('#of-panel-assets .of-resource-card').first().waitFor();await h.release();assert.equal(await page.locator('#of-tab-assets').getAttribute('aria-selected'),'true');await assertOF()});
  await scenario('empty_assets_are_explicit_and_reentry_loads',async({page,handlers,navigate,assertOF})=>{handlers.push({match:u=>u.pathname==='/api/v2/open-finance/domain'&&u.searchParams.get('resource')==='investments',handle:route=>route.fulfill({json:{resource:'investments',items:[],total:0,page:1,has_more:false,checkpoints:[{state:'EMPTY',record_count:0,page_count:1}],consent_diagnostics:[]}})});await page.locator('#of-tab-assets').click();await page.locator('#of-panel-assets .empty').waitFor();assert.match(await page.locator('#of-panel-assets').innerText(),/Consulta concluída sem registros/);await navigate('catalogs');await page.locator('#view h1').filter({hasText:'Cadastros'}).waitFor();await navigate('open-finance');await page.locator('#of-panel-assets .of-resource-card').first().waitFor();await assertOF()});
  await scenario('active_assets_error_reentry_recovers',async({page,hold,navigate,assertOF})=>{const h=hold('/api/v2/open-finance/domain',{status:503,match:u=>u.pathname==='/api/v2/open-finance/domain'&&u.searchParams.get('resource')==='investments'});await page.locator('#of-tab-assets').click();await h.held;await h.release();await page.locator('#of-panel-assets [role=alert]').waitFor();await navigate('catalogs');await page.locator('#view h1').filter({hasText:'Cadastros'}).waitFor();await navigate('open-finance');await page.locator('#of-panel-assets .of-resource-card').first().waitFor();await assertOF()});
  await scenario('same_panel_out_of_order_query_preserves_latest_resource',async({page,hold,assertOF})=>{const h=hold('/api/v2/open-finance/domain',{match:u=>u.pathname==='/api/v2/open-finance/domain'&&u.searchParams.get('resource')==='investments'});await page.locator('#of-tab-assets').click();await h.held;await page.locator('#of-panel-assets select[name=resource]').selectOption('loans');await page.locator('#of-panel-assets button[type=submit]').click();await page.locator('#of-panel-assets [data-domain-kind=CREDIT_CONTRACT]').first().waitFor();await h.release();assert.equal(await page.locator('#of-panel-assets [data-domain-kind=INVESTMENT_POSITION]').count(),0);await assertOF()});
  await scenario('navigation_during_synthetic_sync_does_not_redirect_or_refresh',async({page,hold,navigate,overview,assertOF})=>{await page.locator('#of-tab-connections').click();const h=hold('/api/v2/open-finance/domain-sync',{syntheticWrite:true});page.once('dialog',dialog=>dialog.accept());await page.locator('[data-domain-sync]').first().click();await h.held;await navigate('catalogs');await page.locator('#view h1').filter({hasText:'Cadastros'}).waitFor();await navigate('open-finance');await overview();await h.release();await assertOF()});
  await scenario('navigation_closes_old_dialog_without_old_cancel_redirect',async({page,navigate,overview,assertOF})=>{await navigate('revenue-new');await page.locator('dialog[open]').waitFor();await navigate('open-finance');await overview();assert.equal(await page.locator('dialog').count(),0);await assertOF()});
  await scenario('browser_reload_recovers_current_data_and_private_preference',async({page,navigate,overview,assertOF})=>{await page.locator('#of-tab-assets').click();await page.locator('#of-panel-assets .of-resource-card').first().waitFor();await page.reload();await overview();await assertOF();assert.equal(await page.locator('html').getAttribute('data-money-privacy'),'hidden');assert((await page.locator('#of-panel-overview [data-private-financial]').allTextContents()).every(x=>x==='R$ ••••••'))});
 }finally{await browser.close()}
 const result={status:results.every(x=>x.status==='PASS')?'PASS':'FAIL',pass:results.filter(x=>x.status==='PASS').length,fail:results.filter(x=>x.status==='FAIL').length,tests:results,requests:allRequests,external_requests:external,real_bank_requests:0,synthetic_sync_transport_only:true,wait_limit_ms:timeout};
 fs.writeFileSync(path.join(out,'ADVERSARIAL_RESULTS.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({status:result.status,pass:result.pass,fail:result.fail,external_requests:external,failures:results.filter(x=>x.status==='FAIL')}));process.exitCode=result.fail?1:0;
}
main().catch(e=>{console.error(e.stack);process.exitCode=1});
