// Imported bank staging only. No provider calls or official financial writes.
import {createQueryGeneration} from './query-generation.js';
import {bankMoney,dateBR} from './privacy.js';
import {openFinanceError} from './open-finance-errors.js';
import {mountCoverage} from './open-finance-coverage.js';
import {activeConnections,connectionLabel,runSummary} from './open-finance-status.js';
export function createOpenFinance({api,view,heading,esc,navigation=null,state={}}) {
  const directionLabels={CREDIT:'Entrada',DEBIT:'Saída',UNKNOWN:'Desconhecida',CONFLICT:'Conflito'};
  const runLabels={SUCCEEDED:'Concluída',FAILED:'Falhou',INTERRUPTED:'Interrompida',RUNNING:'Em andamento'};
  const reasonLabels={DECLARED_PROVIDER_TYPE:'Tipo declarado pelo provedor',ZERO_UNCLASSIFIED:'Valor zero: direção não atribuída',TYPE_PRESENCE_UNRECOVERABLE:'Tipo ausente/nulo não distinguível',TYPE_UNKNOWN_VALUE:'Tipo não reconhecido',ACCOUNT_PRODUCT_CONFLICT:'Produto da conta incompatível',PRODUCT_NOT_COVERED:'Produto não abrangido',PRODUCT_CONTEXT_MISSING:'Produto da conta indisponível',ACCOUNT_IDENTITY_UNESTABLISHED:'Identidade da conta não comprovada',VALUE_UNSUPPORTED:'Representação de valor não abrangida',MONETARY_CONTEXT_MISSING:'Contexto monetário indisponível'};
  const option=(value,label)=>`<option value="${esc(value)}">${esc(label)}</option>`;
  let saved=state.saved||{},page=state.page||1,selectedTab=state.selectedTab||'overview',tabInitialized=false;
  return async function openFinance() {
    heading('Open Finance','Dados bancários importados — não são despesas ou receitas oficiais.');
    const host=document.createElement('section');host.className='of-screen';view.append(host);
    host.innerHTML='<p role="status">Carregando conexões bancárias…</p>';
    let catalog;
    try {catalog=await api('/open-finance/catalogs')} catch (_) {
      if(navigation&&!navigation.current())return;
      if(view.contains(host))host.innerHTML='<p role="alert" class="attention">Não foi possível carregar o Open Finance. Verifique o armazenamento e tente novamente.</p><button type="button" data-retry>Recarregar</button>';
      host.querySelector('[data-retry]')?.addEventListener('click',openFinance);return;
    }
    if((navigation&&!navigation.current())||!view.contains(host))return;
    const active=activeConnections(catalog);
    if(saved.connection_id && !active.some(c=>c.id===saved.connection_id)){
      const {connection_id,external_account_id,category_key,origin_run_id,...unscoped}=saved;
      saved=unscoped;page=1;state.saved=saved;state.page=page;
    }
    const accountLabel=a=>{
      const institution=catalog.connections.find(c=>c.id===a.connection_id)?.institution||'Instituição indisponível';
      const peers=catalog.accounts.filter(x=>x.connection_id===a.connection_id&&(x.name||'Conta sem nome')===(a.name||'Conta sem nome'));
      return `${a.name||'Conta sem nome'} · ${institution}${peers.length>1?' · Conta '+(peers.indexOf(a)+1):''}`;
    };
    host.innerHTML=`<p class="of-notice">Consulta de staging bancário. Os filtros usam a data informada pelo provedor, não a competência das despesas. A direção bancária não comprova liquidação nem representa receita/despesa oficial. Não há conciliação ou promoção automática para lançamentos oficiais.</p>
      <div class="of-tabs" role="tablist" aria-label="Áreas do Open Finance">${[['overview','Visão geral'],['flow','Movimentações'],['cards','Cartões'],['assets','Investimentos'],['credit','Crédito'],['connections','Conexões']].map(([id,text])=>`<button type="button" role="tab" id="of-tab-${id}" aria-controls="of-panel-${id}" data-of-tab="${id}">${text}</button>`).join('')}</div>
      <section role="tabpanel" id="of-panel-cards" aria-labelledby="of-tab-cards" class="of-panel"></section>
      <section role="tabpanel" id="of-panel-credit" aria-labelledby="of-tab-credit" class="of-panel"></section>
      <section role="tabpanel" id="of-panel-overview" aria-labelledby="of-tab-overview" class="panel of-panel"><h2>Visão geral</h2><p>Conexões e contas de staging disponíveis para consulta. Não representam o patrimônio nem o saldo consolidado.</p><p>${catalog.connections.length} conexões · ${catalog.accounts.length} contas cadastradas no catálogo.</p><p class="of-notice">Resumo de saldos indisponível: não há contrato implementado para saldos consolidados. Consulte as movimentações na aba Fluxo.</p></section>
      <section role="tabpanel" id="of-panel-assets" aria-labelledby="of-tab-assets" class="panel of-panel"><h2>Ativos</h2><p class="empty">Consulta de ativos indisponível. O contrato de posições, investimentos e avaliação patrimonial ainda não está implementado.</p><p>Nenhum saldo ou valor estimado é apresentado.</p></section>
      <section role="tabpanel" id="of-panel-connections" aria-labelledby="of-tab-connections" class="of-panel"><section class="panel"><h2>Conexões bancárias</h2><p>Informações já registradas no catálogo. Esta tela não consulta a Pluggy nem inicia sincronizações.</p>${catalog.connections.length?`<ul class="of-run-list">${catalog.connections.map(c=>`<li><strong>${esc(connectionLabel(c,catalog.connections))}</strong><small>${c.enabled?'Habilitada na configuração':'Desabilitada na configuração'} · ${catalog.accounts.filter(a=>a.connection_id===c.id).length} contas registradas</small></li>`).join('')}</ul>`:'<p class="empty">Nenhuma conexão registrada.</p>'}</section><section class="panel of-history"><h2>Histórico das sincronizações manuais</h2><p>Nenhuma sincronização é iniciada ao abrir esta tela.</p><div data-history></div></section></section>
      <section role="tabpanel" id="of-panel-flow" aria-labelledby="of-tab-flow" class="of-panel">
      <form class="form-card of-filters" aria-label="Filtros bancários"><div class="form-grid">
      <label>Data inicial<input type="date" name="start"></label><label>Data final<input type="date" name="end"></label>
      <label>Instituição / conexão<select name="connection_id">${option('','Todas as instituições')}${active.map(c=>option(c.id,connectionLabel(c,active))).join('')}</select></label>
      <label>Conta bancária<select name="external_account_id"></select></label>
      <label>Movimentação<select name="direction">${option('all','Todas, incluindo desconhecidas/conflitos')}${option('incoming','Entradas (CREDIT)')}${option('outgoing','Saídas (DEBIT)')}</select></label>
      <label>Categoria bancária<select name="category_key"></select></label>
      <label>Descrição ou estabelecimento<input name="search" type="search" maxlength="256" placeholder="Ex.: café"></label>
      <label>Sincronização de origem<select name="origin_run_id"></select></label>
      </div><div class="actions"><button type="submit">Aplicar filtros</button><button type="button" class="secondary" data-clear>Limpar filtros</button></div></form>
      <div class="of-results" aria-live="polite"></div></section>`;
    const tabs=[...host.querySelectorAll('[data-of-tab]')];
    function selectTab(id,focus=false){
      const changed=!tabInitialized||selectedTab!==id;selectedTab=id;state.selectedTab=id;
      for(const tab of tabs){const active=tab.dataset.ofTab===id;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;host.querySelector('#'+tab.getAttribute('aria-controls')).hidden=!active;if(active&&focus)tab.focus()}
      if(changed)host.dispatchEvent(new CustomEvent('of-tab-selected',{detail:id}));tabInitialized=true;
    }
    tabs.forEach((tab,index)=>{
      tab.onclick=()=>selectTab(tab.dataset.ofTab);
      tab.onkeydown=event=>{const next=event.key==='ArrowRight'?(index+1)%tabs.length:event.key==='ArrowLeft'?(index+tabs.length-1)%tabs.length:event.key==='Home'?0:event.key==='End'?tabs.length-1:null;if(next!==null){event.preventDefault();selectTab(tabs[next].dataset.ofTab,true)}};
    });
    mountCoverage({host,api,esc,catalog,navigation,domainSelections:state.domainSelections??={}});
    mountAnalyticsOverview({host,api,esc,catalog,navigation,state:state.analytics??={}});
    const form=host.querySelector('#of-panel-flow form'),results=host.querySelector('.of-results');
    const names=['start','end','connection_id','external_account_id','direction','category_key','search','origin_run_id'];
    const choice=(name)=>form.elements.namedItem(name);
    function scopedOptions() {
      const cid=choice('connection_id').value;
      for(const [name,items,key,label] of [
        ['external_account_id',catalog.accounts,'external_id',accountLabel],
        ['category_key',catalog.categories,'category_key',c=>c.original_name||c.external_id||'Categoria sem nome'],
        ['origin_run_id',catalog.runs,'id',r=>`${dateBR(r.started_at)} · ${runLabels[r.state]||r.state} · Sincronização ${catalog.runs.indexOf(r)+1}`]]) {
        const select=choice(name);select.innerHTML=option('',cid?'Todas':'Selecione uma conexão')+items.filter(r=>r.connection_id===cid).map(r=>option(r[key],label(r))).join('');select.disabled=!cid;
      }
    }
    for(const name of ['start','end','connection_id','direction','search'])choice(name).value=saved[name]|| (name==='direction'?'all':'');
    scopedOptions();for(const name of ['external_account_id','category_key','origin_run_id'])choice(name).value=saved[name]||'';
    choice('connection_id').onchange=scopedOptions;
    let generation=0;const queries=createQueryGeneration(navigation);
    async function load() {
      const query=queries.begin();state.saved=saved;state.page=page;const current=++generation;
      results.setAttribute('aria-busy','true');results.innerHTML='<p role="status" data-query-loading>Carregando transações bancárias…</p>';
      const q=new URLSearchParams({contract:'of-l2-v2',metrics:'exact',page:String(page),page_size:'25',...saved});
      try {
        const response=await api('/open-finance/transactions?'+q,{queryScope:query});
        if(!query.current()||current!==generation||!view.contains(host))return;
        const meta=response.query_meta,counts=meta.counts;
        const qualifiers=[];
        if(meta.query_completeness!=='COMPLETE')qualifiers.push('Há registros cujo enquadramento nos filtros não pôde ser determinado. A lista não representa todas as possíveis correspondências.');
        if(meta.coverage.direction.state==='PARTIAL')qualifiers.push('Existem movimentos sem direção comprovada ou com conflito. “Todas” mantém esses registros visíveis.');
        if(meta.warnings.includes('PROVENANCE_UNKNOWN_PRESENT'))qualifiers.push('Há origens não comprovadas; não são inferidas pelas datas.');
        const count=counts.after_f04.state==='EXACT'?`${counts.after_f04.value} ${counts.after_f04.value===1?'transação encontrada':'transações encontradas'}`:'Contagem não disponível';
        results.innerHTML=`<p class="of-count">${esc(count)} · Página ${page}</p>${qualifiers.map(t=>`<p class="of-notice">${esc(t)}</p>`).join('')}${response.items.length?`<table class="of-table"><caption>Transações bancárias importadas</caption><thead><tr>${['Data','Instituição','Conta','Descrição / estabelecimento','Categoria bancária','Valor original','Direção'].map(t=>`<th scope="col">${t}</th>`).join('')}</tr></thead><tbody>${response.items.map(tx=>{
          const date=dateBR(tx.transaction_date),category=tx.category;
          const account=catalog.accounts.find(a=>a.connection_id===tx.connection_id&&a.external_id===tx.external_account_id);
          const values=[date,tx.institution,account?accountLabel(account):tx.account_name||'Conta sem nome',
            `${tx.description_original??'Descrição indisponível'}${tx.merchant_name?' · '+tx.merchant_name:''}`,
            tx.category_key===null?'Sem categoria':category?.original_name||category?.external_id||'Categoria não resolvida',
            bankMoney(tx.amount_decimal,tx.currency),directionLabels[tx.direction.result]||'Desconhecida'];
          return `<tr>${values.map((v,i)=>`<td data-label="${['Data','Instituição','Conta','Descrição','Categoria','Valor','Direção'][i]}"><bdi>${esc(v)}</bdi>${i===6?`<small>${esc(reasonLabels[tx.direction.reason_code]||'Direção não comprovada')}${tx.direction.warnings.includes('CARD_SIGN_DOCUMENTATION_UNRESOLVED')?' · Perspectiva da conta do cartão':''}</small>`:''}</td>`).join('')}</tr>`;
        }).join('')}</tbody></table>`:'<p class="empty">Nenhuma transação encontrada para os filtros selecionados.</p>'}
          <div class="actions of-pagination"><button type="button" data-prev ${page===1?'disabled':''}>Anterior</button><button type="button" data-next ${!response.has_more?'disabled':''}>Próxima</button><button type="button" class="secondary" data-refresh>Atualizar consulta</button></div>`;
        results.querySelector('[data-prev]').onclick=()=>{page--;load()};results.querySelector('[data-next]').onclick=()=>{page++;load()};results.querySelector('[data-refresh]').onclick=()=>{if(view.contains(host)){host.remove();openFinance()}};
      } catch(error) {
        if(!query.current()||current!==generation||!view.contains(host))return;
        const message=error.code==='QUERY_PROFILE_UNAVAILABLE'?'Busca textual indisponível: o runtime não possui o perfil Unicode aprovado. Nenhum filtro foi ignorado.':'Não foi possível consultar as transações bancárias. Nenhum resultado parcial foi publicado.';
        results.innerHTML=`<p role="alert" class="attention">${esc(message)}</p><button type="button" data-retry>Repetir consulta</button>`;results.querySelector('button').onclick=load;
      }finally{if(query.current()&&current===generation){results.removeAttribute('aria-busy');results.querySelector('[data-query-loading]')?.remove()}}
    }
    form.onsubmit=e=>{e.preventDefault();if(choice('start').value&&choice('end').value&&choice('start').value>choice('end').value){choice('end').setCustomValidity('A data final deve ser igual ou posterior à inicial.');choice('end').reportValidity();return}saved=Object.fromEntries(names.map(n=>[n,choice(n).value]).filter(([,v])=>v!==''));page=1;load()};
    choice('end').oninput=()=>choice('end').setCustomValidity('');choice('start').oninput=()=>choice('end').setCustomValidity('');
    host.querySelector('[data-clear]').onclick=()=>{saved={};page=1;for(const n of names)choice(n).value=n==='direction'?'all':'';choice('end').setCustomValidity('');scopedOptions();load()};
    const history=host.querySelector('[data-history]');
    host.querySelector('.of-history > p').textContent='Últimas 25 sincronizações registradas. Nenhuma sincronização é iniciada ao abrir esta tela.';
    history.innerHTML=catalog.runs.length?`<ul class="of-run-list">${catalog.runs.slice(0,25).map(r=>`<li><strong>${esc(catalog.connections.find(c=>c.id===r.connection_id)?.institution||'Instituição indisponível')}</strong> · ${esc(runSummary(r,runLabels[r.state]||r.state))}<small>${dateBR(r.started_at)} · ${r.inserted_count} inseridas · ${r.updated_count} atualizadas · ${r.page_count} páginas${r.error_code?' · '+esc(openFinanceError(r.error_code)):''}</small></li>`).join('')}</ul>`:'<p class="empty">Nenhuma sincronização manual registrada.</p>';
    selectTab(selectedTab);
    await load(); // Preserve the existing local Flow prefetch; one request per mount.
  };
}


