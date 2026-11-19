const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {selectPrivacy} = require('./privacy-menu.cjs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || path.join(
  process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'
));

const origin = process.argv[2];
const baseline = process.env.OF_RECOVERY_BASELINE === '1';
const evidence = process.env.OF_RECOVERY_SHOTS;
const amount = value => value.startsWith('-') ? '-R$ ' + value.slice(1) : 'R$ ' + value;
const shot = async (selector, name) => {
  if (evidence) {
    fs.mkdirSync(evidence, {recursive: true});
    await selector.screenshot({path: path.join(evidence, name + '.png')});
  }
};
const isQuery = request => new URL(request.url()).pathname === '/api/v2/open-finance/analytics';

(async () => {
  const browser = await chromium.launch({headless: true, executablePath:
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    await page.goto(origin + '/app/unlock');
    await page.locator('input[name=token]').fill('synthetic-owner-only');
    await page.getByRole('button', {name:'Entrar'}).click();
    await page.goto(origin + '/app/#open-finance');
    await selectPrivacy(page, 'visible');

    const overview = page.locator('#of-panel-overview');
    const list = overview.locator('.of-card-insight');
    await list.getByText('Cartão de teste 1').first().waitFor();
    const kpi = overview.locator('[data-metric=cards]').locator('xpath=ancestor::article');
    if (baseline) {
      assert.match(await list.innerText(), /Consentimento associado a outro Item/);
      assert.match(await kpi.innerText(), /Indisponível/);
    } else {
      await list.getByText('Última posição conhecida · 20/10/2026').first().waitFor();
      assert.match(await kpi.innerText(), /R\$ 690,00/);
      assert.match(await list.innerText(), /17,25%/);
      assert.equal(await list.locator('progress').count(), 1);
      for (const [value,count] of [['276,25',1],['413,75',1],['0,00',2]]) {
        assert.equal(await list.getByText(amount(value), {exact:true}).count(), count);
      }
    }
    await shot(list, baseline ? 'antes-cartoes' : 'depois-cartoes');

    await page.getByRole('tab', {name:'Cartões'}).click();
    const cards = page.locator('#of-panel-cards');
    await cards.locator('[data-domain-kind=CREDIT_CARD]').last().waitFor();
    if (!baseline) {
      const summaries = cards.locator('.of-product-summary');
      assert.equal(await summaries.getByText('Saldo utilizado', {exact:true}).count(),4);
      assert.equal(await summaries.getByText(amount('0,00'), {exact:true}).count(),2);
      assert.equal(await summaries.getByText(amount('413,75'), {exact:true}).count(),1);
    }
    await cards.locator('[data-domain-child=bills]').first().click();
    const bill = cards.locator('[data-domain-kind=CREDIT_BILL]').first();
    await bill.waitFor();
    if (!baseline) {
      assert.match(await bill.locator('h3').innerText(),/Fatura de cartão/);
      const summary = await bill.locator('.of-product-summary').innerText();
      assert.match(summary,/07\/11\/2026/);
      assert.match(summary,/30\/10\/2026/);
      assert.doesNotMatch(summary,/-03:00/);
      await bill.locator('.of-resource-details summary').first().click();
      assert.match(await bill.locator('.of-resource-details').innerText(),/21:00:00-03:00/);
    }
    await shot(bill,baseline ? 'antes-fatura' : 'depois-fatura');

    await page.getByRole('tab', {name:'Movimentações'}).click();
    const flow = page.locator('#of-panel-flow');
    const form = flow.locator('form.of-overview-filters');
    const rows = flow.locator('.of-flow-item');
    const pagination = flow.locator('.of-pagination').first();
    const status = flow.locator('[data-flow-result]');
    const search = form.locator('input[name=search]');
    const apply = form.getByRole('button',{name:'Aplicar filtros'});
    await form.locator('input[name=start]').fill('2026-10-01');
    await form.locator('input[name=end]').fill('2026-10-31');
    await search.fill('Lote nove');

    async function assertNine(){
      await rows.nth(8).waitFor();
      assert.equal(await rows.count(),9);
      assert.equal(await rows.filter({visible:true}).count(),9);
      const labels = await rows.locator('strong').allTextContents();
      for(let index=0;index<9;index++)assert.ok(labels.includes('Lote nove 0'+index));
      assert.match(await rows.first().innerText(),/Lote nove/);
      assert.match(await rows.first().innerText(),/-R\$ \d+,25/);
      assert.match(await flow.locator('.of-flow-date').first().innerText(),/06\/10\/2026/);
      if(!baseline)assert.equal(await rows.locator('time[datetime]').count(),9);
      assert.match(await pagination.innerText(),/1–9 de 9/);
    }
    const response = page.waitForResponse(r => isQuery(r.request()) && r.url().includes('search=Lote+nove'));
    await apply.click();
    assert.equal((await (await response).json()).items.length,9);
    await assertNine();
    const layout = await pagination.evaluate(nav => {
      window.scrollTo({top:nav.getBoundingClientRect().top + window.scrollY - 180,behavior:'instant'});
      const first = document.querySelector('.of-flow-item').getBoundingClientRect();
      const hit = document.elementFromPoint(first.left + 32, first.top + 20);
      return {position:getComputedStyle(nav).position,height:nav.offsetHeight,
        firstVisible:!!hit?.closest('.of-flow-item'),viewport:innerHeight,top:first.top,hit:hit?.className,scroll:window.scrollY};
    });
    if (baseline) {
      assert.equal(layout.position,'sticky');
      assert.ok(layout.height >= layout.viewport * .85);
      assert.equal(layout.firstVisible,false);
    } else {
      assert.equal(layout.position,'static');
      assert.ok(layout.height < layout.viewport / 3);
      assert.equal(layout.firstVisible,true,JSON.stringify(layout));
    }
    await shot(page,baseline ? 'antes-movimentos-primeira-dobra' : 'depois-movimentos-primeira-dobra');
    await shot(flow,baseline ? 'antes-movimentos-validos' : 'depois-movimentos');

    // A withheld response reproduces loading. The next response deliberately
    // reports totals without delivering the corresponding page.
    let resume;
    const delayed = new Promise(resolve => {resume=resolve});
    await page.route('**/api/v2/open-finance/analytics?**',async route=>{
      if(!route.request().url().includes('search=Lote+nove'))return route.fallback();
      await delayed;
      const original = await route.fetch(), data = await original.json();
      await route.fulfill({response:original,json:{...data,items:[]}});
    },{times:1});
    await apply.click();
    await status.getByText('Carregando movimentações…').waitFor();
    resume();
    await status.getByText('Movimentações encontradas').waitFor();
    assert.equal(await rows.count(),0);
    if (baseline) {
      await status.getByText('Nenhuma movimentação encontrada para os filtros.').waitFor();
    } else {
      await status.getByRole('alert').getByText('MOVEMENTS_RESPONSE_INVALID').waitFor();
    }
    await shot(flow,baseline ? 'antes-movimentos-resposta-inconsistente' : 'depois-movimentos-resposta-inconsistente');

    if (!baseline) {
      await status.getByRole('button',{name:'Tentar novamente'}).click();
      await assertNine();
      await page.route('**/api/v2/open-finance/analytics?**',async route=>{
        const original = await route.fetch(), data = await original.json();
        await route.fulfill({response:original,json:{...data,items:[null,...data.items.slice(1)]}});
      },{times:1});
      await apply.click();
      await status.getByRole('alert').getByText('MOVEMENTS_RENDER_FAILED').waitFor();
      await status.getByRole('button',{name:'Tentar novamente'}).click();
      await assertNine();

      await form.locator('details.of-advanced summary').click();
      await form.locator('select[name=connection_id]').selectOption('synthetic-bank-1');
      await form.locator('select[name=account_id]').selectOption('cash-test');
      await form.locator('select[name=category]').selectOption('pluggy:1');
      await apply.click();
      await assertNine();
      await form.locator('select[name=category]').selectOption('');
      await search.fill('Lote');
      assert.deepEqual(await flow.locator('[data-movement-size] option').evaluateAll(
        nodes=>nodes.map(node=>node.value)),['25','50','100','250','500']);
      await flow.locator('[data-movement-size]').selectOption('25');
      await flow.locator('[data-movement-order]').selectOption('description_asc');
      await apply.click();
      await rows.nth(24).waitFor();
      assert.match(await rows.first().innerText(),/Lote extra 09/);
      assert.match(await rows.last().innerText(),/Lote extra 33/);
      await pagination.getByRole('button',{name:'Próxima'}).click();
      await pagination.getByText(/26–36 de 36/).waitFor();
      assert.equal(await rows.count(),11);
      assert.match(await rows.first().innerText(),/Lote extra 34/);
      assert.match(await rows.last().innerText(),/Lote nove 08/);
      await search.fill('sem correspondência');
      await apply.click();
      await status.getByText('Nenhuma movimentação encontrada para os filtros.').waitFor();

      await search.fill('Lote nove');
      await flow.locator('[data-movement-order]').selectOption('date_desc');
      await flow.locator('[data-movement-group]').selectOption('date');
      await apply.click();
      await assertNine();
      await page.setViewportSize({width:390,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      assert.equal(await pagination.evaluate(nav=>getComputedStyle(nav).position),'static');
      assert.equal(await pagination.isVisible(),true);
      await shot(flow,'depois-movimentos-mobile');
      for(const mode of ['masked','full']){
        await selectPrivacy(page,mode);
        await rows.nth(8).waitFor();
        assert.equal(await rows.count(),9);
        assert.doesNotMatch(await rows.first().ariaSnapshot(),/R\$ \d+,25/);
      }
    }
    assert.deepEqual(errors,[]);
    process.stdout.write('PASS: real WSGI, synthetic SQLite, card and bill presentation, visible movement rows\n');
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error);process.exitCode=1;});
