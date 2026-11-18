// Imported bank staging only. No provider calls or official financial writes.
import {createQueryGeneration} from './query-generation.js';
import {dateBR} from './privacy.js';
import {mountAnalyticsOverview} from './open-finance-overview.js';
import {coverageLabel,runStateLabel} from './open-finance-labels.js';
import {openFinanceError} from './open-finance-errors.js';
import {mountCoverage} from './open-finance-coverage.js';
import {mountAnalyticsFlow} from './open-finance-flow.js';
import {connectionLabel,runSummary} from './open-finance-status.js';
export {mountAnalyticsOverview};

export function createOpenFinance({api,view,heading,esc,navigation=null,state={},today=null}) {
  let selectedTab=state.selectedTab||'overview';
  return async function openFinance() {
    heading('Open Finance','Dados bancários importados — não são despesas ou receitas oficiais.');
    const host=document.createElement('section');host.className='of-screen';view.append(host);
    host.innerHTML='<p role="status">Carregando conexões bancárias…</p>';
    let catalog;
    try {catalog=await api('/open-finance/catalogs')} catch (_) {
      if(navigation&&!navigation.current())return;
      if(view.contains(host))host.innerHTML='<p role="alert" class="attention">Não foi possível carregar o Open Finance. Verifique o armazenamento e tente novamente.</p><button type="button" data-retry>Recarregar</button>';
      host.querySelector('[data-retry]')?.addEventListener('click',()=>{host.remove();openFinance()});return;
    }
    if((navigation&&!navigation.current())||!view.contains(host))return;
    let tabInitialized=false;
    host.innerHTML=
      `<div class="of-tabs" role="tablist" aria-label="Áreas do Open Finance">${[['overview','Visão geral'],['flow','Movimentações'],['cards','Cartões'],['assets','Investimentos'],['credit','Crédito'],['connections','Conexões']].map(([id,text])=>`<button type="button" role="tab" id="of-tab-${id}" aria-controls="of-panel-${id}" data-of-tab="${id}">${text}</button>`).join('')}</div>
      ${['overview','flow','cards','assets','credit'].map(id=>`<section hidden role="tabpanel" id="of-panel-${id}" aria-labelledby="of-tab-${id}" class="of-panel"></section>`).join('')}
      <section hidden role="tabpanel" id="of-panel-connections" aria-labelledby="of-tab-connections" class="of-panel"><section class="panel"><h2>Conexões bancárias</h2><p>Informações registradas no catálogo.</p>${connectionCards(catalog,esc)}</section><section class="panel of-history"><h2>Histórico das sincronizações manuais</h2><p></p><div data-history></div></section></section>`;
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
    const analyticsState=state.analytics??={};
    let flow;
    const domains=mountCoverage({host,api,esc,catalog,navigation,analyticsState,domainSelections:state.domainSelections??={},onCardFlow:identity=>{
      const conn=catalog.connections.find(c=>c.id===identity.connection_id);
      flow.update({connection_id:identity.connection_id,account_id:identity.external_id,product:'CREDIT',status:'ALL',direction:'all',category:'',search:'',bill_id:'',history:conn?.enabled&&!conn?.historical?'0':'1'},{load:false});
      selectTab('flow',true);
    },onBillFlow:identity=>{
      const conn=catalog.connections.find(c=>c.id===identity.connection_id);
      flow.update({connection_id:identity.connection_id,account_id:identity.parent_id,bill_id:identity.external_id,product:'CREDIT',status:'ALL',direction:'all',category:'',search:'',history:conn?.enabled&&!conn?.historical?'0':'1'},{load:false});
      selectTab('flow',true);
    }});
    const connectionPanel=host.querySelector('#of-panel-connections');
    organizeConnectionSections(connectionPanel);
    mountConnectionCoverage({host,panel:connectionPanel,api,esc,navigation});
    connectionPanel.querySelectorAll('[data-connection-diagnostic]').forEach(button=>button.onclick=()=>{
      const section=connectionPanel.querySelector('.of-coverage'),form=section?.querySelector('form');
      if(!form)return;section.closest('details')?.setAttribute('open','');
      form.elements.connection_id.value=button.dataset.connectionDiagnostic;
      form.elements.connection_id.dispatchEvent(new Event('change',{bubbles:true}));
      form.requestSubmit();section.scrollIntoView({block:'start',behavior:'smooth'});
    });
    const overview=state.overview??={};
    mountAnalyticsOverview({host,api,esc,catalog,navigation,state:overview,today:today?.(),
      onNavigate:context=>{flow.update(context,{load:selectedTab==='flow'});selectTab('flow',true)},
      onAssets:context=>{domains.updateAssets(context);selectTab('assets',true)},
      onConnections:(id,diagnostic)=>{
        selectTab('connections',true);
        if(diagnostic){
          const button=[...connectionPanel.querySelectorAll('[data-connection-diagnostic]')].find(b=>b.dataset.connectionDiagnostic===id);
          if(button)button.click();
          else{
            const section=connectionPanel.querySelector('.of-coverage');
            section?.closest('details')?.setAttribute('open','');
            section?.querySelector('select')?.focus();
            section?.scrollIntoView({block:'start'});
          }
        }
      },
    });
    for(const key of ['start','end','currency'])analyticsState[key] ||= overview[key];
    flow=mountAnalyticsFlow({host,api,esc,catalog,navigation,state:analyticsState,onRefresh:()=>{if(view.contains(host)){host.remove();openFinance()}}});
    const history=host.querySelector('[data-history]');
    host.querySelector('.of-history > p').textContent='Últimas 25 sincronizações registradas. Nenhuma sincronização é iniciada ao abrir esta tela.';
    history.innerHTML=catalog.runs.length?`<ul class="of-run-list">${catalog.runs.slice(0,25).map(r=>`<li><strong>${esc(catalog.connections.find(c=>c.id===r.connection_id)?.institution||'Instituição indisponível')}</strong> · ${esc(runSummary(r,runStateLabel(r.state)))}<small>${dateBR(r.started_at)} · ${r.inserted_count} inseridas · ${r.updated_count} atualizadas · ${r.page_count} páginas${r.error_code?' · '+esc(openFinanceError(r.error_code)):''}</small></li>`).join('')}</ul>`:'<p class="empty">Nenhuma sincronização manual registrada.</p>';
    selectTab(selectedTab);
    // Each panel manages its own cancellable local read.
  };
}