// This panel displays only the imported, gross figures returned by analytics.
export function mountAnalyticsOverview({host,api,esc,catalog,navigation,state}) {
  const panel=host.querySelector('#of-panel-overview');
  const month=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit'}).formatToParts(new Date());
  const year=month.find(x=>x.type==='year').value, number=month.find(x=>x.type==='month').value;
  const last=new Date(Date.UTC(Number(year),Number(number),0)).getUTCDate();
  state.start ||= `${year}-${number}-01`;state.end ||= `${year}-${number}-${String(last).padStart(2,'0')}`;
  const active=activeConnections(catalog);if(state.connection_id&&!active.some(c=>c.id===state.connection_id))state.connection_id='';
  state.currency ||= 'BRL';
  panel.innerHTML=`<div class="of-overview"><div class="of-overview-header"><div><h2>Visão geral</h2><p>Dados bancários importados</p></div></div>
  <form class="of-overview-filters" aria-label="Filtros da visão geral"><label>Instituição<select name="connection_id"><option value="">Todas as ativas</option>${active.map(c=>`<option value="${esc(c.id)}">${esc(connectionLabel(c,active))}</option>`).join('')}</select></label><label>Moeda<input name="currency" pattern="[A-Z]{3}" maxlength="3" required></label><label>De<input type="date" name="start" required></label><label>Até<input type="date" name="end" required></label><button type="submit">Aplicar</button></form><div data-overview-result aria-live="polite"></div></div>`;
  const form=panel.querySelector('form'),result=panel.querySelector('[data-overview-result]');
  for(const key of ['start','end','connection_id','currency'])form.elements[key].value=state[key]||'';
  const queries=createQueryGeneration(navigation);
  const money=value=>value===null||value===undefined?'Indisponível':bankMoney(value,state.currency);
  const metric=(title,value,detail)=>`<article class="of-metric"><span>${esc(title)}</span><strong ${value===null||value===undefined?'':'data-private-financial'}>${esc(money(value))}</strong><small>${esc(detail)}</small></article>`;
  async function load(){
    const query=queries.begin();result.innerHTML='<p role="status">Carregando resumo bancário…</p>';result.setAttribute('aria-busy','true');
    const params=new URLSearchParams({start:state.start,end:state.end,currency:state.currency,product:'BANK',status:'POSTED'});if(state.connection_id)params.set('connection_id',state.connection_id);
    try{
      const data=await api('/open-finance/analytics?'+params,{queryScope:query});if(!query.current()||!host.isConnected)return;
      const accounts=data.positions.accounts,investments=data.positions.investments,flow=data.flow.BANK;
      const flowCoverage=(data.coverage||[]).filter(x=>x.resource==='transactions');
      const flowKnown=flowCoverage.some(x=>x.state==='AVAILABLE'||x.state==='EMPTY');
      const coverage=x=>x.coverage_state==='COMPLETE'?'Cobertura informada como completa':'Cobertura parcial ou não estabelecida';
      const categories=data.category_ranking?.BANK||[];
      const series=(data.series||[]).filter(point=>point.product==='BANK');
      const scale=Math.max(0,...series.map(point=>Number(point.value)).filter(Number.isFinite));
      const chart=series.length?`<ul class="of-series">${series.map(point=>{const size=Number(point.value);const width=scale>0&&Number.isFinite(size)?Math.max(0,Math.min(100,size/scale*100)):0;return `<li><span>${esc(dateBR(point.date))} · ${point.direction==='incoming'?'Entrada':'Saída'}</span><span class="of-series-track" aria-hidden="true"><i class="${point.direction==='incoming'?'in':'out'}" style="width:${width}%"></i></span><strong data-private-financial>${esc(money(point.value))}</strong></li>`}).join('')}</ul>`:'<p>Sem movimentações no período.</p>';
      result.innerHTML=`<div class="of-metrics">${metric('Saldo informado das contas',accounts.value,coverage(accounts))}${metric('Investimentos informados',investments.value,coverage(investments))}${metric('Entradas bancárias brutas',flowKnown?flow.incoming:null,'Movimentações POSTED · cobertura pode ser parcial')}${metric('Saídas bancárias brutas',flowKnown?flow.outgoing:null,'Movimentações POSTED · cobertura pode ser parcial')}</div>
      <p class="of-overview-note">Valores conhecidos podem estar incompletos. Entradas e saídas são movimentos brutos, não receitas ou despesas econômicas. O frescor financeiro pode não estar estabelecido.</p>
      <section class="of-summary-card"><h3>Entradas e saídas bancárias brutas</h3><p>Valores informados por dia, para o período selecionado.</p>${chart}</section><div class="of-overview-grid"><section class="of-summary-card"><h3>Saídas por categoria</h3>${categories.length?`<ul class="of-category-list">${categories.map(c=>`<li><span>${esc(c.name)}</span><strong data-private-financial>${esc(money(c.value))}</strong></li>`).join('')}</ul>`:'<p>Sem saídas classificadas no período.</p>'}</section><section class="of-summary-card"><h3>Posições por instituição</h3>${accounts.items.length?`<ul class="of-category-list">${accounts.items.map(a=>`<li><span>${esc(a.institution)} · ${esc(a.name||'Conta')}</span><strong ${a.value===null?'':'data-private-financial'}>${esc(money(a.value))}</strong><small>${a.reference_date?'Data financeira: '+esc(dateBR(a.reference_date)):'Data financeira não informada'} · ${a.provider_updated_at?'Atualização informada: '+esc(dateBR(a.provider_updated_at)):'Atualização não informada'}</small></li>`).join('')}</ul>`:'<p>Nenhuma posição disponível para esta moeda.</p>'}</section></div>`;
    }catch(_){if(query.current()&&host.isConnected)result.innerHTML='<p role="alert" class="attention">Não foi possível carregar o resumo bancário.</p><button type="button" data-retry-summary>Tentar novamente</button>';result.querySelector('[data-retry-summary]')?.addEventListener('click',load)}
    finally{if(query.current())result.removeAttribute('aria-busy')}
  }
  form.onsubmit=e=>{e.preventDefault();if(form.elements.start.value>form.elements.end.value){form.elements.end.setCustomValidity('A data final deve ser igual ou posterior à inicial.');form.elements.end.reportValidity();return}for(const key of ['start','end','connection_id','currency'])state[key]=form.elements[key].value;load()};
  form.elements.end.oninput=()=>form.elements.end.setCustomValidity('');form.elements.start.oninput=()=>form.elements.end.setCustomValidity('');
  load();
}
