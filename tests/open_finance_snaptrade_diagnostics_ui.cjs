const assert=require('node:assert/strict');
const path=require('node:path');
const {selectPrivacy}=require('./privacy-menu.cjs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  try{
    const origin=process.argv[2],page=await browser.newPage();
    await page.context().grantPermissions(['clipboard-read','clipboard-write'],{origin});
    page.setDefaultTimeout(8500);
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
    await page.goto(origin+'/app/unlock');
    await page.locator('input[name=token]').fill('synthetic-local-owner-037');
    await page.getByRole('button',{name:'Entrar'}).click();
    await page.goto(origin+'/app/#open-finance');
    await page.getByRole('tab',{name:'Conexões'}).click();
    const section=page.locator('.of-snaptrade-connections');
    const discovery=section.getByRole('button',{name:'Testar credenciais e descobrir contas'});
    const feedback=section.locator('[data-snaptrade-feedback]');
    await discovery.waitFor();
    let posted;
    await page.route('**/api/v2/open-finance/snaptrade/discovery',async route=>{
      const response=await route.fetch();
      assert.equal(response.status(),502);
      posted=await response.json();
      await route.fulfill({status:502,contentType:'text/html',body:'<p>proxy-private-fixture-value-037</p>'});
    },{times:1});
    await discovery.click();
    await feedback.getByText(/A SnapTrade devolveu dados fora do formato esperado/).waitFor();
    const panel=section.locator('[data-snap-diagnosis]');
    await panel.getByText('Diagnóstico técnico').press('Enter');
    assert.equal(await panel.evaluate(details=>details.open),true);
    await panel.getByText(posted.request_id,{exact:true}).waitFor();
    assert.match(await section.innerText(),/Resultado da última tentativa Falha na leitura/);
    for(const mode of ['visible','masked','full']){
      await selectPrivacy(page,mode);
      await panel.getByRole('button',{name:'Copiar diagnóstico'}).click();
      const copied=JSON.parse(await page.evaluate(()=>navigator.clipboard.readText()));
      assert.equal(copied.request_id,posted.request_id);
      assert.equal(copied.resource,'ACCOUNTS');
      assert.equal(copied.field,'results');
      assert.equal(copied.remote_status,200);
      assert.doesNotMatch(JSON.stringify(copied),/proxy-private|canary-fixture|901938475612|62000000-/);
    }
    assert.doesNotMatch(await section.innerHTML(),/proxy-private|canary-fixture|901938475612/);
    await page.route('**/api/v2/open-finance/snaptrade/discovery',route=>route.fulfill({
      status:502,contentType:'application/json',body:JSON.stringify({detail:'untrusted proxy message'})
    }),{times:1});
    await discovery.click();
    await feedback.getByText(/Não foi possível confirmar a operação/).waitFor();
    assert.doesNotMatch(await section.innerHTML(),/untrusted proxy message/);
    assert.deepEqual(errors,[]);
    console.log('PASS: proxy substitution, authenticated status, correlation, clipboard, and three privacy levels');
  }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
