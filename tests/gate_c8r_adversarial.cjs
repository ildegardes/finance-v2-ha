// Independent C8 observations. The product is served unchanged from the sealed C7-R tree.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve}};
async function main(){
 const [origin,out]=process.argv.slice(2),results=[];let external=0,realWrites=0;const timeout=Number(process.env.C8R_BROWSER_TIMEOUT||5000);assert([5000,60000].includes(timeout));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 async function scenario(name,body,{ignoreAbort=true}={}){
  const context=await browser.newContext();context.setDefaultTimeout(timeout);
  if(ignoreAbort)await context.addInitScript(()=>{const native=window.fetch.bind(window);window.fetch=(i,o={})=>native(i,{...o,signal:undefined})});
  await context.addInitScript(()=>{window.__c8rPolls=[];const native=window.setInterval.bind(window);window.setInterval=(fn,delay,...args)=>delay===1500?(window.__c8rPolls.push(fn),-777):native(fn,delay,...args)});
  const handlers=[],gates=[],errors=[],requestFailures=[];let page,revenues,expenses;const observations={};
  await context.route('**/*',async route=>{
   const q=route.request(),u=new URL(q.url());if(u.origin!==origin){external++;return route.abort()}
   const index=handlers.findIndex(h=>h.match(u));if(index>=0){const h=handlers.splice(index,1)[0];return h.run(route,u)}
   if(u.pathname.startsWith('/api/')&&q.method()!=='GET'){realWrites++;return route.abort()}
   if(['/api/v2/revenues','/api/v2/expenses'].includes(u.pathname)&&!u.searchParams.has('search')){
    const response=await route.fetch();const d=await response.json();if(d.items?.length){if(u.pathname.endsWith('/revenues'))revenues=d;else expenses=d}return route.fulfill({response});
   }
   return route.continue();
  });
  const nav=hash=>page.evaluate(x=>location.hash=x,'#'+hash);
  const hold=(match,status=200,data=null,{abort=null}={})=>{
   const entered=deferred(),gate=deferred(),done=deferred();gates.push(gate);
   handlers.push({match,run:async route=>{try{const response=data?null:await route.fetch();entered.resolve();await gate.promise;if(abort)await route.abort(abort);else if(data)await route.fulfill({status,json:data});else if(status!==200)await route.fulfill({status,json:{error:{code:'STORAGE_UNAVAILABLE'}}});else await route.fulfill({response})}catch(e){if(ignoreAbort)throw e}finally{done.resolve()}}});
   return{entered:entered.promise,release:async(idle=true)=>{gate.resolve();await done.promise;if(idle)await page.waitForLoadState('networkidle');await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))}};
  };
  try{
   page=await context.newPage();page.on('pageerror',e=>errors.push(e.name));page.on('requestfailed',q=>requestFailures.push({path:new URL(q.url()).pathname,error:q.failure()?.errorText}));await page.goto(origin+'/app/unlock');await page.locator('[name=token]').fill('synthetic-owner-only-token');await page.locator('button').click();await page.waitForURL('**/app/');
   await nav('open-finance');await page.locator('#of-panel-overview .of-resource-card').first().waitFor();
   await body({page,nav,hold,handlers,observations,revenues:()=>revenues,expenses:()=>expenses,requestFailures});assert.deepEqual(errors,[]);
   results.push({name,status:'PASS',observations});
  }catch(error){results.push({name,status:'FAIL',error:{type:error.name,message:String(error.message).slice(0,1400)},observations,page_errors:errors,pathname:page?new URL(page.url()).pathname:null});}
  finally{for(const gate of gates)gate.resolve();await context.close()}
  fs.writeFileSync(path.join(out,'UI_REVIEW_PROGRESS.json'),JSON.stringify({results},null,2));
 }
 try{
  await scenario('old_cards_response_cannot_replace_current_open_finance',async({page,nav,hold,observations})=>{
   const h=hold(u=>u.pathname==='/api/v2/cards');await nav('cards');await h.entered;await nav('open-finance');await page.locator('#of-panel-overview .of-resource-card').first().waitFor();await h.release();observations.heading=await page.locator('#view h1').innerText();observations.hosts=await page.locator('.of-screen').count();assert.equal(observations.heading,'Open Finance');assert.equal(observations.hosts,1);
  });
  for(const lateError of [false,true])await scenario(lateError?'older_revenue_filter_error_does_not_pollute_newer_success':'older_revenue_filter_success_does_not_replace_newer_success',async({page,nav,hold,handlers,observations,revenues})=>{
   await nav('revenues');await page.waitForFunction(()=>document.querySelector('#rpage')?.textContent==='Página 1');
   assert(revenues()?.items.length,'SYNTHETIC_REVENUE_FIXTURE_REQUIRED');
   const row=mark=>{const d=structuredClone(revenues());for(const r of d.items)r.description=mark;return d};
   const h=hold(u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='old',lateError?503:200,lateError?{error:{code:'STORAGE_UNAVAILABLE'}}:row('OLD_SYNTHETIC_RESULT'));
   handlers.push({match:u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='new',run:route=>route.fulfill({json:row('NEW_SYNTHETIC_RESULT')})});
   await page.locator('#revenue-search').fill('old');await page.locator('#filter-revenue').click();await h.entered;
   await page.locator('#revenue-search').fill('new');await page.locator('#filter-revenue').click();await page.locator('#revenue-rows').getByText('NEW_SYNTHETIC_RESULT',{exact:true}).first().waitFor();
   observations.before_release={search:await page.locator('#revenue-search').inputValue(),new_result:await page.locator('#revenue-rows').getByText('NEW_SYNTHETIC_RESULT',{exact:true}).count()};
   await h.release();observations.after_release={search:await page.locator('#revenue-search').inputValue(),new_result:await page.locator('#revenue-rows').getByText('NEW_SYNTHETIC_RESULT',{exact:true}).count(),old_result:await page.locator('#revenue-rows').getByText('OLD_SYNTHETIC_RESULT',{exact:true}).count(),active_errors:await page.locator('#status .attention').count()};
   assert(observations.after_release.new_result>0,'LATEST_FILTER_RESULT_REPLACED_BY_OLDER_RESPONSE');assert.equal(observations.after_release.old_result,0);assert.equal(observations.after_release.active_errors,0,'OLD_FILTER_ERROR_POLLUTED_CURRENT_SUCCESS');
  });
  await scenario('older_recurring_tab_request_does_not_override_latest_selection',async({page,nav,hold,observations})=>{
   await nav('recurring');await page.locator('#view button[data-action=expense]').waitFor();
   const a=hold(u=>u.pathname==='/api/v2/recurring-series'),b=hold(u=>u.pathname==='/api/v2/revenue-recurring-series');
   await page.locator('#view button[data-action=expense]').click();await Promise.all([a.entered,b.entered]);
   await page.locator('#view button[data-action=revenue]').click();await page.locator('#view button[data-action=revenue].selected').waitFor();
   observations.before_release=await page.locator('#view .tabs button.selected').innerText();await Promise.all([a.release(),b.release()]);
   observations.after_release=await page.locator('#view .tabs button.selected').innerText();assert.equal(observations.after_release,'Receitas','OLD_REQUEST_CHANGED_CURRENT_RECURRING_SELECTION');
  });
  await scenario('open_finance_flow_rejects_old_filter_error',async({page,hold,observations})=>{
   await page.locator('#of-tab-flow').click();await page.locator('.of-results .of-table').waitFor();
   const h=hold(u=>u.pathname==='/api/v2/open-finance/transactions'&&u.searchParams.get('search')==='old',503);
   await page.locator('#of-panel-flow input[name=search]').fill('old');await page.locator('#of-panel-flow button[type=submit]').click();await h.entered;
   await page.locator('#of-panel-flow input[name=search]').fill('');await page.locator('#of-panel-flow button[type=submit]').click();await page.locator('.of-results .of-table').waitFor();await h.release();
   observations.alerts=await page.locator('.of-results [role=alert]').count();observations.tables=await page.locator('.of-results .of-table').count();assert.equal(observations.alerts,0);assert.equal(observations.tables,1);
  });
  await scenario('selected_assets_reentry_initializes_current_resource',async({page,nav,observations})=>{
   await page.locator('#of-tab-assets').click();await page.locator('#of-panel-assets .of-resource-card').first().waitFor();await nav('catalogs');await page.locator('#view h1').getByText('Cadastros',{exact:true}).waitFor();await nav('open-finance');await page.locator('#of-panel-assets .of-resource-card').first().waitFor();
   observations.selected=await page.locator('#of-tab-assets').getAttribute('aria-selected');observations.cards=await page.locator('#of-panel-assets .of-resource-card').count();assert.equal(observations.selected,'true');assert(observations.cards>0);
  });

  for(const lateError of [false,true])await scenario(lateError?'older_expense_filter_error_does_not_pollute_newer_success':'older_expense_filter_success_does_not_replace_newer_success',async({page,nav,hold,handlers,observations,expenses})=>{
   await nav('expenses');await page.waitForFunction(()=>document.querySelector('#page-label')?.textContent==='Página 1');
   assert(expenses()?.items.length,'SYNTHETIC_REVENUE_FIXTURE_REQUIRED');
   const row=mark=>{const d=structuredClone(expenses());for(const r of d.items)r.description=mark;return d};
   const h=hold(u=>u.pathname==='/api/v2/expenses'&&u.searchParams.get('search')==='old',lateError?503:200,lateError?{error:{code:'STORAGE_UNAVAILABLE'}}:row('OLD_SYNTHETIC_RESULT'));
   handlers.push({match:u=>u.pathname==='/api/v2/expenses'&&u.searchParams.get('search')==='new',run:route=>route.fulfill({json:row('NEW_SYNTHETIC_RESULT')})});
   await page.locator('#search').fill('old');await page.locator('#apply').click();await h.entered;
   await page.locator('#search').fill('new');await page.locator('#apply').click();await page.locator('#expense-rows').getByText('NEW_SYNTHETIC_RESULT',{exact:true}).first().waitFor();
   observations.before_release={search:await page.locator('#search').inputValue(),new_result:await page.locator('#expense-rows').getByText('NEW_SYNTHETIC_RESULT',{exact:true}).count()};
   await h.release();observations.after_release={search:await page.locator('#search').inputValue(),new_result:await page.locator('#expense-rows').getByText('NEW_SYNTHETIC_RESULT',{exact:true}).count(),old_result:await page.locator('#expense-rows').getByText('OLD_SYNTHETIC_RESULT',{exact:true}).count(),active_errors:await page.locator('#status .attention').count()};
   assert(observations.after_release.new_result>0,'LATEST_FILTER_RESULT_REPLACED_BY_OLDER_RESPONSE');assert.equal(observations.after_release.old_result,0);assert.equal(observations.after_release.active_errors,0,'OLD_FILTER_ERROR_POLLUTED_CURRENT_SUCCESS');
  });

  await scenario('old_domain_401_cannot_redirect_after_new_resource_success',async({page,hold,observations})=>{
   const h=hold(u=>u.pathname==='/api/v2/open-finance/domain'&&u.searchParams.get('resource')==='investments',401,{error:{code:'UNAUTHORIZED'}});
   await page.locator('#of-tab-assets').click();await h.entered;
   await page.locator('#of-panel-assets select[name=resource]').selectOption('loans');await page.locator('#of-panel-assets button[type=submit]').click();await page.locator('#of-panel-assets [data-domain-kind=CREDIT_CONTRACT]').first().waitFor();
   await h.release();observations.pathname=new URL(page.url()).pathname;observations.hosts=await page.locator('.of-screen').count();assert.equal(observations.pathname,'/app/','OLD_DOMAIN_401_REDIRECTED_CURRENT_SESSION');assert.equal(observations.hosts,1);
  });
  await scenario('old_flow_401_cannot_redirect_after_new_filter_success',async({page,hold,observations})=>{
   await page.locator('#of-tab-flow').click();await page.locator('.of-results .of-table').waitFor();
   const h=hold(u=>u.pathname==='/api/v2/open-finance/transactions'&&u.searchParams.get('search')==='old',401,{error:{code:'UNAUTHORIZED'}});
   await page.locator('#of-panel-flow input[name=search]').fill('old');await page.locator('#of-panel-flow button[type=submit]').click();await h.entered;
   await page.locator('#of-panel-flow input[name=search]').fill('');await page.locator('#of-panel-flow button[type=submit]').click();await page.locator('.of-results .of-table').waitFor();
   await h.release();observations.pathname=new URL(page.url()).pathname;observations.tables=await page.locator('.of-results .of-table').count();assert.equal(observations.pathname,'/app/','OLD_FLOW_401_REDIRECTED_CURRENT_SESSION');assert.equal(observations.tables,1);
  });

  await scenario('older_poll_snapshot_does_not_replace_newer_snapshot',async({page,hold,handlers,observations})=>{
   await page.locator('#of-tab-connections').click();
   const post=hold(u=>u.pathname==='/api/v2/open-finance/coverage-sync',200,{run:{state:'SUCCEEDED'}});
   page.once('dialog',d=>d.accept());await page.locator('[data-coverage-sync]').first().click();await post.entered;
   const old=hold(u=>u.pathname==='/api/v2/open-finance/coverage',200,{coverage:[{state:'RUNNING'}]});
   await page.evaluate(()=>{void window.__c8rPolls[0]()});await old.entered;
   handlers.push({match:u=>u.pathname==='/api/v2/open-finance/coverage',run:r=>r.fulfill({json:{coverage:Array.from({length:3},()=>({state:'RUNNING'}))}})});
   await page.evaluate(()=>window.__c8rPolls[0]());await page.locator('[data-coverage-progress]').getByText('3 coleções em andamento',{exact:false}).waitFor();
   const received=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v2/open-finance/coverage');await old.release(false);await(await received).finished();await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
   observations.progress=await page.locator('[data-coverage-progress]').innerText();await post.release();assert.match(observations.progress,/^3 coleções/,'OLD_POLL_REPLACED_NEWER_SNAPSHOT');
  });
  await scenario('finished_collection_invalidates_pending_poll_401',async({page,hold,observations})=>{
   await page.locator('#of-tab-connections').click();const post=hold(u=>u.pathname==='/api/v2/open-finance/coverage-sync',200,{run:{state:'SUCCEEDED'}});
   page.once('dialog',d=>d.accept());await page.locator('[data-coverage-sync]').first().click();await post.entered;
   const old=hold(u=>u.pathname==='/api/v2/open-finance/coverage',401,{error:{code:'UNAUTHORIZED'}});await page.evaluate(()=>{void window.__c8rPolls[0]()});await old.entered;
   await post.release(false);await page.locator('[data-coverage-progress]').getByText('Coleta concluída.',{exact:false}).waitFor();await old.release();observations.pathname=new URL(page.url()).pathname;assert.equal(observations.pathname,'/app/','FINISHED_POLL_REDIRECTED_CURRENT_SESSION');
  });
  await scenario('older_catalog_refresh_401_does_not_redirect_newer_refresh',async({page,nav,hold,observations})=>{
   await nav('catalogs');await page.locator('[data-action=toggle-accounts]').first().waitFor();
   const a=hold(u=>u.pathname.startsWith('/api/v2/accounts/'),200,{}),b=hold(u=>u.pathname.startsWith('/api/v2/categories/'),200,{});
   await page.locator('[data-action=toggle-accounts]').first().click();await page.locator('dialog[open] button[type=submit]').click();await a.entered;
   await page.locator('[data-action=toggle-categories]').first().click();await page.locator('dialog[open] button[type=submit]').click();await b.entered;
   const old=hold(u=>u.pathname==='/api/v2/catalogs',401,{error:{code:'UNAUTHORIZED'}});
   await a.release(false);await old.entered;await b.release(false);await page.locator('[data-action=toggle-accounts]').first().waitFor();await old.release();observations.pathname=new URL(page.url()).pathname;assert.equal(observations.pathname,'/app/','OLD_CATALOG_REFRESH_REDIRECTED_CURRENT_SESSION');
  });

  const financial=async(c,kind='revenues')=>{
   const {page,nav}=c;await nav(kind);const label=kind==='revenues'?'#rpage':'#page-label';await page.waitForFunction(s=>document.querySelector(s)?.textContent==='Página 1',label);
   const data=(kind==='revenues'?c.revenues:c.expenses)();assert(data?.items.length,'SYNTHETIC_FINANCIAL_FIXTURE_REQUIRED');
   return mark=>{const d=structuredClone(data);for(const x of d.items)x.description=mark;return d};
  };
  const frames=page=>page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  const addData=(handlers,search,data,kind='revenues')=>handlers.push({match:u=>u.pathname==='/api/v2/'+kind&&u.searchParams.get('search')===search,run:r=>r.fulfill({json:data})});
  await scenario('old_success_cannot_replace_current_error',async c=>{
   const {page,hold,handlers,observations}=c,row=await financial(c),old=hold(u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='old',200,row('OLD_RESULT'));
   handlers.push({match:u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='bad',run:r=>r.fulfill({status:503,json:{error:{code:'STORAGE_UNAVAILABLE'}}})});
   await page.locator('#revenue-search').fill('old');await page.locator('#filter-revenue').click();await old.entered;
   await page.locator('#revenue-search').fill('bad');await page.locator('#filter-revenue').click();await page.locator('#status .attention').waitFor();await old.release();
   observations.errors=await page.locator('#status .attention').count();observations.oldRows=await page.locator('#revenue-rows').getByText('OLD_RESULT',{exact:true}).count();observations.loading=await page.locator('#revenue-rows [data-query-loading]').count();assert.equal(observations.errors,1);assert.equal(observations.oldRows,0);assert.equal(observations.loading,0);
  });
  await scenario('old_finalization_cannot_end_current_loading',async c=>{
   const {page,hold,observations}=c,row=await financial(c),old=hold(u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='old',200,row('OLD_RESULT')),current=hold(u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='new',200,row('NEW_RESULT'));
   await page.locator('#revenue-search').fill('old');await page.locator('#filter-revenue').click();await old.entered;await page.locator('#revenue-search').fill('new');await page.locator('#filter-revenue').click();await current.entered;
   const response=page.waitForResponse(r=>new URL(r.url()).searchParams.get('search')==='old');await old.release(false);await(await response).finished();await frames(page);
   observations.loading=await page.locator('#revenue-rows [data-query-loading]').count();observations.busy=await page.locator('#revenue-rows').getAttribute('aria-busy');assert.equal(observations.loading,1);assert.equal(observations.busy,'true');await current.release();assert.equal(await page.locator('#revenue-rows [data-query-loading]').count(),0);assert.equal(await page.locator('#revenue-rows').getAttribute('aria-busy'),null);assert(await page.locator('#revenue-rows').getByText('NEW_RESULT',{exact:true}).count()>0);
  });
  await scenario('three_rapid_filters_keep_the_latest_response',async c=>{
   const {page,hold,handlers,observations}=c,row=await financial(c),a=hold(u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='a',200,row('RESULT_A')),b=hold(u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='b',200,row('RESULT_B'));addData(handlers,'c',row('RESULT_C'));
   for(const [value,h] of [['a',a],['b',b]]){await page.locator('#revenue-search').fill(value);await page.locator('#filter-revenue').click();await h.entered}
   await page.locator('#revenue-search').fill('c');await page.locator('#filter-revenue').click();await page.locator('#revenue-rows').getByText('RESULT_C',{exact:true}).first().waitFor();
   await b.release(false);await a.release();observations.search=await page.locator('#revenue-search').inputValue();observations.current=await page.locator('#revenue-rows').getByText('RESULT_C',{exact:true}).count();assert.equal(observations.search,'c');assert(observations.current>0);assert.equal(await page.locator('#revenue-rows').getByText('RESULT_A',{exact:true}).count(),0);assert.equal(await page.locator('#revenue-rows').getByText('RESULT_B',{exact:true}).count(),0);
  });
  await scenario('rapid_recurring_selections_keep_latest_loading_and_selection',async({page,nav,hold,observations})=>{
   await nav('recurring');await page.locator('#view button[data-action=expense]').waitFor();
   const a=hold(u=>u.pathname==='/api/v2/recurring-series'),b=hold(u=>u.pathname==='/api/v2/revenue-recurring-series');await page.locator('#view button[data-action=expense]').click();await Promise.all([a.entered,b.entered]);
   const c=hold(u=>u.pathname==='/api/v2/recurring-series'),d=hold(u=>u.pathname==='/api/v2/revenue-recurring-series');await page.locator('#view button[data-action=revenue]').click();await Promise.all([c.entered,d.entered]);
   await Promise.all([a.release(false),b.release(false)]);observations.loading=await page.locator('[data-recurring-results] [data-query-loading]').count();assert.equal(observations.loading,1);assert.equal(await page.locator('#view .tabs button.selected').innerText(),'Receitas');
   await page.locator('#view button[data-action=all]').click();await page.locator('[data-recurring-results][aria-busy]').waitFor({state:'hidden'});await Promise.all([c.release(false),d.release(false)]);await page.waitForLoadState('networkidle');observations.selected=await page.locator('#view .tabs button.selected').innerText();assert.equal(observations.selected,'Todas');assert.equal(await page.locator('[data-recurring-results] [data-query-loading]').count(),0);
  });
  await scenario('same_screen_reentry_discards_pending_old_filter',async c=>{
   const {page,hold,observations}=c,row=await financial(c),old=hold(u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='old',200,row('OLD_REENTRY'));
   await page.locator('#revenue-search').fill('old');await page.locator('#filter-revenue').click();await old.entered;await page.evaluate(()=>window.dispatchEvent(new HashChangeEvent('hashchange')));await page.waitForFunction(()=>document.querySelector('#rpage')?.textContent==='Página 1');await old.release();observations.search=await page.locator('#revenue-search').inputValue();assert.equal(observations.search,'');assert.equal(await page.locator('#revenue-rows').getByText('OLD_REENTRY',{exact:true}).count(),0);assert.equal(await page.locator('#view h1').innerText(),'Receitas');
  });
  await scenario('leaving_and_returning_during_expense_query_preserves_new_screen',async c=>{
   const {page,nav,hold,observations}=c,row=await financial(c,'expenses'),old=hold(u=>u.pathname==='/api/v2/expenses'&&u.searchParams.get('search')==='old',200,row('OLD_EXPENSE'));
   await page.locator('#search').fill('old');await page.locator('#apply').click();await old.entered;await nav('open-finance');await page.locator('#of-panel-overview .of-resource-card').first().waitFor();await nav('expenses');await page.waitForFunction(()=>document.querySelector('#page-label')?.textContent==='Página 1');await old.release();observations.search=await page.locator('#search').inputValue();assert.equal(observations.search,'');assert.equal(await page.locator('#expense-rows').getByText('OLD_EXPENSE',{exact:true}).count(),0);assert.equal(await page.locator('#view h1').innerText(),'Despesas');
  });
  await scenario('native_query_abort_allows_a_new_query',async c=>{
   const {page,hold,handlers,observations,requestFailures}=c,row=await financial(c),old=hold(u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='old',200,row('OLD_ABORT'));addData(handlers,'new',row('NEW_AFTER_ABORT'));
   await page.locator('#revenue-search').fill('old');await page.locator('#filter-revenue').click();await old.entered;await page.locator('#revenue-search').fill('new');await page.locator('#filter-revenue').click();await page.locator('#revenue-rows').getByText('NEW_AFTER_ABORT',{exact:true}).first().waitFor();await old.release();observations.aborted=requestFailures.some(x=>x.path==='/api/v2/revenues'&&x.error==='net::ERR_ABORTED');assert(observations.aborted);assert.equal(await page.locator('#status .attention').count(),0);assert.equal(await page.locator('#revenue-rows [data-query-loading]').count(),0);
  },{ignoreAbort:false});
  await scenario('independent_open_finance_panels_do_not_cancel_each_other',async({page,hold,observations})=>{
   const cards=hold(u=>u.pathname==='/api/v2/open-finance/domain'&&u.searchParams.get('resource')==='accounts'&&u.searchParams.get('type')==='CREDIT');await page.locator('#of-tab-cards').click();await cards.entered;await page.locator('#of-tab-assets').click();await page.locator('#of-panel-assets [data-domain-kind=INVESTMENT_POSITION]').first().waitFor();await cards.release();observations.selected=await page.locator('#of-tab-assets').getAttribute('aria-selected');observations.cards=await page.locator('#of-panel-cards [data-domain-kind=CREDIT_CARD]').count();observations.positions=await page.locator('#of-panel-assets [data-domain-kind=INVESTMENT_POSITION]').count();assert.equal(observations.selected,'true');assert(observations.cards>0&&observations.positions>0);
  });
  for(const kind of ['revenues','expenses'])await scenario(kind+'_active_error_then_new_query_recovers',async c=>{
   const {page,handlers,observations}=c,row=await financial(c,kind),search=kind==='revenues'?'#revenue-search':'#search',button=kind==='revenues'?'#filter-revenue':'#apply',target=kind==='revenues'?'#revenue-rows':'#expense-rows';
   handlers.push({match:u=>u.pathname==='/api/v2/'+kind&&u.searchParams.get('search')==='bad',run:r=>r.fulfill({status:503,json:{error:{code:'STORAGE_UNAVAILABLE'}}})});addData(handlers,'new',row('RECOVERED_RESULT'),kind);
   await page.locator(search).fill('bad');await page.locator(button).click();await page.locator('#status .attention').waitFor();assert.equal(await page.locator(target+' [data-query-loading]').count(),0);await page.locator(search).fill('new');await page.locator(button).click();await page.locator(target).getByText('RECOVERED_RESULT',{exact:true}).first().waitFor();observations.errors=await page.locator('#status .attention').count();assert.equal(observations.errors,0);assert.equal(await page.locator(target).getAttribute('aria-busy'),null);
  });
  await scenario('superseded_auxiliary_catalog_response_cannot_restore_old_revenue_data',async c=>{
   const {page,hold,handlers,observations}=c,row=await financial(c);addData(handlers,'old',row('OLD_AUXILIARY'));const catalog=hold(u=>u.pathname==='/api/v2/catalogs');
   await page.locator('#revenue-search').fill('old');await page.locator('#filter-revenue').click();await catalog.entered;addData(handlers,'new',row('NEW_AUXILIARY'));await page.locator('#revenue-search').fill('new');await page.locator('#filter-revenue').click();await page.locator('#revenue-rows').getByText('NEW_AUXILIARY',{exact:true}).first().waitFor();await catalog.release();observations.newRows=await page.locator('#revenue-rows').getByText('NEW_AUXILIARY',{exact:true}).count();assert(observations.newRows>0);assert.equal(await page.locator('#revenue-rows').getByText('OLD_AUXILIARY',{exact:true}).count(),0);
  });
  await scenario('out_of_order_pagination_keeps_current_page_and_rows',async c=>{
   const {page,hold,handlers,observations}=c,row=await financial(c),data=number=>{const d=row('');d.items=Array.from({length:25},(_,i)=>({...d.items[0],id:10000*number+i+1,description:'PAGE_'+number+'_ROW_'+i}));d.page=number;d.page_size=25;d.has_more=number<3;d.total=75;return d};
   handlers.push({match:u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='paging'&&u.searchParams.get('page')==='1',run:r=>r.fulfill({json:data(1)})});
   await page.locator('#revenue-search').fill('paging');await page.locator('#filter-revenue').click();await page.locator('#revenue-rows').getByText('PAGE_1_ROW_0',{exact:true}).waitFor();
   const old=hold(u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('page')==='2',200,data(2));handlers.push({match:u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('page')==='3',run:r=>r.fulfill({json:data(3)})});
   await page.locator('#rn').click();await old.entered;await page.locator('#rn').click();await page.locator('#revenue-rows').getByText('PAGE_3_ROW_0',{exact:true}).waitFor();await old.release();observations.page=await page.locator('#rpage').innerText();observations.currentRows=await page.locator('#revenue-rows tbody tr').count();assert.equal(observations.page,'Página 3');assert.equal(observations.currentRows,25);assert.equal(await page.locator('#revenue-rows').getByText('PAGE_2_ROW_0',{exact:true}).count(),0);assert(await page.locator('#rn').isDisabled());
  });
  await scenario('current_query_401_still_requires_authentication',async c=>{
   const {page,handlers,observations}=c;await financial(c);handlers.push({match:u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='auth',run:r=>r.fulfill({status:401,json:{error:{code:'UNAUTHORIZED'}}})});await page.locator('#revenue-search').fill('auth');await page.locator('#filter-revenue').click();await page.waitForURL('**/app/unlock');observations.pathname=new URL(page.url()).pathname;assert.equal(observations.pathname,'/app/unlock');
  });
  await scenario('queued_poll_callback_after_completion_does_not_start_another_read',async({page,hold,handlers,observations})=>{
   await page.locator('#of-tab-connections').click();const post=hold(u=>u.pathname==='/api/v2/open-finance/coverage-sync',200,{run:{state:'SUCCEEDED'}});page.once('dialog',d=>d.accept());await page.locator('[data-coverage-sync]').first().click();await post.entered;await post.release();await page.locator('[data-coverage-progress]').getByText('Coleta concluída.',{exact:false}).waitFor();let calls=0;handlers.push({match:u=>u.pathname==='/api/v2/open-finance/coverage',run:r=>{calls++;return r.fulfill({json:{coverage:[]}})}});await page.evaluate(()=>window.__c8rPolls[0]());await frames(page);observations.callsAfterCompletion=calls;assert.equal(calls,0);
  });
  await scenario('old_network_timeout_does_not_replace_current_success',async c=>{
   const {page,hold,handlers,observations}=c,row=await financial(c),old=hold(u=>u.pathname==='/api/v2/revenues'&&u.searchParams.get('search')==='old',200,row('OLD_TIMEOUT'),{abort:'timedout'});addData(handlers,'new',row('CURRENT_AFTER_TIMEOUT'));
   await page.locator('#revenue-search').fill('old');await page.locator('#filter-revenue').click();await old.entered;await page.locator('#revenue-search').fill('new');await page.locator('#filter-revenue').click();await page.locator('#revenue-rows').getByText('CURRENT_AFTER_TIMEOUT',{exact:true}).first().waitFor();await old.release();observations.errors=await page.locator('#status .attention').count();assert.equal(observations.errors,0);assert.equal(await page.locator('#revenue-rows [data-query-loading]').count(),0);
  });
 }finally{await browser.close()}
 const result={status:results.every(r=>r.status==='PASS')?'PASS':'FAIL',pass:results.filter(r=>r.status==='PASS').length,fail:results.filter(r=>r.status==='FAIL').length,tests:results,external_requests:external,actual_api_writes:realWrites,real_bank_requests:0,product_code_modified:false,wait_limit_ms:timeout};fs.writeFileSync(path.join(out,'UI_REVIEW_RESULTS.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));process.exitCode=result.fail?1:0;
}
main().catch(e=>{console.error(e.stack);process.exitCode=1});
