import {bankMark} from './open-finance-identity.js';
import {classificationDetail,mountClassification,natureNames,originNames,reviewNames} from './open-finance-classification-ui.js';
import {categoryLabel,institutionName,statusLabel,countBR} from './open-finance-labels.js';
import {createQueryGeneration} from './query-generation.js';
import {bankMoney,dateBR,privacyMode} from './privacy.js';
import {activeConnections,connectionLabel} from './open-finance-status.js';

const pageSizes=[25,50,100,250,500];
const orders={date_desc:'Data · mais recentes primeiro',date_asc:'Data · mais antigas primeiro',
  value_desc:'Valor · maior para menor',value_asc:'Valor · menor para maior',
  description_asc:'Descrição · A a Z',description_desc:'Descrição · Z a A'};
const groups={none:'Sem agrupamento',date:'Por data',institution:'Por instituição',category:'Por categoria efetiva'};
const preferencesKey='finance-of-movements-v1';
function readPreferences(){
  try{return JSON.parse(localStorage.getItem(preferencesKey))||{}}catch{return {}}
}

// All totals are computed by analytics, never by the browser.
export function mountAnalyticsFlow({host,api,esc,catalog,navigation,state,onRefresh=()=>{}}) {
  const panel=host.querySelector('#of-panel-flow'),active=activeConnections(catalog),queries=createQueryGeneration(navigation);
  state.product ||= 'BANK'; state.status ||= 'POSTED'; state.direction ||= 'all'; state.page ||= 1;
  const saved=readPreferences();
  state.pageSize=pageSizes.includes(saved.pageSize)?saved.pageSize:50;
  state.order=Object.hasOwn(orders,saved.order)?saved.order:'date_desc';
  state.group=Object.hasOwn(groups,saved.group)?saved.group:'date';
  const presentation=()=>{
    const order=privacyMode()==='full'&&state.order.startsWith('value_')?'date_desc':state.order;
    return {order,group:state.group==='date'&&!order.startsWith('date_')?'none':state.group};
  };
  const opt=(v,t)=>`<option value="${esc(v)}">${esc(t)}</option>`;
  const cats=catalog.categories.map(c=>{
    const translated=['VERIFIED','OWNER_OVERRIDE'].includes(c.translation_status)&&!!c.display_name_pt;
    const category={key:c.external_id?'pluggy:'+c.external_id:'local:'+c.connection_id+':'+c.category_key,
      name:translated?c.display_name_pt:c.original_name,translated};
    return {...category,name:categoryLabel(category)};
  });
  const unique=[...new Map(cats.map(c=>[c.key,c])).values()];
  const named=(dictionary)=>Object.entries(dictionary).map(([key,label])=>opt(key,label)).join('');
  panel.innerHTML=`<h2>Movimentações</h2><p>Movimentos importados e suas classificações analíticas.</p><button type="button" class="quiet of-center-entry" data-open-classification>Central de classificação</button><div data-effective-selection hidden></div><form class="of-overview-filters" aria-label="Filtros de movimentações">
    <label>De<input type="date" name="start" required></label><label>Até<input type="date" name="end" required></label>
    <label>Instituição<select name="connection_id">${opt('','Todas as ativas')}${active.map(c=>opt(c.id,connectionLabel(c,active))).join('')}</select></label>
    <label>Moeda<input name="currency" pattern="[A-Z]{3}" maxlength="3" required></label>
    <label>Origem<select name="product">${opt('BANK','Contas')}${opt('CREDIT','Cartões')}</select></label>
    <label>Categoria efetiva<input name="effective_category" maxlength="120"></label><label>Direção<select name="direction">${opt('all','Todas')}${opt('incoming','Entradas')}${opt('outgoing','Saídas')}${opt('unknown','Não estabelecida')}</select></label><label>Busca<input type="search" name="search" maxlength="256"></label><div data-bill-filter hidden>Fatura selecionada <button type="button" class="quiet" data-clear-bill>Remover filtro de fatura</button></div><details class="of-advanced"><summary>Mais filtros<span data-advanced-count></span></summary><div class="of-overview-filters"><label>Categoria original<select name="category">${opt('','Todas')}${opt('missing','Sem categoria')}${unique.map(c=>opt(c.key,c.name)).join('')}</select></label>
    <label><input type="checkbox" name="history"> Incluir conexões históricas</label><label>Conta<select name="account_id"></select></label><label>Situação<select name="status">${opt('POSTED','Efetivadas')}${opt('PENDING','Pendentes')}${opt('ALL','Todas')}</select></label><label>Natureza financeira<select name="nature">${opt('','Todas')}${named(natureNames)}</select></label>
      <label>Origem da classificação<select name="origin">${opt('','Todas')}${named(originNames)}</select></label>
      <label>Revisão<select name="review">${opt('','Todas')}${named(reviewNames)}</select></label>
      <label>Regra aplicada<input name="rule" maxlength="80"></label><label>Componente do fluxo<select name="bucket">${opt('','Todos')}${named({operating:'Receitas e despesas identificadas',capital:'Capital',internal:'Movimentações internas',settlement:'Liquidações',pending:'A revisar'})}</select></label>
      <label>Agrupar pendências por<select name="group_by">${named({pattern:'Descrição normalizada',recurring:'Padrão recorrente',institution:'Instituição',account:'Conta',direction:'Direção',category:'Categoria original'})}</select></label>
      <label>Ordenar grupos<select name="group_order">${named({count:'Ocorrências',date:'Data mais recente',magnitude:'Magnitude financeira'})}</select></label>
      </div></details><button type="submit">Aplicar filtros</button><button type="button" class="quiet" data-reset-flow>Limpar filtros</button></form>
    <div class="of-presentation" aria-label="Apresentação das movimentações">
      <label>Ordenação<select data-movement-order>${named(orders)}</select></label>
      <label>Registros por página<select data-movement-size>${pageSizes.map(n=>opt(n,n)).join('')}</select></label>
      <label>Agrupamento<select data-movement-group>${named(groups)}</select></label><small data-group-note></small>
    </div><div data-flow-result aria-live="polite"></div>`;
  const form=panel.querySelector('form'),result=panel.querySelector('[data-flow-result]');
  const classificationKeys=['nature','effective_category','origin','review','rule','bucket'];
  const drilldownKeys=['effective_key','provent','investment','flow_component','card_economic'];
  const names=['start','end','connection_id','account_id','currency','product','status','direction','category','search',...classificationKeys];
  const classification=mountClassification({host,panel,api,esc,catalog,navigation,getScope:()=>state,reload:load});
  panel.querySelector('[data-open-classification]').onclick=()=>classification.toggle();
  function accounts(){const cid=form.elements.connection_id.value,select=form.elements.account_id;select.innerHTML=opt('','Todas')+catalog.accounts.filter(a=>a.connection_id===cid).map(a=>opt(a.external_id,a.name||'Conta sem nome')).join('');select.disabled=!cid;}
  function connections(){const select=form.elements.connection_id,current=select.value,items=form.elements.history.checked?catalog.connections:active;select.innerHTML=opt('',form.elements.history.checked?'Todas, inclusive históricas':'Todas as ativas')+items.map(c=>opt(c.id,connectionLabel(c,items))).join('');select.value=items.some(c=>c.id===current)?current:'';}
  function syncForm(){
    const selection=panel.querySelector('[data-effective-selection]');
    selection.hidden=!drilldownKeys.some(key=>state[key]);
    selection.innerHTML=selection.hidden?'':'<p>Filtro contextual · '+esc(state.effectiveLabel||'Classificação selecionada')+' <button type="button" class="of-link" data-clear-context>Remover filtro contextual</button></p>';
    selection.querySelector('button')?.addEventListener('click',()=>{
      for(const key of drilldownKeys)state[key]='';
      state.page=1;syncForm();load();
    });
    const choices=state.history==='1'?catalog.connections:active;
    if(state.connection_id&&!choices.some(c=>c.id===state.connection_id)){
      Object.assign(state,{connection_id:'',account_id:'',bill_id:'',category:'',page:1});
    }
    form.querySelector('[data-bill-filter]').hidden=!state.bill_id;const advanced=[state.category,state.account_id,state.history==='1',state.status!=='POSTED',
      ...classificationKeys.filter(key=>key!=='effective_category').map(key=>state[key])].filter(Boolean).length;
    form.querySelector('[data-advanced-count]').textContent=advanced?' · '+advanced+' ativos':'';
    form.elements.history.checked=state.history==='1';connections();for(const n of names)if(n!=='account_id'&&n!=='category')form.elements[n].value=state[n]||'';
    const category=form.elements.category;
    category.querySelector('[data-context-option]')?.remove();
    if(state.category&&![...category.options].some(option=>option.value===state.category)){
      const option=new Option(state.categoryLabel||'Categoria selecionada',state.category);
      option.dataset.contextOption='';category.add(option);
    }
    category.value=state.category||'';form.elements.group_by.value=state.group_by||'pattern';form.elements.group_order.value=state.group_order||'count';accounts();form.elements.account_id.value=state.account_id||'';}
  form.elements.history.onchange=()=>{connections();state.account_id='';accounts()};
  form.elements.connection_id.onchange=()=>{state.account_id='';accounts()};
  function monetary(value){return value==null?'Indisponível':bankMoney(value,state.currency)}
  function privateValue(value){return `<strong ${value==null?'':'data-private-financial'+(state.currency==='BRL'?'':' data-private-mask="neutral"')}>${esc(monetary(value))}</strong>`}
  async function load(){
    const query=queries.begin();classification.loading();result.setAttribute('aria-busy','true');result.innerHTML='<p role="status">Carregando movimentações…</p>';
    const {order,group}=presentation();
    const params=new URLSearchParams({page:String(state.page),page_size:String(state.pageSize),sort:order});if(state.bill_id)params.set('bill_id',state.bill_id);if(state.history==='1')params.set('history','1');for(const n of names)if(state[n])params.set(n,state[n]);
    for(const key of drilldownKeys)if(state[key])params.set(key,state[key]);
    if(classification.open()){params.set('center','1');params.set('group_by',state.group_by||'pattern');params.set('group_order',state.group_order||'count');}
    try {const data=await api('/open-finance/analytics?'+params,{queryScope:query});if(!query.current()||!host.isConnected)return;
      const pages=data.total_pages||Math.max(1,Math.ceil(data.total/state.pageSize));
      if(state.page>pages){state.page=pages;load();return;}
      classification.present(data.classification_center);
      const totals=data.flow[state.product],coverage=(data.coverage||[]).filter(c=>c.resource==='transactions'),known=coverage.some(c=>c.state==='AVAILABLE'||c.state==='EMPTY');
      const rowMarkup=(tx,index)=>`<article class="of-flow-item"><div><strong>${esc(tx.description||'Descrição indisponível')}</strong><p>${bankMark(tx.institution,esc)}${esc(institutionName(tx.institution))} · ${esc(tx.account_name||'Conta')} · ${esc(categoryLabel(tx.effective_category||tx.category))}</p><small>${esc(tx.direction==='incoming'?'Entrada':tx.direction==='outgoing'?'Saída':'Direção não estabelecida')} · ${esc(statusLabel(tx.status))}</small></div><div>${privateValue(tx.amount)}<details><summary>Detalhes</summary><p>${esc(tx.product==='CREDIT'?'Cartão':'Conta bancária')} · ${esc(statusLabel(tx.reconciliation))}</p>${classificationDetail(tx,esc)}${recognitionDetail(tx)}</details>${tx.classification?`<button class="of-link of-class-edit" type="button" data-edit-transaction="${index}">Classificar movimentação</button>`:''}</div></article>`;
      const grouped=new Map();
      data.items.forEach((tx,index)=>{
        const label=group==='date'?dateBR(tx.date):group==='institution'?institutionName(tx.institution):
          group==='category'?categoryLabel(tx.effective_category||tx.category):'';
        const key=group==='category'?(tx.effective_category||tx.category)?.key||label:label;
        if(!grouped.has(key))grouped.set(key,{label,entries:[]});
        grouped.get(key).entries.push(rowMarkup(tx,index));
      });
      const rows=[...grouped.values()].map(({label,entries})=>(label?'<h3 class="of-flow-date">'+esc(label)+'</h3>':'')+entries.join('')).join('');
      result.innerHTML=`<div class="of-flow-metrics"><article class="of-metric"><span>Entradas brutas</span>${privateValue(totals.reported?totals.reported.incoming:known?totals.incoming:null)}</article><article class="of-metric"><span>Saídas brutas</span>${privateValue(totals.reported?totals.reported.outgoing:known?totals.outgoing:null)}</article><article class="of-metric"><span>Movimentações encontradas</span><strong>${esc(data.total)}</strong></article></div>${paginationMarkup(data,pages,'superior')}${rows||'<p class="empty">Nenhuma movimentação encontrada para os filtros.</p>'}${paginationMarkup(data,pages,'inferior')}<button type="button" class="quiet" data-flow-refresh>Atualizar consulta</button>`;
      result.querySelectorAll('[data-edit-transaction]').forEach(button=>button.onclick=()=>classification.edit(data.items[Number(button.dataset.editTransaction)]));
      result.querySelectorAll('[data-flow-page]').forEach(button=>button.onclick=()=>go(Number(button.dataset.flowPage),pages));
      result.querySelectorAll('[data-page-form]').forEach(node=>node.onsubmit=event=>{
        event.preventDefault();go(Number(node.elements.page.value),pages);
      });
      result.querySelector('[data-flow-refresh]').onclick=onRefresh;
    }catch(_){if(query.current()&&host.isConnected){result.innerHTML='<p role="alert" class="attention">Não foi possível consultar as movimentações.</p><button type="button" data-flow-retry>Tentar novamente</button>';result.querySelector('[data-flow-retry]').onclick=load}}
    finally{if(query.current())result.removeAttribute('aria-busy')}
  }
  function go(page,pages){
    if(Number.isInteger(page)&&page>=1&&page<=pages&&page!==state.page){state.page=page;load()}
  }
  function paginationMarkup(data,pages,where){
    const first=data.total?(state.page-1)*state.pageSize+1:0,last=first?first+data.items.length-1:0;
    return '<nav class="of-pagination" aria-label="Paginação '+where+'">'+
      '<p>Exibindo '+countBR.format(first)+'–'+countBR.format(last)+' de '+countBR.format(data.total)+' movimentações. Página '+state.page+' de '+pages+'.</p>'+
      '<div class="actions">'+[
        [1,'Primeira','first',state.page===1],[state.page-1,'Anterior','prev',state.page===1],
        [state.page+1,'Próxima','next',state.page===pages],[pages,'Última','last',state.page===pages]
      ].map(([page,label,role,disabled])=>'<button type="button" data-flow-'+role+' data-flow-page="'+page+'" '+(disabled?'disabled':'')+'>'+label+'</button>').join('')+
      '<form data-page-form><label>Ir à página<input name="page" type="number" min="1" max="'+pages+'" value="'+state.page+'" required></label><button type="submit">Ir</button></form></div></nav>';
  }
  function recognitionDetail(row){
    const evidence=row.economic_recognition;
    if(!evidence||evidence.source==='UNESTABLISHED')return '';
    const origin={PROVIDER_CATEGORY:'Categoria do provedor compatível',DETERMINISTIC_PAYROLL:'Rubrica de folha reconhecida',
      MANUAL:'Classificação individual',CUSTOM:'Regra personalizada',NATIVE:'Regra nativa'}[evidence.source];
    return '<p>Reconhecimento financeiro · '+esc(origin||'Evidência indisponível')+' · '+esc(natureNames[evidence.nature]||evidence.nature)+'</p>';
  }
  const orderSelect=panel.querySelector('[data-movement-order]'),sizeSelect=panel.querySelector('[data-movement-size]'),
        groupSelect=panel.querySelector('[data-movement-group]');
  let lastOrder=presentation().order;
  function syncPresentation(){
    const {order,group}=presentation(),full=privacyMode()==='full';
    for(const option of orderSelect.options)option.disabled=full&&option.value.startsWith('value_');
    orderSelect.value=order;sizeSelect.value=state.pageSize;
    groupSelect.querySelector('option[value=date]').disabled=!order.startsWith('date_');
    groupSelect.value=group;
    panel.querySelector('[data-group-note]').textContent=group==='institution'||group==='category'
      ?'Grupos desta página. A ordenação vale dentro de cada grupo.':'';
  }
  for(const [select,key,read] of [[orderSelect,'order',String],[sizeSelect,'pageSize',Number],[groupSelect,'group',String]]){
    select.onchange=()=>{
      state[key]=read(select.value);state.page=1;
      try{localStorage.setItem(preferencesKey,JSON.stringify({pageSize:state.pageSize,order:state.order,group:state.group}))}catch{}
      syncPresentation();lastOrder=presentation().order;load();
    };
  }
  state.periodDefaults||={start:state.start,end:state.end,currency:state.currency};
  panel.querySelector('[data-reset-flow]').onclick=()=>{
    Object.assign(state,Object.fromEntries(names.map(key=>[key,''])),state.periodDefaults,
      {history:'0',product:'BANK',status:'POSTED',direction:'all',bill_id:'',page:1});
    for(const key of drilldownKeys)state[key]='';
    syncForm();load();
  };
  form.onsubmit=e=>{e.preventDefault();if(state.bill_id&&(form.elements.connection_id.value!==state.connection_id||form.elements.account_id.value!==state.account_id||form.elements.product.value!=='CREDIT'))state.bill_id='';form.querySelector('[data-bill-filter]').hidden=!state.bill_id;if(form.elements.start.value>form.elements.end.value){form.elements.end.setCustomValidity('Data final anterior à inicial.');form.elements.end.reportValidity();return}for(const n of names)state[n]=form.elements[n].value;state.group_by=form.elements.group_by.value;state.group_order=form.elements.group_order.value;state.history=form.elements.history.checked?'1':'0';state.page=1;syncForm();load()};
  for(const n of ['start','end'])form.elements[n].oninput=()=>form.elements.end.setCustomValidity('');
  form.querySelector('[data-clear-bill]').onclick=()=>{state.bill_id='';state.page=1;syncForm();load()};
  function update(context,{load:immediately=true}={}){
    for(const key of [...classificationKeys,...drilldownKeys])state[key]='';
    Object.assign(state,context,{page:1});syncForm();
    if(context.openClassification)classification.toggle(true);
    else if(immediately)load();
  }
  host.addEventListener('of-tab-selected',event=>{if(event.detail==='flow'){syncForm();load()}else queries.cancel()});
  function privacyChanged(){
    syncPresentation();
    const currentOrder=presentation().order;
    if(lastOrder!==currentOrder){
      lastOrder=currentOrder;
      if(!panel.hidden){state.page=1;load()}
    }
    const select=form.elements.group_order,hidden=privacyMode()==='full';
    select.querySelector('option[value=magnitude]').disabled=hidden;
    if(hidden&&state.group_order==='magnitude'){
      state.group_order='count';select.value='count';
      if(!panel.hidden&&classification.open())load();
    }else if(hidden&&select.value==='magnitude')select.value='count';
  }
  host.addEventListener('finance-privacy-changed',privacyChanged);
  syncForm();privacyChanged();if(!panel.hidden)load();return {update};
}
