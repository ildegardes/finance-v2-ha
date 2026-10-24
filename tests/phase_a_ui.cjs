// Synthetic frontend integration only. No SQLite, migrations, banks or HA.
const {test,before,after,beforeEach,afterEach}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {pathToFileURL}=require('node:url');
const runtime=process.env.FINANCE_NODE_MODULES||path.join(process.env.USERPROFILE||process.env.HOME,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const {chromium}=require(path.join(runtime,'playwright'));
const web=path.resolve(__dirname,'../finance-v17/src/finance_v2/web');
const evidence=process.env.FINANCE_UI_EVIDENCE;
const KEY='finance-v17:money-visible',MASK='R$ ••••••';
let browser,server,origin,context,page,requests,jsErrors,external;
const catalog={accounts:[{id:1,name:'Conta sintética',active:1}],categories:[{id:1,name:'Categoria sintética',active:1}],tags:[],cards:[{id:1,name:'Cartão sintético',active:1}]};
const expense={id:1,description:'Despesa sintética',amount_cents:123456,expense_date:'2026-10-12',due_date:'2026-10-18',planned_payment_method:'PIX',category_id:1,account_id:1,category_name:'Categoria sintética',effective_status:'PENDING',financial_status:'PENDING',lifecycle_state:'ACTIVE',requires_manual_action:true,tags:[],payments:[]};
const revenue={...expense,description:'Receita sintética',competence_date:'2026-10-12',expected_on:'2026-10-18',receipts:[]};
const recurring={...expense,description:'Recorrência sintética',frequency:'MONTHLY',active:1,start_date:'2026-10-12',next_occurrence:'2026-10-18'};
const invoice={id:1,card_id:1,state:'OPEN',balance_cents:123456,effective_total_cents:123456,paid_cents:0,payment_mode:'MANUAL',closing_date:'2026-10-12',due_date:'2026-10-18',items:[expense],payments:[],events:[]};
const connections=[{id:'itau-test',institution:'Itaú',enabled:false},{id:'santander-test',institution:'Santander',enabled:false}];
const accounts=connections.map(c=>({connection_id:c.id,external_id:'private-account-test',name:'Conta corrente'}));
const runs=Array.from({length:4},(_,i)=>({id:'run-test-'+i,connection_id:connections[i%2].id,state:'SUCCEEDED',started_at:'2026-10-18T23:30:00Z',inserted_count:1,updated_count:0,page_count:1}));
const ofCatalog={connections,accounts,categories:connections.map(c=>({connection_id:c.id,category_key:'id:food',original_name:'Food and drink'})),runs};
const transactions=Array.from({length:63},(_,i)=>({id:i+1,connection_id:i<50?'itau-test':'santander-test',external_account_id:'private-account-test',account_name:'Conta corrente',institution:i<50?'Itaú':'Santander',transaction_date:'2026-10-12',amount_decimal:i===0?'-1234.56':'1234.56',currency:'BRL',description_original:i===0?'Café sintético':'Movimento sintético '+i,merchant_name:'Estabelecimento sintético',category_key:'id:food',category:{original_name:'Food and drink'},direction:{result:i%2===0?'DEBIT':'CREDIT',reason_code:'DECLARED_PROVIDER_TYPE',warnings:[]},origin:{status:'unknown'}}));
function fixture(url){
  const p=url.pathname.replace('/api/v2','');
  if(p==='/context')return {system_date:'2026-10-23',csrf_token:'artificial-csrf'};
  if(p==='/catalogs')return catalog;
  if(p==='/dashboard')return {summary:{revenue_received_cents:223456,revenue_expected_cents:223456,net_paid_cents:100000,expense_recognized_cents:123456,expense_pending_cents:123456,invoice_open_cents:123456,expense_overdue_cents:123456},trend:[{month:'2026-10-01',revenue_cents:223456,expense_cents:123456}],categories:[{name:'Sintética',amount_cents:123456}],upcoming:[expense],invoices:[{...invoice,card_name:'Cartão sintético',amount_cents:123456}],recurring:[{...recurring,kind:'EXPENSE'}],recent:[{...expense,kind:'EXPENSE',event_date:'2026-10-12'}]};
  if(p==='/expenses'||p==='/revenues')return {items:[p==='/expenses'?expense:revenue],has_more:false};
  if(p==='/expenses/1')return expense;
  if(p==='/revenues/1')return revenue;
  if(p==='/cards')return {items:catalog.cards};
  if(p==='/cards/1')return {card:catalog.cards[0],calendar_versions:[{effective_from:'2026-01-01',closing_day:12,due_day:18}],invoices:[invoice]};
  if(p==='/invoices')return {items:[invoice]};
  if(p==='/invoices/1')return invoice;
  if(p==='/recurring-series'||p==='/revenue-recurring-series')return {items:[recurring]};
  if(p==='/revenue-recurring-series/1')return {series:{...recurring,expected_day:18},occurrences:[]};
  if(p==='/installment-series')return {items:[{...expense,total_cents:123456,payment_method:'PIX',purchase_date:'2026-10-12',installment_count:3,next_installment:{installment_number:1,amount_cents:123456,expense_date:'2026-10-12'}}]};
  if(p==='/open-finance/catalogs')return ofCatalog;
  if(p==='/open-finance/resources')return {resource:url.searchParams.get('resource'),items:[],coverage:[],total:0,page:+(url.searchParams.get('page')||1),has_more:false};
  if(p==='/open-finance/transactions'){
    const q=url.searchParams;
    const selected=transactions.filter(t=>(!q.get('connection_id')||t.connection_id===q.get('connection_id'))&&(!q.get('external_account_id')||t.external_account_id===q.get('external_account_id'))&&(!q.get('category_key')||t.category_key===q.get('category_key'))&&(!q.get('search')||t.description_original.toLocaleLowerCase().normalize('NFD').replace(/\p{M}/gu,'').includes(q.get('search')))&&(!q.get('start')||t.transaction_date>=q.get('start'))&&(!q.get('end')||t.transaction_date<=q.get('end'))&&(!q.get('direction')||q.get('direction')==='all'||t.direction.result===(q.get('direction')==='incoming'?'CREDIT':'DEBIT')));
    // The artificial API honors the existing query shape; no claim of backend filter validation.
    const page=+(q.get('page')||1),size=+(q.get('page_size')||25);
    return {items:selected.slice((page-1)*size,page*size),has_more:page*size<selected.length,query_meta:{counts:{after_f04:{state:'EXACT',value:selected.length}},query_completeness:'COMPLETE',coverage:{direction:{state:'COMPLETE'}},warnings:['PROVENANCE_UNKNOWN_PRESENT']}};
  }
  throw new Error('UNEXPECTED_API:'+p);
}
before(async()=>{
  server=http.createServer((req,res)=>{
    const pathname=new URL(req.url,'http://localhost').pathname;
    const relative=pathname==='/app/'?'index.html':pathname.replace('/app/assets/','');
    const file=path.resolve(web,relative);
    if(!file.startsWith(web+path.sep)||!fs.existsSync(file)){res.writeHead(404);res.end();return}
    res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin='http://127.0.0.1:'+server.address().port;
  const edge=process.env.FINANCE_BROWSER_EXECUTABLE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
  browser=await chromium.launch({headless:true,...(fs.existsSync(edge)?{executablePath:edge}:{})});
});
after(async()=>{await browser?.close();await new Promise(resolve=>server?.close(resolve))});
beforeEach(async()=>{
  requests=[];jsErrors=[];external=0;
  context=await browser.newContext({viewport:{width:1440,height:1000}});context.setDefaultTimeout(5000);
  await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.origin!==origin){external++;return route.abort()}
    if(url.pathname.startsWith('/api/v2/')){
      requests.push({path:url.pathname,query:Object.fromEntries(url.searchParams),method:req.method(),body:req.postDataJSON()});
      if(req.method()!=='GET')return route.fulfill({status:403,json:{error:{code:'SYNTHETIC_WRITES_FORBIDDEN'}}});
      return route.fulfill({json:fixture(url)});
    }
    return route.continue();
  });
  page=await context.newPage();page.on('pageerror',e=>jsErrors.push(e.message));
});
afterEach(async()=>{await context.close();assert.deepEqual(jsErrors,[]);assert.equal(external,0);assert.equal(requests.filter(r=>r.method!=='GET').length,0)});
async function go(hash='dashboard'){await page.goto(origin+'/app/#'+hash);await page.locator('h1').waitFor();await page.waitForFunction(()=>document.querySelector('#money-privacy-toggle svg'));}
async function flow(){await go('open-finance');await page.getByRole('tab',{name:'Fluxo',exact:true}).click();await page.locator('.of-table tbody tr').first().waitFor()}
async function masked(){await page.waitForFunction(()=>document.documentElement.dataset.moneyPrivacy==='hidden');assert.doesNotMatch(await page.locator('#view').innerText(),/\d[.,]\d{2}(?:\s|$)/);assert.match(await page.locator('#view').innerText(),/R\$ ••••••/)}

