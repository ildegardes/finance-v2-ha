const {selectPrivacy}=require('./privacy-menu.cjs');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));

const connection = (id, institution, enabled = true) => ({id, institution, enabled, historical: !enabled});
const connections = [
  connection('santander', 'Santander - Banco Santander Pessoa Física'),
  connection('itau', 'Itaú - itau'),
  connection('santander-antigo', 'Santander', false),
];
const position = (value, state, items = []) => ({value, coverage_state: state, items, known: value == null ? 0 : 1});
const response = {
  positions: {
    accounts: {...position('19840.55', 'PARTIAL'),known:2},
    investments: {...position('27482.80', 'PARTIAL'), known:3, by_class: [
      {type:'FIXED INCOME', value:'18450.00'},
      {type:'EQUITY', value:'6720.45'},
      {type:'MUTUAL FUND', value:'2312.35'},
      {type:'MYSTÈRE', value:null, unavailable:1},
    ]},
  },
  institutions: [
    {connection_id:'santander',current:true,accounts:position('19840.55','COMPLETE',[{name:'Conta corrente',value:'19840.55',observed_at:'2026-10-30T12:00:00Z',provider_updated_at:'2026-10-29T08:00:00Z',freshness:{state:'STALE'}}]),
      investments:position('27482.80','PARTIAL',[{name:'Carteira de investimentos',value:'27482.80',observed_at:'2026-10-30T12:00:00Z',provider_updated_at:'2026-10-28T11:00:00Z',reference_date:'2026-10-26'}])},
    {connection_id:'itau',current:true,accounts:position('0','COMPLETE'),investments:position(null,'NOT_AVAILABLE')},
  ],
  flow: {BANK:{coverage_state:'PARTIAL',reported:{incoming:'14250.50',outgoing:'7523.55'},observed_net:'6726.95'}},
  series: [
    ['02','incoming','2800.00'],['03','outgoing','1650.00'],['09','incoming','3260.50'],
    ['10','outgoing','2260.45'],['14','incoming','3190.00'],['16','outgoing','1250.00'],
    ['23','incoming','5000.00'],['24','outgoing','2363.10'],
  ].map(([day,direction,value])=>({date:'2026-10-'+day,product:'BANK',direction,value})),
  category_ranking: {BANK:[
    {key:'pluggy:transfer',name:'Same person transfer',value:'3200.00'},
    {key:'pluggy:electr',name:'Electricity',value:'1600.55'},
    {key:'pluggy:books',name:'Bookstore',value:'1505.00'},
    {key:'pluggy:school',name:'Kindergarten',value:'850.00'},
    {key:'pluggy:services',name:'Services',value:'300.00'},
    {key:'missing',name:'Sem categoria',value:'68.00'},
  ]},
  coverage:[{resource:'transactions',state:'FAILED',observed_at:'2026-10-30T12:00:00Z'}],
};
const empty = {
  positions:{accounts:position(null,'NOT_ESTABLISHED'),investments:position(null,'NOT_ESTABLISHED')},
  flow:{BANK:{coverage_state:'NOT_ESTABLISHED',reported:{incoming:null,outgoing:null}}},
  institutions:[],series:[],category_ranking:{BANK:[]},coverage:[],
};

