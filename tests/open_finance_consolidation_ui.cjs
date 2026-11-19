const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const {selectPrivacy}=require('./privacy-menu.cjs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  try{
    const origin=process.argv[2],page=await browser.newPage({viewport:{width:1440,height:950}});
    page.setDefaultTimeout(10000);
    const errors=[],calls=[];
    page.on('pageerror',error=>{errors.push(error.message);console.error(error.stack);});
    page.on('request',r=>calls.push(new URL(r.url()).pathname));
    await page.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
    const shots=process.env.OF_CONSOLIDATION_SHOTS;
    async function shot(name){
      if(!shots)return;
      fs.mkdirSync(shots,{recursive:true});
      await page.evaluate(()=>window.scrollTo(0,0));
      await page.screenshot({path:path.join(shots,name+'.png'),animations:'disabled',fullPage:true});
    }
    await page.goto(origin+'/app/unlock');
    await page.locator('input[name=token]').fill('synthetic-owner-only');
    await page.getByRole('button',{name:'Entrar'}).click();
    await page.goto(origin+'/app/#open-finance');
    const overview=page.locator('#of-panel-overview');
    const tab=name=>page.getByRole('tab',{name});
    const header=overview.getByRole('form',{name:'Filtros da visão geral'});
    const select=header.getByLabel('Moeda de apresentação');
    const metric=name=>overview.locator('.of-kpi').filter({has:page.getByRole('button',{name,exact:true})});
    const awaitAmount=async(name,amount)=>{await metric(name).getByText(amount,{exact:false}).first().waitFor();};
    try{await overview.locator('.of-six-kpis').waitFor();}catch(error){console.error(page.url(),await page.locator('body').innerText());throw error;}
    await selectPrivacy(page,'visible');
    if(process.argv.includes('--rounding')){
      const cases=await page.evaluate(async()=>{
        const {bankMoney,money,exchangeRate}=await import('/app/assets/privacy.js');
        return [bankMoney('0','BRL'),bankMoney('-150.245','BRL'),bankMoney('0.0049999','USD'),
          bankMoney('0.005','USD'),bankMoney('9007199254740993.12500000000000000000000000001','BRL'),
          bankMoney('1e-40','USD'),bankMoney('1.995','EUR'),bankMoney(null,'BRL'),
          bankMoney('9.999','BRL'),money(-15025),exchangeRate('4.123456')];
      });
      assert.deepEqual(cases,['R$ 0,00','-R$ 150,25','US$ 0,00','US$ 0,01','R$ 9.007.199.254.740.993,13',
        'US$ 0,00','€ 2,00','Valor indisponível','R$ 10,00','-R$ 150,25','R$ 4,123456']);
      await metric('Investimentos').getByText('R$ 246.487,56',{exact:true}).waitFor();
      const aggregate=page.waitForResponse(response=>response.url().includes('presentation=USD')&&response.url().includes('/analytics'));
      await select.selectOption('USD');
      const data=(await (await aggregate).json()).presentation_view;
      assert(data.investments.amounts.USD.split('.')[1].length>30);
      assert(data.income.credits.amounts.USD.split('.')[1].length>30);
      await metric('Investimentos').getByText('US$ 59.777,75',{exact:true}).waitFor();
      await metric('Rendimentos').getByText('US$ 18,91',{exact:true}).waitFor();
      await overview.locator('.of-allocation-ring').getByText('US$ 59.777,75',{exact:true}).waitFor();
      assert.deepEqual(await overview.locator('.of-chart-axis span').allInnerTexts(),['US$ 27,16','US$ 13,58','US$ 0,00']);
      assert.match(await overview.locator('.of-column.incoming').getAttribute('title'),/US\$ 27,16$/);
      const card=overview.locator('.of-card-insight');
      await card.getByText('Consentimento associado a outro Item',{exact:true}).first().waitFor();
      await card.getByText('Diagnóstico de cartões',{exact:true}).click();
      const diagnostics=card.getByRole('textbox',{name:'Código de saldo, código de limite e quantidade'});
      const copy=await diagnostics.inputValue();
      assert.equal(copy,'FINANCE_V17_CARD_DIAGNOSTICS/1\nCONSENT_ITEM_MISMATCH | CONSENT_ITEM_MISMATCH | 4');
      assert(!/9400|account-CREDIT|consent-039/.test(copy));
      await card.getByRole('button',{name:'Copiar diagnóstico'}).click();
      await card.getByText(/Diagnóstico copiado|Texto selecionado/).waitFor();
      await overview.getByText('Qualidade dos dados',{exact:true}).click();
      await overview.getByText('R$ 4,1234',{exact:false}).first().waitFor();
      for(const width of [390,768,1440]){
        await page.setViewportSize({width,height:950});
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
        if(width===390)await shot('formatacao-usd-mobile');
      }
      await shot('diagnostico-cartoes');
      for(const mode of ['masked','full']){
        await selectPrivacy(page,mode);
        assert(!/59\.777,75|18,91|4,1234/.test(await overview.innerHTML()));
        assert(!/59\.777,75|18,91|4,1234/.test(await overview.ariaSnapshot()));
      }
      await selectPrivacy(page,'visible');
      await select.selectOption('original');
      await metric('Investimentos').getByText('R$ 150.000,00',{exact:true}).waitFor();
      await metric('Investimentos').getByText('US$ 23.400,00',{exact:true}).waitFor();
      assert.deepEqual(errors,[]);
      console.log('PASS: exact money rendering, precision, sanitized card diagnostics and privacy');
      return;
    }
    if(process.argv.includes('--missing-fx')){
      await awaitAmount('Investimentos','150.000,00');
      const broker=overview.locator('.of-position').filter({hasText:'Charles Schwab'});
      assert.deepEqual((await broker.locator('.of-native-value').allInnerTexts()).map(value=>value.replace(/\s+/g,' ')),
        ['US$ 500,00','US$ 23.400,00']);
      await broker.getByText('Referência financeira ausente',{exact:true}).waitFor();
      await broker.getByText('Cotação PTAX indisponível',{exact:true}).waitFor();
      await overview.getByText('Qualidade dos dados',{exact:true}).click();
      await overview.getByText('Valores originais fora da conversão',{exact:false}).waitFor();
      await shot('schwab-moeda-nativa');
      assert.deepEqual(errors,[]);
      console.log('PASS: Schwab keeps native cash and positions when rates or references are missing');
      return;
    }
    await awaitAmount('Investimentos','267.000,00');
    assert.equal(await select.inputValue(),'BRL');
    assert.deepEqual(await overview.locator('.of-kpi-group').evaluateAll(groups=>groups.map(group=>group.children.length)),[3,3]);
    await awaitAmount('Saldo em contas','3.000,00');
    await awaitAmount('Cartões de crédito','500,00');
    const cards=overview.locator('.of-card-insight');
    assert.equal(await cards.locator('.of-card-used-total').innerText(),await metric('Cartões de crédito').locator(':scope > strong').innerText());
    await cards.getByText('12,5%', {exact:false}).waitFor();
    assert.equal(await cards.getByRole('progressbar').getAttribute('value'),'12.5');
    assert.equal(await cards.locator('li').count(),4);
    await cards.getByText('R$ 0,00',{exact:true}).first().waitFor();
    await cards.getByText('9400',{exact:false}).waitFor();
    await overview.getByText('Renda variável',{exact:true}).waitFor();
    const icons=await page.getByRole('navigation',{name:'Principal'}).locator('a svg path').evaluateAll(paths=>paths.map(p=>p.getAttribute('d')));
    assert.equal(icons.length,10);
    assert.equal(new Set(icons).size,10);
    await awaitAmount('Receitas identificadas','112,00');
    await awaitAmount('Despesas identificadas','80,00');
    await awaitAmount('Rendimentos','92,00');
    assert.equal(await overview.getByText('Distribuição geográfica e por moeda').count(),0);
    const institutions=overview.locator('[data-current-positions]');
    assert.equal(await institutions.locator('.of-position').count(),3);
    const schwab=institutions.locator('article').filter({hasText:'Charles Schwab'});
    await schwab.getByText('Caixa em corretora',{exact:true}).waitFor();
    assert.match(await schwab.innerText(),/2\.500,00/);
    assert.match(await schwab.locator('.of-native-value').first().innerText(),/US\$\s*500,00/);
    assert.match(await schwab.innerText(),/US\$\s*500,00/);
    await overview.getByText('Stocks',{exact:true}).waitFor();
    await overview.getByText('REITs',{exact:true}).waitFor();
    await overview.getByText('ETFs',{exact:true}).waitFor();
    await overview.getByText('Não classificado',{exact:true}).waitFor();
    const forecast=overview.locator('.of-portfolio');
    const series=forecast.getByLabel('Instituição da série');
    assert.equal(await series.locator('option').first().innerText(),'Patrimônio consolidado');
    await forecast.locator('.of-portfolio-plot').waitFor();
    await shot('visao-geral-brl');
    const queriesBefore=calls.filter(path=>path.endsWith('/analytics')).length;
    await select.selectOption('USD');
    await awaitAmount('Investimentos','53.400,00');
    await awaitAmount('Cartões de crédito','100,00');
    assert.equal(calls.filter(path=>path.endsWith('/analytics')).length-queriesBefore,1);
    assert.equal(calls.filter(path=>path.endsWith('/portfolio')).length,0);
    await series.selectOption({label:'Charles Schwab'});
    await forecast.getByText('23.400,00',{exact:false}).first().waitFor();
    await shot('visao-geral-usd');
    await select.selectOption('original');
    await awaitAmount('Investimentos','150.000,00');
    await awaitAmount('Investimentos','23.400,00');
    assert.equal(await metric('Investimentos').locator('strong>.of-money-line').count(),2);
    await shot('visao-geral-originais');
    await page.reload();
    await awaitAmount('Investimentos','23.400,00');
    assert.equal(await select.inputValue(),'original');
    await select.selectOption('USD');
    await awaitAmount('Investimentos','53.400,00');
    await overview.getByRole('button',{name:'Ver rendimentos e proventos'}).click();
    const income=page.locator('.of-investment-income');
    await income.getByText('Impostos retidos no exterior',{exact:true}).first().waitFor();
    await income.getByText('Rendimento líquido indisponível',{exact:false}).waitFor();
    await tab('Visão geral').click();
    await awaitAmount('Investimentos','53.400,00');
    await schwab.getByRole('button',{name:'Movimentações'}).click();
    await page.locator('.of-wealth [data-wealth-result]').getByText('Distribuição sintética',{exact:true}).waitFor();
    await tab('Visão geral').click();
    await awaitAmount('Investimentos','53.400,00');
    await schwab.getByRole('button',{name:'Investimentos'}).click();
    await page.locator('.of-wealth').getByText('País de negociação informado',{exact:true}).waitFor();
    await tab('Visão geral').click();
    await awaitAmount('Investimentos','53.400,00');
    await selectPrivacy(page,'masked');
    assert(!/53\.400,00|500,00|100,00/.test(await overview.innerHTML()));
    assert.equal(await cards.getByRole('progressbar').count(),0);
    await selectPrivacy(page,'full');
    assert.equal(await cards.getByText('9400',{exact:false}).count(),0);
    assert.equal(await overview.locator('.of-allocation-ring,.of-portfolio-plot,.of-ranking-track').count(),0);
    assert(!/53\.400,00|500,00|100,00/.test(await overview.innerHTML()));
    await selectPrivacy(page,'visible');
    for(const width of [390,768,1440,1920]){
      await page.setViewportSize({width,height:950});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'width '+width);
      if(width===390){
        await page.getByRole('button',{name:'Abrir menu'}).click();
        await page.getByRole('navigation',{name:'Principal'}).getByRole('link',{name:'Instituições Financeiras'}).waitFor();
        await page.locator('#menu-toggle').click();
        await shot('visao-geral-mobile');
      }
    }
    assert.deepEqual(errors,[]);
    console.log('PASS: global currency, persistence, institution, investments, income, history, privacy and responsive overview');
  }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
