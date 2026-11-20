const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {selectPrivacy}=require('./privacy-menu.cjs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||path.join(
  process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const origin=process.argv[2];
const baseline=process.env.OF_042_BASELINE==='1';
const evidence=process.env.OF_042_SHOTS;

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
    const shots=async(node,name)=>{
      if(!evidence)return;
      fs.mkdirSync(evidence,{recursive:true});
      await node.screenshot({path:path.join(evidence,name+'.png')});
    };
    async function brand(){
      const header=page.locator('img.brand-mark').first();
      await header.waitFor();
      await page.waitForFunction(()=>document.querySelector('img.brand-mark')?.naturalWidth>0);
      const icons=await page.locator('head link[rel=icon],head link[rel=apple-touch-icon]').evaluateAll(
        links=>links.map(link=>({rel:link.rel,href:link.getAttribute('href'),sizes:link.getAttribute('sizes')})));
      assert.deepEqual(icons.map(icon=>icon.sizes),['any','16x16','32x32','48x48','180x180']);
      for(const icon of icons){
        assert.match(icon.href,/^\/app\/assets\/finance-v17.*\?v=042$/);
        const response=await page.request.get(origin+icon.href);
        assert.equal(response.status(),200);
        if (icon.sizes==='any'){
          assert.match(response.headers()['content-type'],/image\/svg\+xml/);
          assert.match(await response.text(),/#005b3c/);
        }else{
          assert.equal(response.headers()['content-type'],'image/png');
          const [w,h]=icon.sizes.split('x').map(Number),png=await response.body();
          assert.equal(png.readUInt32BE(16),w);
          assert.equal(png.readUInt32BE(20),h);
        }
      }
    }
    await page.goto(origin+'/app/unlock');
    if(!baseline){
      await brand();
      await shots(page.locator('.unlock-card'),'identidade-autenticacao');
    }
    await page.locator('input[name=token]').fill('synthetic-owner-only');
    await Promise.all([page.waitForURL(origin+'/app/'),page.getByRole('button',{name:'Entrar'}).click()]);
    await page.goto(origin+'/app/#open-finance');
    if(!baseline){
      await brand();
      await shots(page.locator('.app-header'),'identidade-cabecalho');
    }
    await selectPrivacy(page,'visible');
    const money=text=>text.replaceAll('\u00a0',' ');
    const overview=page.locator('#of-panel-overview');
    const cards=overview.locator('.of-card-insight');
    await cards.getByText('Cartão de teste 1').first().waitFor();
    const kpi=overview.locator('[data-metric=cards]').locator('xpath=ancestor::article');
    if (baseline){
      assert.match(await kpi.innerText(),/Indisponível/);
      assert.match(money(await cards.innerText()),/Saldo em aberto · R\$ 123,45/);
    }else{
      const main=cards.locator('.of-card-open-total');
      assert.equal(money(await main.innerText()),'R$ 365,00');
      assert.equal(money(await kpi.locator(':scope > strong').innerText()),'R$ 365,00');
      assert.match(await kpi.innerText(),/Cobertura parcial.*19\/10\/2026 a 20\/10\/2026/);
      const amounts=(await cards.locator('[data-card-open-balance]').allInnerTexts()).map(money).sort();
      assert.deepEqual(amounts,['R$ 0,00','R$ 0,00','R$ 123,45','R$ 241,55']);
      assert.equal(await cards.locator('progress').count(),0);
      assert.equal(await cards.getByText('Limite consolidado').count(),0);
    }
    await shots(cards,baseline?'antes-saldo-aberto':'depois-saldo-aberto');
    if(!baseline){
      const select=overview.locator('select[name=presentation]');
      await select.selectOption('USD');
      await cards.locator('.of-card-open-total').getByText(/85,08/).waitFor();
      assert.equal(money(await kpi.locator(':scope > strong').innerText()),'US$ 85,08');
      await selectPrivacy(page,'full');
      await page.waitForFunction(()=>document.documentElement.dataset.financePrivacy==='full');
      assert.doesNotMatch(await cards.ariaSnapshot(),/365,00|85,08|123,45|241,55/);
      await selectPrivacy(page,'visible');
      await page.getByRole('tab',{name:'Cartões'}).click();
      const detail=page.locator('#of-panel-cards .of-product-summary');
      await detail.last().waitFor();
      assert.equal(await detail.getByText('Saldo em aberto',{exact:true}).count(),4);
      assert.equal(await detail.getByText('R$ 0,00',{exact:true}).count(),2);
      assert.equal(await detail.getByText('R$ 123,45',{exact:true}).count(),1);
      await shots(page.locator('#of-panel-cards .of-resource-card').first(),'saldo-aberto-detalhado');
    }

    await page.getByRole('tab',{name:'Conexões'}).click();
    const panel=page.locator('#of-panel-connections');
    const santander=panel.locator('[data-connection-id=synthetic-bank-2]');
    const archived=panel.locator('[data-connection-id=archived-fixture]');
    if (baseline){
      assert.equal(await santander.locator('[data-connection-auto]').count(),0);
      await shots(santander,'antes-santander');
    }else{
      const enabled=santander.getByRole('button',{name:'Habilitar coleta automática'});
      const paused=santander.getByRole('button',{name:'Pausar coleta automática'});
      await enabled.waitFor();
      assert.equal(await archived.isVisible(),false);
      await panel.getByText('Conexões arquivadas (1)',{exact:true}).click();
      await archived.waitFor();
      assert.equal(await archived.locator('[data-connection-auto]').count(),0);
      assert.match(await archived.innerText(),/Arquivada/);
      await enabled.click();
      await paused.waitFor();
      assert.match(await santander.innerText(),/Próxima coleta local prevista\s+\d{2}\/\d{2}\/\d+/);
      const schedule=await (await page.request.get(origin+'/api/v2/open-finance/sync-preferences')).json();
      const row=schedule.connections.find(item=>item.connection_id==='synthetic-bank-2');
      assert.equal(row.effective,true);
      assert.equal(Date.parse(row.next_attempt)-Date.parse(row.last_success),24*3600000);
      await shots(santander,'depois-santander-ativo');
      await page.reload();
      await page.getByRole('tab',{name:'Conexões'}).click();
      await paused.waitFor();
      await paused.click();
      await enabled.waitFor();
      await page.setViewportSize({width:390,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      assert.ok(await page.locator('img.brand-mark').isVisible());
      await shots(santander,'depois-santander-mobile');
      const noCookie=await browser.newContext();
      try{
        const forged=await noCookie.request.post(origin+'/api/v2/open-finance/registry/auto-sync',
          {headers:{Authorization:'Bearer synthetic-owner-only',Origin:origin},data:{
            connection_id:'synthetic-bank-2',revision:2,enabled:true,confirmed:true}});
        assert.equal(forged.status(),403);
      }finally{await noCookie.close();}
    }
    assert.deepEqual(errors,[]);
    console.log('PASS: native open balances, connection policy, branding and scope in WSGI');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
