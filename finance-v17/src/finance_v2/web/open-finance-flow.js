import {createQueryGeneration} from './query-generation.js';
import {bankMoney,dateBR} from './privacy.js';
import {activeConnections,connectionLabel} from './open-finance-status.js';

// All totals are computed by analytics, never by the browser.
export function mountAnalyticsFlow({host,api,esc,catalog,navigation,state}) {
  const panel=host.querySelector('#of-panel-flow'),active=activeConnections(catalog),queries=createQueryGeneration(navigation);
  state.product ||= 'BANK'; state.status ||= 'POSTED'; state.direction ||= 'all'; state.page ||= 1;
  const opt=(v,t)=>`<option value="${esc(v)}">${esc(t)}</option>`;
  const cats=catalog.categories.map(c=>({key:c.external_id?'pluggy:'+c.external_id:'local:'+c.connection_id+':'+c.category_key,name:c.translation_status!=='UNVERIFIED'&&c.display_name_pt?c.display_name_pt:c.original_name||c.external_id||'Categoria sem nome'}));
  const unique=[...new Map(cats.map(c=>[c.key,c])).values()];
  panel.innerHTML=`<h2>Movimentações</h2><p>Movimentos brutos informados pelo banco; classificação econômica não estabelecida.</p><form class="of-overview-filters" aria-label="Filtros de movimentações">
    <label>De<input type="date" name="start" required></label><label>Até<input type="date" name="end" required></label>
    <label>Instituição<select name="connection_id">${opt('','Todas as ativas')}${active.map(c=>opt(c.id,connectionLabel(c,active))).join('')}</select></label>
    <label>Moeda<input name="currency" pattern="[A-Z]{3}" maxlength="3" required></label>
    <label>Origem<select name="product">${opt('BANK','Contas')}${opt('CREDIT','Cartões')}</select></label>
    <label>Categoria<select name="category">${opt('','Todas')}${opt('missing','Sem categoria')}${unique.map(c=>opt(c.key,c.name)).join('')}</select></label>
    <label>Busca<input type="search" name="search" maxlength="256"></label><div data-bill-filter hidden>Fatura selecionada <button type="button" class="quiet" data-clear-bill>Remover filtro de fatura</button></div><details class="of-advanced"><summary>Mais filtros</summary><div class="of-overview-filters"><label><input type="checkbox" name="history"> Incluir conexões históricas</label><label>Conta<select name="account_id"></select></label><label>Situação<select name="status">${opt('POSTED','Lançadas')}${opt('PENDING','Pendentes')}${opt('ALL','Todas')}</select></label><label>Direção<select name="direction">${opt('all','Todas')}${opt('incoming','Entradas')}${opt('outgoing','Saídas')}${opt('unknown','Não estabelecida')}</select></label></div></details><button type="submit">Aplicar filtros</button></form><div data-flow-result aria-live="polite"></div>`;
  const form=panel.querySelector('form'),result=panel.querySelector('[data-flow-result]');
  const names=['start','end','connection_id','account_id','currency','product','status','direction','category','search'];
  function accounts(){const cid=form.elements.connection_id.value,select=form.elements.account_id;select.innerHTML=opt('','Todas')+catalog.accounts.filter(a=>a.connection_id===cid).map(a=>opt(a.external_id,a.name||'Conta sem nome')).join('');select.disabled=!cid;}
  function connections(){const select=form.elements.connection_id,current=select.value,items=form.elements.history.checked?catalog.connections:active;select.innerHTML=opt('',form.elements.history.checked?'Todas, inclusive históricas':'Todas as ativas')+items.map(c=>opt(c.id,connectionLabel(c,items))).join('');select.value=items.some(c=>c.id===current)?current:'';}
  function syncForm(){form.querySelector('[data-bill-filter]').hidden=!state.bill_id;form.querySelector('.of-advanced').open=!!(state.account_id||state.history==='1'||state.status!=='POSTED'||state.direction!=='all');form.elements.history.checked=state.history==='1';connections();for(const n of names)if(n!=='account_id')form.elements[n].value=state[n]||'';accounts();form.elements.account_id.value=state.account_id||'';}
  form.elements.history.onchange=()=>{connections();state.account_id='';accounts()};
  form.elements.connection_id.onchange=()=>{state.account_id='';accounts()};
  function monetary(value){return value==null?'Indisponível':bankMoney(value,state.currency)}
  function privateValue(value){return `<strong ${value==null?'':'data-private-financial'}>${esc(monetary(value))}</strong>`}
  async function load(){
    const query=queries.begin();result.setAttribute('aria-busy','true');result.innerHTML='<p role="status">Carregando movimentações…</p>';
    const params=new URLSearchParams({page:String(state.page),page_size:'25'});if(state.bill_id)params.set('bill_id',state.bill_id);if(state.history==='1')params.set('history','1');for(const n of names)if(state[n])params.set(n,state[n]);
    try {const data=await api('/open-finance/analytics?'+params,{queryScope:query});if(!query.current()||!host.isConnected)return;
      const totals=data.flow[state.product],coverage=(data.coverage||[]).filter(c=>c.resource==='transactions'),known=coverage.some(c=>c.state==='AVAILABLE'||c.state==='EMPTY');
      let prior='';const rows=data.items.map(tx=>{const date=tx.date!==prior?`<h3 class="of-flow-date">${esc(dateBR(tx.date))}</h3>`:'';prior=tx.date;return `${date}<article class="of-flow-item"><div><strong>${esc(tx.description||'Descrição indisponível')}</strong><p>${esc(tx.institution)} · ${esc(tx.account_name||'Conta')} · ${esc(tx.category?.name||'Sem categoria')}</p><small>${esc(tx.direction==='incoming'?'Entrada':tx.direction==='outgoing'?'Saída':'Direção não estabelecida')} · ${esc(tx.status||'Situação desconhecida')}</small></div><div>${privateValue(tx.amount)}<details><summary>Detalhes</summary><p>${esc(tx.product==='CREDIT'?'Cartão':'Conta bancária')} · ${esc(tx.reconciliation||'Não reconciliada')}</p><p>Classificação econômica não estabelecida.</p></details></div></article>`}).join('');
      result.innerHTML=`<div class="of-flow-metrics"><article class="of-metric"><span>Entradas brutas</span>${privateValue(known?totals.incoming:null)}</article><article class="of-metric"><span>Saídas brutas</span>${privateValue(known?totals.outgoing:null)}</article><article class="of-metric"><span>Movimentações encontradas</span><strong>${esc(data.total)}</strong></article></div><p class="of-overview-note">Cobertura pode ser parcial; valores brutos não representam receita ou despesa econômica.</p>${rows||'<p class="empty">Nenhuma movimentação encontrada para os filtros.</p>'}<div class="actions of-pagination"><button type="button" data-flow-prev ${state.page===1?'disabled':''}>Anterior</button><span>Página ${state.page}</span><button type="button" data-flow-next ${!data.has_more?'disabled':''}>Próxima</button></div>`;
      result.querySelector('[data-flow-prev]').onclick=()=>{state.page--;load()};result.querySelector('[data-flow-next]').onclick=()=>{state.page++;load()};
    }catch(_){if(query.current()&&host.isConnected){result.innerHTML='<p role="alert" class="attention">Não foi possível consultar as movimentações.</p><button type="button" data-flow-retry>Tentar novamente</button>';result.querySelector('[data-flow-retry]').onclick=load}}
    finally{if(query.current())result.removeAttribute('aria-busy')}
  }
  form.onsubmit=e=>{e.preventDefault();if(state.bill_id&&(form.elements.connection_id.value!==state.connection_id||form.elements.account_id.value!==state.account_id||form.elements.product.value!=='CREDIT'))state.bill_id='';form.querySelector('[data-bill-filter]').hidden=!state.bill_id;if(form.elements.start.value>form.elements.end.value){form.elements.end.setCustomValidity('Data final anterior à inicial.');form.elements.end.reportValidity();return}for(const n of names)state[n]=form.elements[n].value;state.history=form.elements.history.checked?'1':'0';state.page=1;load()};
  for(const n of ['start','end'])form.elements[n].oninput=()=>form.elements.end.setCustomValidity('');
  form.querySelector('[data-clear-bill]').onclick=()=>{state.bill_id='';state.page=1;syncForm();load()};
  function update(context){Object.assign(state,context,{page:1});syncForm();load()}
  host.addEventListener('of-tab-selected',event=>{if(event.detail==='flow'){syncForm();load()}});
  syncForm();load();return {update};
}