(async()=>{
  const browser = await chromium.launch({headless:true, executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  try{
    const page = await browser.newPage({viewport:{width:1440,height:980}});
    const errors = [];
    page.on('pageerror',error=>errors.push(error.message));
    const web = path.resolve('finance-v17/src/finance_v2/web');
    await page.route('http://synthetic.local/**',async route=>{
      const pathname = new URL(route.request().url()).pathname;
      if(pathname==='/'){
        const body = '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/open-finance.css"></head><body><button id="money-privacy-toggle">Privacidade</button><main><header class="page-header"><div><h1>Open Finance</h1><p>Dados bancários importados</p></div></header><section id="host"><section id="of-panel-overview"></section></section></main></body></html>';
        return route.fulfill({contentType:'text/html',body});
      }
      const filename=path.join(web,path.basename(pathname));
      return fs.existsSync(filename)?route.fulfill({contentType:pathname.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync(filename,'utf8')}):route.fulfill({status:404});
    });
    async function mount(mode=null){
      await page.goto('http://synthetic.local/');
      await page.evaluate(async ({connections,response,empty,mode})=>{
        const {installPrivacy,PRIVACY_KEY}=await import('/privacy.js');
        if(mode!==null)localStorage.setItem(PRIVACY_KEY,mode);
        installPrivacy();
        const {mountAnalyticsOverview}=await import('/open-finance.js');
        const {classLabel,categoryLabel,statusLabel}=await import('/open-finance-labels.js');
        window.labels=[classLabel('  fIxEd_inCoMe  '),classLabel('éΩ!'),classLabel(null),categoryLabel({name:'Saúde'}),categoryLabel({name:'Bookstore'}),statusLabel('posted'),categoryLabel({name:'42',has_name:false})];
        window.calls=[];window.delayed=[];window.strategy='normal';
        const esc=text=>String(text).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
        mountAnalyticsOverview({
          host:document.querySelector('#host'),catalog:{connections},esc,today:'2026-10-31',
          state:{},onNavigate:context=>window.navigationResult=context,onAssets:context=>window.assetResult=context,
          api:url=>{
            const query=new URL(url,location.origin).searchParams;window.calls.push(Object.fromEntries(query));
            if(window.strategy==='error')return Promise.reject(new Error('HTTP 503'));
            if(window.strategy==='empty')return Promise.resolve(empty);
            if(window.strategy==='delayed')return new Promise(resolve=>window.delayed.push(()=>resolve(query.get('connection_id')==='itau'?empty:response)));
            return Promise.resolve(response);
          },
        });
      },{connections,response,empty,mode});
      await page.locator('.of-kpi').first().waitFor();
    }
    await mount('false');
    assert.equal(await page.locator('html').getAttribute('data-finance-privacy'),'full');
    assert.equal(await page.locator('.of-kpi').count(),6);
    assert.equal(await page.locator('[data-position-connection]').count(),2);
    assert.equal(await page.locator('select[name=connection_id] option[value=santander-antigo]').count(),0);
    const assertFull=async()=>{
      assert.equal(await page.locator('.of-column,.of-chart-axis,.of-allocation-ring,.of-ranking-track').count(),0);
      assert.doesNotMatch(await page.locator('#of-panel-overview').ariaSnapshot(),/R\$|\d+(?:,\d+)?\s*%/);
      assert.doesNotMatch(await page.locator('#of-panel-overview').innerHTML(),/--height:|conic-gradient|19\.840,55/);
    };
    await assertFull();
    assert.deepEqual(await page.evaluate(()=>window.labels),['Renda fixa','Classe não identificada','Classe não informada','Saúde','Livrarias','Efetivada','Categoria não identificada']);
    await selectPrivacy(page,'visible');
    assert.equal(await page.locator('.of-kpi').first().locator('strong').innerText(),'R$ 19.840,55');
    assert.equal(await page.locator('.of-net-value').innerText(),'R$ 6.726,95');
    assert.equal(await page.locator('.of-column').count(),8);
    assert.equal(await page.locator('.of-allocation-ring').count(),1);
    await page.getByRole('button',{name:'Transferência entre contas próprias'}).click();
    assert.equal(await page.evaluate(()=>window.navigationResult.effective_key),'pluggy:transfer');
    assert.equal(await page.evaluate(()=>window.navigationResult.direction),'outgoing');
    await page.getByRole('button',{name:'Renda fixa'}).click();
    assert.equal(await page.evaluate(()=>window.assetResult.type),'FIXED INCOME');
    await page.locator('.of-column').first().focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(()=>window.navigationResult.start),'2026-10-01');
    assert.equal(await page.evaluate(()=>window.navigationResult.end),'2026-10-04');
    await page.getByText('Ver dados do gráfico em texto').click();
    assert.match(await page.locator('.of-chart-alternative').innerText(),/sem registro/);
    await page.getByText('Ver dados do gráfico em texto').click();
    const labels = await page.locator('#of-panel-overview select,#of-panel-overview input').evaluateAll(nodes=>nodes.every(node=>node.labels.length||node.getAttribute('aria-label')));
    assert.ok(labels);
    const output=process.env.OF_OVERVIEW_SHOTS;
    if(output)fs.mkdirSync(output,{recursive:true});
    const capture=async(name)=>{
      if(output)await page.screenshot({path:path.join(output,name+'.png'),fullPage:true,animations:'disabled'});
    };
    for(const width of [390,768,1440,1920]){
      await page.setViewportSize({width,height:980});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'horizontal overflow at '+width);
      await capture('visao-geral-'+width);
    }
    await page.setViewportSize({width:1440,height:980});
    await page.getByText('Qualidade dos dados',{exact:true}).click();
    await page.locator('[data-position-connection=santander]').getByText('Ver posições e datas').click();
    await capture('cobertura-parcial');
    await selectPrivacy(page,'masked');
    assert.equal(await page.locator('.of-column').count(),8);
    assert.equal(await page.locator('.of-chart-axis').count(),0);
    assert.doesNotMatch(await page.locator('.of-column').first().getAttribute('title'),/R\$/);
    assert.doesNotMatch(await page.locator('#of-panel-overview').ariaSnapshot(),/R\$/);
    await capture('ocultar-valores');
    await mount();
    assert.equal(await page.locator('html').getAttribute('data-finance-privacy'),'masked');
    await selectPrivacy(page,'full');
    await assertFull();
    await capture('privacidade-total');
    await page.getByLabel('Período',{exact:true}).selectOption('year');
    await page.waitForFunction(()=>window.calls.at(-1)?.start==='2026-01-01');
    assert.equal(await page.evaluate(()=>window.calls.at(-1).end),'2026-10-31');
    await page.getByRole('button',{name:'Período anterior',exact:true}).click();
    await page.waitForFunction(()=>window.calls.at(-1)?.start==='2025-01-01');
    assert.equal(await page.evaluate(()=>window.calls.at(-1).end),'2025-12-31');
    await page.getByLabel('Período',{exact:true}).selectOption('month');
    await page.getByRole('button',{name:'Período anterior',exact:true}).click();
    await page.waitForFunction(()=>window.calls.at(-1)?.start==='2026-09-01');
    assert.equal(await page.evaluate(()=>window.calls.at(-1).end),'2026-09-30');
    await page.locator('select[name=connection_id]').selectOption('!history');
    await page.getByRole('button',{name:'Aplicar',exact:true}).click();
    await page.getByText(/O fluxo inclui conexões arquivadas/).waitFor();
    assert.equal(await page.evaluate(()=>window.calls.at(-1).history),'1');
    await page.evaluate(()=>window.strategy='delayed');
    await page.locator('select[name=connection_id]').selectOption('santander');
    await page.getByRole('button',{name:'Aplicar',exact:true}).click();
    await page.locator('select[name=connection_id]').selectOption('itau');
    await page.getByRole('button',{name:'Aplicar',exact:true}).click();
    await page.locator('[aria-busy=true]').waitFor();
    await page.evaluate(()=>window.delayed[1]());
    await page.getByText('Nenhuma conexão ativa neste escopo.').waitFor();
    await page.evaluate(()=>window.delayed[0]());
    assert.equal(await page.locator('[data-position-connection]').count(),0);
    await selectPrivacy(page,'visible');
    await capture('vazio');
    await page.evaluate(()=>window.strategy='error');
    await page.getByRole('button',{name:'Aplicar',exact:true}).click();
    await page.getByRole('alert').waitFor();
    await capture('erro');
    await page.evaluate(()=>window.strategy='normal');
    await page.getByRole('button',{name:'Tentar novamente'}).click();
    await page.locator('.of-kpi').first().waitFor();
    assert.deepEqual(errors,[]);
    process.stdout.write('PASS: overview, placement, contextual filters, keyboard, all privacy modes, load race and HTTP retry\n');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