test('default hidden, accessible eye button and immediate toggle without requests',async()=>{
  await flow();await masked();const count=requests.length;
  const button=page.getByRole('button',{name:'Exibir valores monetários'});assert.equal(await button.getAttribute('aria-pressed'),'false');
  await button.click();assert.match(await page.locator('.of-results').innerText(),/R\$ 1\.234,56/);assert.equal(await page.locator('#money-privacy-toggle').getAttribute('aria-pressed'),'true');
  await page.locator('#money-privacy-toggle').click();await masked();assert.equal(requests.length,count);
});
test('visible preference survives reload; hidden preference also survives reload',async()=>{
  await flow();await page.locator('#money-privacy-toggle').click();await page.reload();await page.getByRole('tab',{name:'Fluxo',exact:true}).click();await page.locator('.of-table').waitFor();assert.match(await page.locator('.of-results').innerText(),/1\.234,56/);
  await page.locator('#money-privacy-toggle').click();await page.reload();await page.getByRole('tab',{name:'Fluxo',exact:true}).click();await page.locator('.of-table').waitFor();await masked();
});
test('storage unavailable fails closed but toggle remains functional',async()=>{
  await page.addInitScript(()=>{Storage.prototype.getItem=()=>{throw new Error('storage blocked')};Storage.prototype.setItem=()=>{throw new Error('storage blocked')}});
  await flow();await masked();await page.locator('#money-privacy-toggle').click();assert.match(await page.locator('.of-results').innerText(),/1\.234,56/);
});
test('invalid saved preference fails closed',async()=>{
  await page.addInitScript(key=>localStorage.setItem(key,'garbage'),KEY);await flow();await masked();
});
test('same-origin storage event immediately hides another open tab',async()=>{
  await flow();await page.locator('#money-privacy-toggle').click();const other=await context.newPage();await other.goto(origin+'/app/#open-finance');await other.locator('h1').waitFor();await other.locator('#money-privacy-toggle').click();await masked();await other.close();
});
for(const [hash,selector] of [['dashboard','.summary-card'],['expenses','.finance-table'],['expense-1','.detail-value'],['revenues','.finance-table'],['revenue-1','.detail-value'],['invoices','.invoice-card'],['invoice-1','.detail-value'],['recurring','.finance-table'],['installments','.finance-table']]){
  test('privacy across real frontend screen: '+hash,async()=>{await go(hash);await page.locator(selector).first().waitFor();await masked();await page.locator('#money-privacy-toggle').click();assert.match(await page.locator('#view').innerText(),/1\.234,56/);await page.locator('#money-privacy-toggle').click();await masked()});
}
test('cards route, calendar and navigation remain operational',async()=>{await go('cards');await page.locator('.invoice-card').waitFor();await page.getByText('Ver cartão e calendário').click();await page.getByRole('heading',{name:'Calendário versionado'}).waitFor();assert.match(await page.locator('#view').innerText(),/01\/01\/2026/)});
test('inputs and FormData retain exact amounts while masked and after toggling',async()=>{
  await go('expenses-new');const field=page.locator('input[name=amount]');await field.waitFor();await field.fill('1234,56');
  await page.waitForFunction(()=>document.querySelector('[name=amount]').type==='password');
  assert.equal(await field.inputValue(),'1234,56');assert.equal(await page.evaluate(()=>new FormData(document.querySelector('#new-expense')).get('amount')),'1234,56');
  assert.equal(await field.locator('..').locator('.privacy-field-mask').innerText(),MASK);
  await page.locator('#money-privacy-toggle').click();assert.equal(await field.getAttribute('type'),'text');assert.equal(await field.inputValue(),'1234,56');
});
test('late asynchronous rendering and SVG titles are masked before animation frame',async()=>{
  await flow();const result=await page.evaluate(async()=>{
    const el=document.createElement('section');document.querySelector('#view').append(el);
    await Promise.resolve();el.innerHTML='<p title="R$ 9.876,54" aria-label="Saldo R$ 9.876,54">R$ 9.876,54</p><svg><title>R$ 9.876,54</title></svg>';
    await new Promise(requestAnimationFrame);return {text:el.textContent,title:el.querySelector('p').title,label:el.querySelector('p').getAttribute('aria-label')};
  });assert(!JSON.stringify(result).includes('9.876,54'));assert.match(result.text,/••••••/);
});
test('replaced text and accessible labels never restore stale amounts',async()=>{
  await flow();await page.evaluate(()=>{const p=document.createElement('p');p.id='late';p.textContent='R$ 10,00';p.title='R$ 10,00';document.querySelector('#view').append(p)});
  await page.waitForFunction(()=>document.querySelector('#late').textContent.includes('••'));
  await page.evaluate(()=>{document.querySelector('#late').textContent='R$ 20,00';document.querySelector('#late').title='R$ 20,00'});
  await page.locator('#money-privacy-toggle').click();assert.equal(await page.locator('#late').innerText(),'R$ 20,00');assert.equal(await page.locator('#late').getAttribute('title'),'R$ 20,00');
});
test('default overview and assets do not invent balances',async()=>{
  await go('open-finance');await page.getByRole('tabpanel',{name:'Visão geral',exact:true}).waitFor();await page.locator('#of-panel-overview .empty').waitFor();assert.match(await page.locator('#of-panel-overview').innerText(),/não são somados como patrimônio/);
  await page.getByRole('tab',{name:'Ativos',exact:true}).click();await page.locator('#of-panel-assets .empty').waitFor();assert.match(await page.locator('#of-panel-assets').innerText(),/não comprova ausência/);assert.doesNotMatch(await page.locator('#of-panel-assets').innerText(),/R\$|0,00/);
});
test('connections reuse four runs, dates and catalog without synchronization',async()=>{
  await go('open-finance');await page.getByRole('tab',{name:'Conexões',exact:true}).click();assert.equal(await page.locator('.of-history li').count(),4);assert.match(await page.locator('.of-history').innerText(),/18\/10\/2026/);assert(!requests.some(r=>/sync/.test(r.path)));
});
test('tabs implement keyboard arrows, Home, End, selection and panel relationships',async()=>{
  await go('open-finance');const first=page.getByRole('tab',{name:'Visão geral',exact:true});await first.focus();await page.keyboard.press('ArrowRight');assert.equal(await page.getByRole('tab',{name:'Fluxo',exact:true}).getAttribute('aria-selected'),'true');await page.keyboard.press('End');assert.equal(await page.getByRole('tab',{name:'Conexões',exact:true}).getAttribute('aria-selected'),'true');await page.keyboard.press('Home');assert.equal(await first.getAttribute('aria-selected'),'true');assert.equal(await page.locator('[role=tabpanel]:visible').count(),1);
});
test('pagination remains 25 + 25 + 13, no duplicates, filters survive tabs and privacy',async()=>{
  await flow();const seen=[];
  let expectedPage=1;for(const count of [25,25,13]){await page.waitForFunction(n=>document.querySelector('.of-count')?.textContent.includes('Página '+n),expectedPage++);await page.waitForFunction(n=>document.querySelectorAll('.of-table tbody tr').length===n,count);seen.push(...await page.locator('.of-table tbody tr td:nth-child(4)').allTextContents());if(count===25)await page.locator('[data-next]').click()}
  assert.equal(new Set(seen).size,63);assert.equal(await page.locator('[data-next]').isDisabled(),true);
  await page.getByRole('tab',{name:'Conexões',exact:true}).click();await page.locator('#money-privacy-toggle').click();await page.getByRole('tab',{name:'Fluxo',exact:true}).click();assert.match(await page.locator('.of-count').innerText(),/Página 3/);
  const form=page.locator('.of-filters');for(const [name,value] of [['start','2026-10-12'],['end','2026-10-18'],['search','cafe']])await form.locator(`[name=${name}]`).fill(value);
  for(const [name,value] of [['connection_id','itau-test'],['external_account_id','private-account-test'],['direction','outgoing'],['category_key','id:food'],['origin_run_id','run-test-0']])await form.locator(`[name=${name}]`).selectOption(value);
  await form.locator('[type=submit]').click();await page.waitForFunction(()=>document.querySelectorAll('.of-table tbody tr').length===1);
  const query=requests.filter(r=>r.path.endsWith('/transactions')).at(-1).query;for(const key of ['start','end','connection_id','external_account_id','direction','category_key','search','origin_run_id'])assert(query[key]);assert.equal(query.page,'1');assert.equal(query.contract,'of-l2-v2');
  await page.getByRole('tab',{name:'Ativos',exact:true}).click();await page.getByRole('tab',{name:'Fluxo',exact:true}).click();assert.equal(await form.locator('[name=search]').inputValue(),'cafe');await page.locator('[data-clear]').click();await page.waitForFunction(()=>document.querySelectorAll('.of-table tbody tr').length===25);assert.equal(await form.locator('[name=search]').inputValue(),'');
});
test('friendly account names, original bank categories, dates and BRL sign',async()=>{
  await flow();await page.locator('#money-privacy-toggle').click();const text=await page.locator('.of-results').innerText();assert.match(text,/12\/10\/2026/);assert.match(text,/-R\$ 1\.234,56/);assert.match(text,/Food and drink/);assert.match(text,/Conta corrente · Itaú/);assert.doesNotMatch(text,/private-account-test|itau-test/);assert.match(text,/Saída/);assert.match(text,/origens não comprovadas/);
});
test('empty state, query errors and loading state preserve fail-closed result handling',async()=>{
  await flow();await page.locator('[name=search]').fill('no-match');await page.locator('.of-filters [type=submit]').click();await page.getByText('Nenhuma transação encontrada para os filtros selecionados.',{exact:true}).waitFor();
  await page.route('**/api/v2/open-finance/transactions?*',async route=>{await new Promise(r=>setTimeout(r,100));return route.fulfill({status:503,json:{error:{code:'STORAGE_UNAVAILABLE'}}})});
  await page.locator('[data-clear]').click();await page.getByText('Carregando transações bancárias…',{exact:true}).waitFor();await page.locator('.of-results [role=alert]').waitFor();assert.equal(await page.locator('.of-table').count(),0);
});
test('mobile and desktop responsive layout, touch targets and focus',async()=>{
  await flow();for(const width of [360,390,768,1440]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'overflow '+width);const box=await page.locator('#money-privacy-toggle').boundingBox();assert(box.width>=44&&box.height>=44);for(const tab of await page.getByRole('tab').all())assert((await tab.boundingBox()).height>=44);}
  await page.locator('#money-privacy-toggle').focus();assert.equal(await page.locator('#money-privacy-toggle').evaluate(e=>document.activeElement===e),true);
  if(evidence){fs.mkdirSync(evidence,{recursive:true});await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:path.join(evidence,'desktop-hidden.png')});await page.setViewportSize({width:390,height:844});await page.waitForFunction(()=>document.querySelector('nav').getBoundingClientRect().right<=0);await page.screenshot({path:path.join(evidence,'mobile-hidden.png')});await page.locator('#money-privacy-toggle').click();await page.screenshot({path:path.join(evidence,'mobile-visible-synthetic.png')});}
});
test('formatting preserves precision and calendar dates, rejects unsupported input',async()=>{
  const {bankMoney,dateBR,maskText}=await import(pathToFileURL(path.join(web,'privacy.js')));
  assert.equal(bankMoney('-1234.56','BRL'),'-R$ 1.234,56');assert.equal(bankMoney('9007199254740993.1234','BRL'),'R$ 9.007.199.254.740.993,1234');assert.equal(bankMoney('0','USD'),'USD 0,00');assert.equal(bankMoney('no','BRL'),'Valor indisponível');assert.equal(bankMoney('1','<x>'),'Valor indisponível');assert.equal(dateBR('2026-10-12T23:30:00-03:00'),'12/10/2026');assert.equal(dateBR('2026-02-30'),'Data indisponível');assert.equal(maskText('Previstas R$ 12,34; -USD 1,00'),`Previstas ${MASK}; ${MASK}`);
});
test('financial action guards and direction semantics remain intact',async()=>{
  const c=await import(pathToFileURL(path.join(web,'capabilities.js'))),p=await import(pathToFileURL(path.join(web,'presentation.js')));
  assert(c.expenseActions(expense).includes('pay'));assert(!c.expenseActions({...expense,effective_status:'PAID'}).includes('pay'));
  assert(!c.revenueActions({...revenue,financial_status:'RECEIVED'}).includes('edit'));assert(!c.revenueActions({...revenue,financial_status:'CANCELLED'}).includes('receive'));
  assert(!c.invoiceActions({...invoice,state:'PAID',payments:[{id:1}]}).includes('correct'));
  assert.equal(p.financialDirection('REVENUE').label,'Entrada');assert.equal(p.financialDirection('EXPENSE').label,'Saída');
});
test('financial immutable audit presentation still preserves corrections and originals',async()=>{
  const {humanAudit}=await import(pathToFileURL(path.join(web,'presentation.js'))),{money,dateBR}=await import(pathToFileURL(path.join(web,'privacy.js')));
  const result=humanAudit({event_type:'THIS_AND_FUTURE',metadata_json:JSON.stringify({new_version_id:2,old_version_ids:[1]})},{versions:[{id:1,amount_cents:2245},{id:2,amount_cents:2490,effective_from:'2026-11-02',frequency:'MONTHLY',planned_payment_method:'CREDIT_CARD'}]},{money,dateBR,label:x=>x});
  assert.match(result.description,/22,45.*24,90/);assert.match(result.description,/02\/11\/2026/);assert.match(result.description,/preservadas/);
});
test('dynamic dialog, select options and accessible money are covered globally',async()=>{
  await go('dashboard');await page.evaluate(()=>{const d=document.createElement('dialog');d.innerHTML='<h2>Operação sintética</h2><p>Integral R$ 12,50</p><select><option value="unchanged">R$ 12,50</option></select><label>Valor<input name="total" value="12,50"></label>';document.body.append(d);d.showModal()});
  await page.waitForFunction(()=>document.querySelector('dialog').textContent.includes('••'));assert.doesNotMatch(await page.locator('dialog').innerText(),/12,50/);assert.equal(await page.locator('dialog input').inputValue(),'12,50');assert.equal(await page.locator('dialog select').inputValue(),'unchanged');
  // Native modal dialogs correctly make the header inert. Toggle from another
  // same-origin tab to exercise the real storage event while the dialog is open.
  const other=await context.newPage();await other.goto(origin+'/app/#dashboard');await other.locator('#money-privacy-toggle svg').waitFor();await other.locator('#money-privacy-toggle').click();await page.waitForFunction(()=>document.documentElement.dataset.moneyPrivacy==='visible');assert.match(await page.locator('dialog').innerText(),/12,50/);await other.close();await page.evaluate(()=>document.querySelector('dialog').close());
});
test('in-flight API response honors the latest privacy state without a visible frame',async()=>{
  let intercepted;const pending=new Promise(resolve=>intercepted=resolve);
  await page.route('**/api/v2/open-finance/transactions?*',route=>intercepted(route));
  await go('open-finance');const held=await pending;
  await page.locator('#money-privacy-toggle').click();await page.locator('#money-privacy-toggle').click();
  await held.fulfill({json:fixture(new URL(held.request().url()))});
  await page.getByRole('tab',{name:'Fluxo',exact:true}).click();await page.locator('.of-table').waitFor();
  await page.evaluate(()=>new Promise(requestAnimationFrame));await masked();
});
test('monetary prompt is a DOM dialog, retains the original value and supports confirm/cancel',async()=>{
  await go('dashboard');await page.evaluate(async()=>{const {moneyPrompt}=await import('/app/assets/privacy.js');window.syntheticMoneyResult=moneyPrompt('Valor (R$)','1234,56')});
  await page.waitForFunction(()=>document.querySelector('dialog input').type==='password');assert.equal(await page.locator('dialog input').inputValue(),'1234,56');assert.doesNotMatch(await page.locator('dialog').innerText(),/1234/);
  await page.locator('dialog input').fill('456,78');await page.locator('dialog').getByRole('button',{name:'Confirmar'}).click();assert.equal(await page.evaluate(()=>window.syntheticMoneyResult),'456,78');
  await page.evaluate(async()=>{const {moneyPrompt}=await import('/app/assets/privacy.js');window.syntheticMoneyResult=moneyPrompt('Valor (R$)','1234,56')});await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>window.syntheticMoneyResult),null);
});
test('real recurring revenue edit never exposes a native monetary prompt',async()=>{
  const native=[];page.on('dialog',async d=>{native.push(d.message());await d.accept('Descrição sintética')});
  await go('revenue-series-1');await page.locator('[data-action=change-revenue]').click();await page.locator('dialog').getByRole('button',{name:'Continuar'}).click();
  await page.getByRole('heading',{name:'Editar valor',exact:true}).waitFor();await page.waitForFunction(()=>document.querySelector('dialog input[name=amount]').type==='password');assert.equal(await page.locator('dialog input[name=amount]').inputValue(),'1234,56');assert.deepEqual(native,['Descrição']);await page.getByRole('dialog').filter({has:page.getByRole('heading',{name:'Editar valor',exact:true})}).getByRole('button',{name:'Cancelar'}).click();
});
test('baseline counterexample: native monetary prompt and extra materialization dialog predate this change',async()=>{
  const baseline=require('node:child_process').execFileSync('git',['-c','safe.directory='+path.resolve(__dirname,'..').replaceAll('\\','/'),'show','f634d2b7ff9b6616ef2f02624027efb1ac066a99:finance-v17/src/finance_v2/web/completion.js'],{cwd:path.resolve(__dirname,'..'),encoding:'utf8'});
  await page.route('**/app/assets/completion.js',route=>route.fulfill({contentType:'text/javascript',body:baseline}));
  const native=[];page.on('dialog',async d=>{native.push({message:d.message(),value:d.defaultValue()});if(d.message()==='Descrição')await d.accept('Descrição sintética');else await d.dismiss()});
  await go('revenue-series-1');await page.locator('[data-action=change-revenue]').click();await page.locator('dialog').getByRole('button',{name:'Continuar'}).click();
  await page.waitForFunction(()=>document.querySelectorAll('dialog').length===1);
  assert.deepEqual(native,[{message:'Descrição',value:'Recorrência sintética'},{message:'Valor (R$)',value:'1234,56'}]);
  await page.getByRole('heading',{name:'Materializar receitas',exact:true}).waitFor();
  await page.getByRole('dialog').getByRole('button',{name:'Cancelar'}).click();
});