// Keep the existing operational controls mounted while reducing visual noise.
export function organizeConnectionSections(panel){
  if(!panel)return;
  const sections=[...panel.children].filter(node=>node.tagName==='SECTION');
  for(const section of sections.slice(1)){
    const heading=section.querySelector('h2');
    const wrapper=document.createElement('details');wrapper.className='of-connection-section';
    const summary=document.createElement('summary');summary.textContent=heading?.textContent||'Detalhes da conexão';
    section.before(wrapper);wrapper.append(summary,section);
  }
}


export function connectionCards(catalog,esc){
  if(!catalog.connections.length)return '<p class="empty">Nenhuma conexão registrada.</p>';
  return `<div class="of-connection-grid">${catalog.connections.map(c=>{
    const accounts=catalog.accounts.filter(a=>a.connection_id===c.id),banks=accounts.filter(a=>a.type==='BANK').length,cards=accounts.filter(a=>a.type==='CREDIT').length;
    const run=catalog.runs.find(r=>r.connection_id===c.id),state=c.historical?'Histórica':c.enabled?'Habilitada':'Desabilitada';
    return `<article class="of-connection-card" data-connection-id="${esc(c.id)}"><h3>${esc(connectionLabel(c,catalog.connections))}</h3><span class="status">${esc(state)}</span><details><summary>Identificação original</summary><p>${esc(c.institution)} · ${esc(c.id)}</p></details><p>${banks} ${banks===1?'conta':'contas'} · ${cards} ${cards===1?'cartão':'cartões'} no catálogo</p><p>${run?`Última sincronização registrada: ${esc(dateBR(run.started_at))} · ${esc(runStateLabel(run.state))}`:'Nenhuma sincronização registrada.'}</p><div data-connection-coverage><small>Cobertura ainda não consultada.</small></div>${c.enabled&&!c.historical?`<button type="button" class="quiet" data-connection-diagnostic="${esc(c.id)}">Consultar diagnóstico</button>`:'<small>Histórico preservado; seleção operacional indisponível.</small>'}</article>`;
  }).join('')}</div>`;
}


// Coverage reflects recorded collection states, not account balances or consent validity.
export function mountConnectionCoverage({host,panel,api,esc,navigation}){
  const queries=createQueryGeneration(navigation);
  const resources={accounts:'Contas e cartões',transactions:'Movimentações',investments:'Investimentos',investment_transactions:'Movimentos de investimento',bills:'Faturas',loans:'Crédito',statements:'Extratos',consents:'Consentimentos',resources:'Recursos',item:'Conexão'};
  const cards=[...panel.querySelectorAll('[data-connection-id]')];
  async function load(){
    const query=queries.begin();for(const card of cards)card.querySelector('[data-connection-coverage]').innerHTML='<small role="status">Consultando cobertura…</small>';
    try{
      const result=await api('/open-finance/coverage',{queryScope:query});if(!query.current()||!host.isConnected)return;
      for(const card of cards){const rows=(result.coverage||[]).filter(row=>row.connection_id===card.dataset.connectionId),target=card.querySelector('[data-connection-coverage]');
        target.innerHTML=rows.length?`<details><summary>Cobertura registrada (${rows.length})</summary><ul class="of-coverage-list">${rows.map(row=>`<li>${esc(resources[row.resource]||row.resource)} · ${esc(coverageLabel(row.state))} · Coleta: ${esc(dateBR(row.observed_at))}</li>`).join('')}</ul><small>Coleta recente não comprova frescor financeiro nem consentimento atual.</small></details>`:'<small>Cobertura não registrada.</small>';
      }
    }catch(_){if(query.current()&&host.isConnected)for(const card of cards){const target=card.querySelector('[data-connection-coverage]');target.innerHTML='<small role="alert">Cobertura indisponível.</small><button type="button" class="quiet" data-coverage-retry>Tentar novamente</button>';target.querySelector('[data-coverage-retry]').onclick=load}}
  }
  host.addEventListener('of-tab-selected',event=>{if(event.detail==='connections')load();else queries.cancel()});
}
