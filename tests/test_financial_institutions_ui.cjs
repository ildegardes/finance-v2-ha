const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));

const web = path.resolve(__dirname, '../finance-v17/src/finance_v2/web');
const assets = new Set(['financial-institutions.js', 'privacy.js', 'open-finance-errors.js', 'open-finance-status.js',
  'open-finance.js', 'open-finance-flow.js', 'open-finance-coverage.js', 'open-finance-domain.js',
  'santander-binding-recovery.js', 'navigation.js', 'query-generation.js']);
let server, browser, origin;

before(async () => {
  server = http.createServer((request, response) => {
    const name = request.url.slice(1);
    if (!name) {
      response.setHeader('Content-Type', 'text/html; charset=utf-8');
      response.end('<main></main>');
    } else if (assets.has(name)) {
      response.setHeader('Content-Type', 'text/javascript');
      response.end(fs.readFileSync(path.join(web, name)));
    } else {
      response.writeHead(404).end();
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = 'http://127.0.0.1:' + server.address().port;
  browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
});

async function fixture(t, writable) {
  const context = await browser.newContext();
  t.after(() => context.close());
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const page = await context.newPage();
  await page.goto(origin);
  await page.evaluate(async available => {
    const {showFinancialInstitutions} = await import('/financial-institutions.js');
    window.calls = [];
    window.active = true;
    let dispose;
    window.leave = () => { window.active = false; dispose(); };
    const rows = [{id: 'santander', institution: 'Santander', lifecycle: 'ACTIVE',
      enabled: true, revision: 0, sync_state: 'FAILED', staged_account_count: 4,
      observed_resources: ['accounts', 'bills', 'unexpected'] }];
    const api = async (route, options) => {
      calls.push({route, method: options?.method || 'GET'});
      if (route === '/open-finance/connections') return {registry_admin_available: available, connections: rows};
      if (route.startsWith('/open-finance/sync-runs?')) return {items: [{
        state: 'FAILED', started_at: '2026-11-01T12:00:00Z', error_code: 'AUTH_FAILED',
      }], has_more: route.includes('page=1&')};
      if (route.endsWith('/details')) return {institution: 'Santander', lifecycle: 'ACTIVE', sync_state: 'FAILED', revision: 0};
      if (route.endsWith('/connectors')) return {connectors: [{id: 200, name: 'MeuPluggy'}], catalog_complete: false};
      if (route.endsWith('/archive/inspect')) return {dependencies: 'NO_FINANCIAL_ROWS_WITH_HISTORY'};
      if (route.endsWith('/archive')) {
        const row = rows.find(row => row.id === options.body.connection_id);
        if (!row || row.revision !== options.body.revision || !options.body.confirmed) throw Error('Unexpected archive request');
        Object.assign(row, {lifecycle: 'ARCHIVED', enabled: false, revision: row.revision + 1});
        return {};
      }
      if (route.endsWith('/drafts')) {
        if (![undefined, 'santander'].includes(options.body.replaces_id) || options.body.client_secret !== 'synthetic-secret') {
          throw Error('Unexpected draft request');
        }
        rows.push({id: 'conn-fixture', institution: options.body.label, lifecycle: 'DRAFT',
          enabled: false, revision: 0, replaces_id: options.body.replaces_id, source: 'MANAGED'});
        return {};
      }
      if (route.endsWith('/activate')) {
        const row = rows.find(row => row.id === options.body.connection_id);
        if (!row || row.revision !== options.body.revision || !options.body.confirmed) throw Error('Unexpected activation');
        window.activationConnector = options.body.connector_id;
        Object.assign(row, {lifecycle: 'ACTIVE', enabled: true, revision: row.revision + 1});
        return {};
      }
      if (route.endsWith('/validate')) {
        if (!options.body.confirmed) throw Error('Missing validation confirmation');
        return {item_verified: true, capabilities_state: 'PARTIAL',
          capabilities: [{type: 'ACCOUNT', status: 'AVAILABLE'}, {type: 'PRIVATE_VALUE', status: 'AVAILABLE'}]};
      }
      if (route.endsWith('/rename') || route.endsWith('/disable')) {
        const row = rows.find(row => row.id === options.body.connection_id);
        if (!row || row.revision !== options.body.revision) throw Error('Unexpected revision');
        if (route.endsWith('/rename')) row.institution = options.body.label;
        else Object.assign(row, {lifecycle: 'DISABLED', enabled: false});
        row.revision += 1;
        return {};
      }
      if (route.endsWith('/rotate-credentials')) {
        const body = options.body;
        if (body.connection_id !== 'conn-fixture' || body.revision !== 0 || body.confirmed !== true
            || body.client_id !== 'synthetic-client' || body.client_secret !== 'rotated-secret'
            || Object.hasOwn(body, 'item_id')) throw Error('Unexpected rotation');
        rows[1].revision = 1;
        return {};
      }
      if (route.endsWith('/delete/inspect') || route.endsWith('/delete')) {
        const index = rows.findIndex(row => row.id === options.body.connection_id);
        const row = rows[index];
        if (!row || row.lifecycle !== 'ARCHIVED' || row.revision !== options.body.revision) throw Error('Unexpected deletion');
        if (route.endsWith('/inspect')) return {eligible: true};
        if (!options.body.backup_confirmed || options.body.confirmation !== 'EXCLUIR DEFINITIVAMENTE') throw Error('Missing confirmation');
        rows.splice(index, 1);
        return {};
      }
      throw Error('Unexpected request');
    };
    await showFinancialInstitutions({
      api, view: document.querySelector('main'), heading: () => {},
      navigation: {current: () => window.active, onDispose: callback => { dispose = callback; }},
    });
  }, writable);
  return page;
}

test('shows private details and sends the selected connector on activation', async t => {
  const page = await fixture(t, true);
  await page.getByRole('button', {name: 'Ver detalhes'}).click();
  await page.getByText(/Revisão 0/).waitFor();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Desativar', exact: true}).click();
  await page.getByRole('button', {name: 'Consultar conectores'}).click();
  await page.getByLabel('Conector para validar na ativação').selectOption('200');
  await page.getByText(/Catálogo parcial/).waitFor();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Validar e reativar'}).click();
  await page.getByRole('status').filter({hasText: 'Conexão ativada'}).waitFor();
  assert.equal(await page.evaluate(() => activationConnector), 200);
});

test('shows staged account count and allowlisted observed resources', async t => {
  const page = await fixture(t, false);
  await page.getByText(/Contas registradas: 4/).waitFor();
  await page.getByText(/Recursos observados: Contas, Faturas/).waitFor();
  assert.equal(await page.getByText(/unexpected/).count(), 0);
});

test('public owner view is read-only for administration', async t => {
  const page = await fixture(t, false);
  assert(await page.getByRole('button', {name: 'Adicionar instituição'}).isHidden());
  assert.equal(await page.getByRole('button', {name: 'Arquivar'}).count(), 0);
  assert.deepEqual(await page.evaluate(() => calls.map(call => call.method)), ['GET']);
});

test('archives, enrolls and activates a distinct replacement, then reads old history', async t => {
  const page = await fixture(t, true);
  page.once('dialog', dialog => dialog.dismiss());
  await page.getByRole('button', {name: 'Arquivar', exact: true}).click();
  assert.deepEqual(await page.evaluate(() => calls.map(c => c.route)), [
    '/open-finance/connections', '/open-finance/registry/archive/inspect',
  ]);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Arquivar', exact: true}).click();
  await page.getByRole('button', {name: 'Cadastrar substituta'}).click();
  await page.getByLabel('Client ID', {exact: true}).fill('synthetic-client');
  await page.getByLabel('Client Secret', {exact: true}).fill('synthetic-secret');
  await page.getByLabel('Item ID').fill('synthetic-item');
  await page.getByRole('button', {name: 'Salvar rascunho'}).click();
  assert.equal(await page.getByLabel('Client Secret', {exact: true}).inputValue(), '');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Validar e ativar'}).click();
  await page.getByRole('status').filter({hasText: 'Conexão ativada'}).waitFor();
  const archived = page.getByRole('listitem').filter({hasText: 'Arquivada'});
  await archived.getByRole('button', {name: 'Ver histórico'}).click();
  await page.getByRole('button', {name: 'Próxima página'}).click();
  assert.deepEqual(await page.evaluate(() => calls.filter(c => c.method === 'POST').map(c => c.route)), [
    '/open-finance/registry/archive/inspect', '/open-finance/registry/archive/inspect',
    '/open-finance/registry/archive', '/open-finance/registry/drafts', '/open-finance/registry/activate',
  ]);
  assert((await page.evaluate(() => calls.at(-1).route)).includes('connection_id=santander&page=2'));
});

test('navigation clears credential fields and blocks stale submissions', async t => {
  const page = await fixture(t, true);
  await page.getByRole('button', {name: 'Adicionar instituição'}).click();
  await page.getByLabel('Client Secret', {exact: true}).fill('synthetic-secret');
  await page.evaluate(() => window.leave());
  assert.equal(await page.getByLabel('Client Secret', {exact: true}).inputValue(), '');
  await page.locator('form').filter({has: page.getByRole('button', {name: 'Salvar rascunho'})})
    .evaluate(form => form.dispatchEvent(new Event('submit', {cancelable: true})));
  assert.equal(await page.evaluate(() => calls.length), 1);
});

test('edits the label and suspends and resumes only after confirmation', async t => {
  const page = await fixture(t, true);
  await page.getByRole('button', {name: 'Editar nome'}).click();
  await page.getByLabel('Novo nome').fill('Santander pessoal');
  await page.getByRole('button', {name: 'Salvar nome'}).click();
  await page.getByText('Santander pessoal', {exact: true}).waitFor();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Desativar', exact: true}).click();
  await page.getByRole('button', {name: 'Validar e reativar'}).waitFor();
  assert.equal(await page.getByRole('button', {name: 'Consultar cache Pluggy'}).count(), 0);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Validar e reativar'}).click();
  await page.getByRole('button', {name: 'Consultar cache Pluggy'}).waitFor();
  assert.deepEqual(await page.evaluate(() => calls.filter(c => c.method === 'POST').map(c => c.route)), [
    '/open-finance/registry/rename', '/open-finance/registry/disable', '/open-finance/registry/activate',
  ]);
});

test('shows verified capabilities from a bounded preview without activating or collecting', async t => {
  const page = await fixture(t, true);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Verificar Item e recursos'}).click();
  const status = page.getByRole('status').filter({hasText: 'Item verificado'});
  await status.waitFor();
  assert.match(await status.innerText(), /Conta disponível.*primeira página/);
  assert(!((await status.innerText()).includes('PRIVATE_VALUE')));
  assert.deepEqual(await page.evaluate(() => calls.filter(c => c.method === 'POST').map(c => c.route)), [
    '/open-finance/registry/validate',
  ]);
});

test('rotates managed credentials without requesting the Item ID or retaining the secret', async t => {
  const page = await fixture(t, true);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Arquivar', exact: true}).click();
  await page.getByRole('button', {name: 'Cadastrar substituta'}).click();
  await page.getByLabel('Client ID', {exact: true}).fill('synthetic-client');
  await page.getByLabel('Client Secret', {exact: true}).fill('synthetic-secret');
  await page.getByLabel('Item ID').fill('synthetic-item');
  await page.getByRole('button', {name: 'Salvar rascunho'}).click();
  await page.getByRole('button', {name: 'Trocar credenciais'}).click();
  assert(await page.getByLabel('Item ID').isHidden());
  await page.getByLabel('Client ID da conexão').fill('synthetic-client');
  await page.getByLabel('Novo Client Secret').fill('rotated-secret');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Validar e salvar credenciais'}).click();
  await page.getByRole('status').filter({hasText: 'Credenciais validadas e atualizadas'}).waitFor();
  assert.equal(await page.getByLabel('Novo Client Secret').inputValue(), '');
  assert.equal(await page.evaluate(() => calls.filter(c => c.route.endsWith('/rotate-credentials')).length), 1);
});

test('deletes an eligible archived draft after inspection and reinforced confirmation', async t => {
  const page = await fixture(t, true);
  await page.getByRole('button', {name: 'Adicionar instituição'}).click();
  await page.getByLabel('Nome da instituição').fill('Instituição sintética');
  await page.getByLabel('Client ID', {exact: true}).fill('synthetic-client');
  await page.getByLabel('Client Secret', {exact: true}).fill('synthetic-secret');
  await page.getByLabel('Item ID').fill('synthetic-item');
  await page.getByRole('button', {name: 'Salvar rascunho'}).click();
  const row = page.getByRole('listitem').filter({hasText: 'Instituição sintética'});
  page.once('dialog', dialog => dialog.accept());
  await row.getByRole('button', {name: 'Arquivar', exact: true}).click();
  await row.getByRole('button', {name: 'Verificar exclusão'}).click();
  await page.getByText('Nenhuma dependência impeditiva foi encontrada.').waitFor();
  assert.equal(await page.evaluate(() => calls.some(c => c.route.endsWith('/registry/delete'))), false);
  await page.getByLabel('Verifiquei que existe um backup atual e recuperável.').check();
  await page.getByLabel('Digite EXCLUIR DEFINITIVAMENTE').fill('EXCLUIR DEFINITIVAMENTE');
  await page.getByRole('button', {name: 'Excluir definitivamente'}).click();
  await page.getByRole('status').filter({hasText: 'Conexão excluída'}).waitFor();
  assert.equal(await row.count(), 0);
  assert.equal(await page.getByText('Santander', {exact: true}).count(), 1);
});

test('operational filters refresh by stable ID and keep archived history', async t => {
  const context = await browser.newContext();
  t.after(() => context.close());
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const page = await context.newPage();
  await page.goto(origin);
  await page.evaluate(async () => {
    const {createOpenFinance} = await import('/open-finance.js');
    const view = document.querySelector('main');
    const row = (id, institution, enabled, historical, state) => ({id, institution, enabled, historical, state});
    window.connections = [
      row('itau', 'Itaú', true, false),
      row('santander', 'Santander', false, true, 'FAILED'),
      row('santander-new', 'Santander', true, false, 'FAILED'),
      row('partial', 'Parcial', true, false, 'PARTIAL'),
      row('disabled', 'Desativada', false, false),
      row('unknown', 'Desconhecida', undefined, false),
    ];
    window.requests = [];
    const state = {};
    const api = async path => {
      requests.push(path);
      if (path === '/open-finance/catalogs') return {connections, accounts: [], categories: [], runs: [
        {connection_id:'santander', id:'old-run', state:'FAILED', started_at:'2026-11-01', inserted_count:0, updated_count:0, page_count:0},
      ]};
      if (path.startsWith('/open-finance/transactions?')) return {items:[], query_meta:{
        query_completeness:'COMPLETE', coverage:{direction:{state:'COMPLETE'}}, warnings:[],
        counts:{after_f04:{state:'EXACT',value:0}},
      }};
      if (path.startsWith('/open-finance/analytics?')) return {positions:{accounts:{value:null,coverage_state:'PARTIAL',items:[]},investments:{value:null,coverage_state:'PARTIAL',items:[],by_class:[]}},flow:{BANK:{incoming:'0',outgoing:'0'},CREDIT:{incoming:'0',outgoing:'0'}},category_ranking:{BANK:[]},series:[],coverage:[],items:[],total:0,page:1,has_more:false};
      if (path.startsWith('/open-finance/domain?')) return {items:[],total:0};
      throw new Error('Unexpected route');
    };
    await createOpenFinance({api, view, state, heading(){}, esc:String})();
  });
  const values = selector => page.locator(selector).evaluateAll(nodes => nodes.map(node => [node.value,node.textContent]));
  const flow = '#of-panel-flow select[name="connection_id"]';
  const domain = '#of-panel-assets select[name="connection_id"]';
  const expected = [['','Todas as ativas'],['itau','Itaú'],['santander-new','Santander'],['partial','Parcial']];
  assert.deepEqual(await values(flow+' option'),expected);
  assert.deepEqual((await values(domain+' option')).slice(1),expected.slice(1));
  await page.locator('[data-of-tab="connections"]').click();
  assert.match(await page.locator('[data-history]').textContent(),/Santander.*Falhou/);
  await page.locator('[data-of-tab="flow"]').click();
  await page.locator(flow).selectOption('santander-new');
  await page.getByRole('button',{name:'Aplicar filtros'}).click();
  await page.getByRole('button',{name:'Atualizar consulta'}).waitFor();
  const requests = () => page.evaluate(() => requests.filter(path => path.includes('/analytics?')));
  assert.match((await requests()).at(-1),/connection_id=santander-new(?:&|$)/);
  await page.getByRole('button',{name:'Atualizar consulta'}).click();
  await page.getByRole('button',{name:'Atualizar consulta'}).waitFor();
  assert.equal(await page.locator(flow).inputValue(),'santander-new');
  await page.evaluate(() => {connections.find(c=>c.id==='santander-new').enabled=false});
  await page.getByRole('button',{name:'Atualizar consulta'}).click();
  await page.getByRole('button',{name:'Atualizar consulta'}).waitFor();
  assert.equal(await page.locator(flow).inputValue(),'');
  assert.doesNotMatch((await requests()).at(-1),/connection_id=/);
  await page.evaluate(() => {connections.forEach(c=>c.enabled=false)});
  await page.getByRole('button',{name:'Atualizar consulta'}).click();
  await page.getByRole('button',{name:'Atualizar consulta'}).waitFor();
  assert.deepEqual(await values(flow+' option'),[['','Todas as ativas']]);
  await page.evaluate(() => {connections.find(c=>c.id==='santander-new').enabled=true});
  await page.getByRole('button',{name:'Atualizar consulta'}).click();
  await page.getByRole('button',{name:'Atualizar consulta'}).waitFor();
  assert.deepEqual(await values(flow+' option'),[['','Todas as ativas'],['santander-new','Santander']]);
});