test('cached account values and nested limits respect global privacy without fake wealth',async()=>{
  await page.route('**/api/v2/open-finance/resources?**',route=>route.fulfill({json:{resource:'accounts',total:1,has_more:false,coverage:[{state:'AVAILABLE',record_count:1,page_count:1,observed_at:'2026-10-23T12:00:00Z',omitted_field_count:0}],items:[{connection_id:'itau-test',state:'PRESENT',observed_at:'2026-10-23T12:00:00Z',data:{name:'Conta sintética',balance:1234.56,currencyCode:'BRL',creditData:{creditLimit:2000}}}]}}));
  await go('open-finance');await page.locator('.of-resource-card').waitFor();
  await page.waitForFunction(()=>document.querySelector('[data-private-financial]')?.textContent==='R$ ••••••');
  assert.doesNotMatch(await page.locator('#of-panel-overview').innerText(),/1\.234,56|2\.000,00/);
  await page.locator('#money-privacy-toggle').click();assert.match(await page.locator('#of-panel-overview').innerText(),/1\.234,56/);
  assert.match(await page.locator('#of-panel-overview').innerText(),/não são somados como patrimônio/);
  await page.locator('#money-privacy-toggle').click();assert.doesNotMatch(await page.locator('#of-panel-overview').innerText(),/1\.234,56/);
});

