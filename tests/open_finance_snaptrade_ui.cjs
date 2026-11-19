const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {selectPrivacy}=require('./privacy-menu.cjs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  try{
    const origin=process.argv[2], dir=process.env.OF_SNAPTRADE_SHOTS;
    const page=await browser.newPage({viewport:{width:1440,height:940}});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    page.setDefaultTimeout(8500);
    await page.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
    if(dir)fs.mkdirSync(dir,{recursive:true});
    async function shot(name,component){
      if(!dir)return;
      if(component)await component.screenshot({path:path.join(dir,name+'.png'),animations:'disabled'});
      else await page.screenshot({path:path.join(dir,name+'.png'),animations:'disabled',fullPage:true});
    }
    await page.goto(origin+'/app/unlock');
    await page.locator('input[name=token]').fill('synthetic-snaptrade-browser-owner');
    await page.getByRole('button',{name:'Entrar'}).click();
    await page.goto(origin+'/app/#open-finance');
    const overview=page.locator('.of-wealth-overview');
    const portfolio=page.locator('.of-wealth');
    const result=portfolio.locator('[data-wealth-result]');
    const connections=page.locator('.of-snaptrade-connections');
    await overview.getByText('Distribuição geográfica e por moeda').waitFor();
    await selectPrivacy(page,'visible');
    assert.match(await overview.innerText(),/20\.000,00/);
    await shot('visao-geral-moedas-originais');
    const presentation=overview.getByLabel('Moeda de apresentação');
    await presentation.selectOption('BRL');
    await overview.getByText('Posições convertidas').waitFor();
    assert.match(await overview.innerText(),/200\.000,00/);
    await shot('visao-geral-brl');
    await presentation.selectOption('USD');
    await overview.getByText('40.000,00',{exact:false}).first().waitFor();
    await shot('visao-geral-usd');
    await overview.getByRole('button',{name:'Ver carteira unificada'}).press('Enter');
    await result.getByText('ACME',{exact:true}).waitFor();
    await portfolio.getByText('Filtros e ordenação',{exact:true}).click();
    await portfolio.locator('[name=start]').fill('2026-10-01');
    await portfolio.locator('[name=end]').fill('2026-10-20');
    await shot('carteira-unificada');
    await result.locator('article').filter({hasText:'ACME'}).getByRole('button',{name:'Ver posição'}).press('Enter');
    const detail=result.locator('[data-wealth-detail]');
    assert.equal(await detail.evaluate(element=>document.activeElement===element),true);
    await shot('detalhe-de-posicao',detail);
    await detail.getByRole('button',{name:'Histórico da posição'}).click();
    await result.getByText('Histórico patrimonial em formação.').waitFor();
    await shot('historico',result);
    const activityResponse=page.waitForResponse(response=>response.url().includes('view=activities'));
    await detail.getByRole('button',{name:'Operações do ativo'}).click();
    const operationResponse=await activityResponse;
    const debug=await operationResponse.json();
    assert.equal(debug.total,11,JSON.stringify({url:operationResponse.url(),data:debug}));
    await result.getByText('Distribuição sintética',{exact:true}).waitFor();
    await shot('atividades',result);
    await detail.getByRole('button',{name:'Proventos do ativo'}).click();
    await result.getByText('Dividendo',{exact:true}).waitFor();
    await shot('proventos',result);
    await detail.getByRole('button',{name:'Voltar à carteira'}).click();
    await result.getByText('ACME',{exact:true}).waitFor();
    await selectPrivacy(page,'masked');
    assert.doesNotMatch(await result.innerHTML(),/20\.000,00|100\.000,00/);
    await shot('ocultar-valores');
    await selectPrivacy(page,'full');
    assert.deepEqual(await portfolio.locator('[name=sort] option').evaluateAll(nodes=>nodes.map(node=>node.disabled)),[false,true,true]);
    assert.doesNotMatch(await result.innerHTML(),/20\.000,00|100\.000,00/);
    await shot('privacidade-total');
    await selectPrivacy(page,'visible');
    await portfolio.getByText('Filtros e ordenação',{exact:true}).click();
    for(const width of [390,768,1440,1920]){
      await page.setViewportSize({width,height:940});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'viewport '+width);
      await shot('carteira-'+width);
    }
    const tabs=page.getByRole('tablist',{name:'Áreas do Open Finance'});
    await tabs.getByRole('tab',{name:'Investimentos'}).focus();
    await page.keyboard.press('End');
    const active=tabs.getByRole('tab',{name:'Conexões'});
    assert.equal(await active.getAttribute('aria-selected'),'true');
    assert.equal(await active.evaluate(element=>document.activeElement===element),true);
    await connections.getByRole('heading',{name:'Charles Schwab'}).waitFor();
    await connections.getByText('Contas e diagnóstico',{exact:true}).first().click();
    assert.doesNotMatch(await connections.innerHTML(),/901938475612|canary-fixture-/);
    await shot('conexoes',connections);
    const preferences=connections.getByRole('form',{name:'Preferências SnapTrade'});
    await preferences.getByLabel('Intervalo SnapTrade').selectOption('6');
    await preferences.getByRole('button',{name:'Salvar configuração'}).click();
    await connections.getByText('Operação concluída.').waitFor();
    assert.equal(await preferences.getByLabel('Intervalo SnapTrade').inputValue(),'6');
    await shot('configuracao-da-coleta',preferences);
    await page.route('**/api/v2/open-finance/snaptrade',async route=>{
      const response=await route.fetch(),data=await response.json();
      data.error_code='SNAPTRADE_RATE_LIMIT';
      await route.fulfill({response,json:data});
    },{times:1});
    await connections.getByRole('button',{name:'Testar credenciais e descobrir contas'}).click();
    await connections.getByText(/Limite de chamadas/).waitFor();
    await shot('limite-de-chamadas',connections);
    await tabs.getByRole('tab',{name:'Investimentos'}).click();
    await result.getByText('ACME',{exact:true}).waitFor();
    const ratio=await portfolio.getByRole('heading',{name:'Carteira unificada'}).evaluate(heading=>{
      const channels=value=>value.match(/[\d.]+/g)?.map(Number);
      const luminance=rgb=>rgb.slice(0,3).map(x=>x/255).map(x=>x<=0.04045?x/12.92:((x+0.055)/1.055)**2.4)
        .reduce((sum,x,i)=>sum+x*[0.2126,0.7152,0.0722][i],0);
      const color=luminance(channels(getComputedStyle(heading).color));
      let background=1;
      for(let node=heading;node;node=node.parentElement){
        const rgb=channels(getComputedStyle(node).backgroundColor);
        if(rgb?.length===3||rgb?.[3]===1){background=luminance(rgb);break;}
      }
      return (Math.max(color,background)+0.05)/(Math.min(color,background)+0.05);
    });
    assert.ok(ratio>=4.5,'portfolio heading contrast '+ratio);
    await portfolio.getByText('Filtros e ordenação',{exact:true}).click();
    await portfolio.getByLabel('Buscar').fill('sem correspondência sintética');
    await portfolio.getByRole('button',{name:'Aplicar'}).click();
    await result.getByText('Nenhum registro para o escopo.').waitFor();
    await shot('carteira-vazia');
    await page.route('**/api/v2/open-finance/portfolio?*',async route=>{
      const response=await route.fetch(),data=await response.json();
      data.summary.partial_resources=true;
      await route.fulfill({response,json:data});
    },{times:1});
    await portfolio.getByLabel('Buscar').fill('');
    await portfolio.getByRole('button',{name:'Aplicar'}).click();
    await result.getByText(/Há dados parciais/).waitFor();
    await shot('carteira-parcial');
    assert.deepEqual(errors,[]);
    console.log('PASS: WSGI, unified portfolio, BRL/USD, asset detail, privacy, responsive layout and broker diagnostics');
  }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