test('six areas, credit filter and observation history are query-only',async()=>{
  await go('open-finance');assert.equal(await page.getByRole('tab').count(),6);
  await page.getByRole('tab',{name:'Cartões',exact:true}).click();await page.locator('#of-panel-cards .empty').waitFor();
  assert(requests.some(r=>r.path.endsWith('/resources')&&r.query.type==='CREDIT'));
  await page.getByRole('tab',{name:'Ativos',exact:true}).click();await page.locator('#of-panel-assets .empty').waitFor();
  await page.locator('#of-panel-assets [name=history]').check();await page.locator('#of-panel-assets [type=submit]').click();
  await page.waitForFunction(()=>document.querySelector('#of-panel-assets .empty'));
  assert(requests.some(r=>r.path.endsWith('/resources')&&r.query.resource==='investments'&&r.query.history==='1'));
});

test('manual cached collection requires explicit confirmation and can be cancelled',async()=>{
  await page.route('**/api/v2/open-finance/catalogs',route=>route.fulfill({json:{...ofCatalog,connections:connections.map((c,i)=>({...c,enabled:i===0}))}}));
  await go('open-finance');await page.getByRole('tab',{name:'Conexões',exact:true}).click();
  page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'Consultar cache: Itaú'}).click();
  assert.match(await page.locator('[data-coverage-progress]').innerText(),/Nenhuma coleta iniciada/);
  assert.equal(requests.filter(r=>r.method==='POST').length,0);
});

test('missing currency never silently becomes BRL or a zero balance',async()=>{
  await page.route('**/api/v2/open-finance/resources?**',route=>route.fulfill({json:{resource:'investments',total:1,has_more:false,coverage:[{state:'NOT_AUTHORIZED',record_count:0,page_count:1,observed_at:'2026-10-23'}],items:[{connection_id:'itau-test',state:'PRESENT',observed_at:'2026-10-23',data:{name:'Ativo sintético',balance:0}}]}}));
  await go('open-finance');await page.locator('.of-resource-card').waitFor();await page.locator('#money-privacy-toggle').click();
  assert.match(await page.locator('#of-panel-overview').innerText(),/Valor indisponível/);
  assert.match(await page.locator('#of-panel-overview').innerText(),/Acesso não autorizado/);
  assert.doesNotMatch(await page.locator('#of-panel-overview').innerText(),/R\$ 0,00/);
});

test('foreign card balances require their own currency instead of inheriting BRL',async()=>{
  await page.route('**/api/v2/open-finance/resources?**',route=>route.fulfill({json:{resource:'accounts',total:1,has_more:false,coverage:[],items:[{connection_id:'itau-test',state:'PRESENT',observed_at:'2026-10-23',data:{name:'Cartão sintético',currencyCode:'BRL',creditData:{creditLimit:1234.56,balanceForeignCurrency:[{balance:1000},{balance:50,currencyCode:'USD'}]}}}]}}));
  await go('open-finance');await page.locator('.of-resource-card').waitFor();await page.locator('#money-privacy-toggle').click();
  const text=await page.locator('#of-panel-overview').innerText();
  assert.match(text,/Valor indisponível/);assert.match(text,/USD 50,00/);assert.match(text,/R\$ 1\.234,56/);assert.doesNotMatch(text,/R\$ 1\.000,00/);
});
