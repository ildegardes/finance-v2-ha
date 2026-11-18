import {bridgePanel,cardPanel,incomePanel} from './open-finance-insights.js';
import {createQueryGeneration} from './query-generation.js';
import {bankMoney,dateBR,privacyMode,PRIVACY_MODES} from './privacy.js';
import {activeConnections,connectionLabel} from './open-finance-status.js';
import {categoryLabel,classLabel,countBR,coverageLabel,institutionName,percentBR} from './open-finance-labels.js';

const dayMs=86400000;
const iso=date=>date.toISOString().slice(0,10);
const asDate=value=>new Date(value+'T00:00:00Z');
const shift=(value,days)=>iso(new Date(+asDate(value)+dayMs*days));
const monthStart=value=>value.slice(0,7)+'-01';
const minDate=(a,b)=>a<b?a:b;
const maxDate=(a,b)=>a>b?a:b;
const decimalScale=10n**20n;
const periodLabels={month:'Este mês',previous:'Mês anterior',days30:'Últimos 30 dias',days90:'Últimos 90 dias',year:'Este ano',yearRolling:'Últimos 12 meses',custom:'Personalizado'};
const directionLabels={incoming:'Entradas',outgoing:'Saídas'};
const palette=['#08765f','#377db8','#9461aa','#c57925','#6e8320','#95705c','#5a737e'];
const resources={accounts:'Contas',investments:'Investimentos',transactions:'Movimentações'};
const icons={
  accounts:'M3 7h18v12H3z M3 11h18 M7 15h3',
  investments:'M4 19V5 M4 19h16 M8 14l4-4 3 2 5-6',
  incoming:'M6 6l12 12 M9 18h9V9',
  outgoing:'M6 18 18 6 M9 6h9v9',
};

function scaled(value){
  const [whole,fraction='']=String(value).replace(/^-/,'').split('.');
  const magnitude=BigInt(whole)*decimalScale+BigInt(fraction.padEnd(20,'0'));
  return String(value).startsWith('-')?-magnitude:magnitude;
}

function decimal(value){
  const magnitude=value<0n?-value:value;
  const digits=(magnitude%decimalScale).toString().padStart(20,'0').replace(/0+$/,'');
  return (value<0n?'-':'')+(magnitude/decimalScale).toString()+(digits?'.'+digits:'');
}

function fraction(part,total){
  return total>0n?Number(part*1000000n/total)/1000000:0;
}

function periodRange(key,today){
  const month=monthStart(today);
  if(key==='previous')return [monthStart(shift(month,-1)),shift(month,-1)];
  if(key==='days30')return [shift(today,-29),today];
  if(key==='days90')return [shift(today,-89),today];
  if(key==='yearRolling'){
    const first=asDate(month);first.setUTCMonth(first.getUTCMonth()-11);return [iso(first),today];
  }
  if(key==='year')return [today.slice(0,4)+'-01-01',today];
  return [month,today];
}

function bucketBounds(day,grouping){
  if(grouping==='day')return [day,day];
  if(grouping==='week'){
    const start=shift(day,-((asDate(day).getUTCDay()+6)%7));
    return [start,shift(start,6)];
  }
  const start=monthStart(day),next=asDate(start);
  next.setUTCMonth(next.getUTCMonth()+1);
  return [start,shift(iso(next),-1)];
}

function flowBuckets(series,filters,grouping){
  const buckets=new Map();
  for(const point of series){
    if(point.product!=='BANK'||!Object.hasOwn(directionLabels,point.direction))continue;
    const [first,last]=bucketBounds(point.date,grouping);
    const bucket=buckets.get(first)||{start:maxDate(first,filters.start),end:minDate(last,filters.end)};
    bucket[point.direction]=(bucket[point.direction]??0n)+scaled(point.value);
    buckets.set(first,bucket);
  }
  // Preserve time intervals without creating an unbounded number of empty controls.
  const days=(+asDate(filters.end)-+asDate(filters.start))/dayMs+1;
  if(days<=(grouping==='month'?3660:grouping==='week'?1098:366)){
    for(let day=filters.start;day<=filters.end;){
      const [first,last]=bucketBounds(day,grouping);
      if(!buckets.has(first))buckets.set(first,{start:day,end:minDate(last,filters.end)});
      if(last>=filters.end)break;
      day=shift(last,1);
    }
  }
  return [...buckets.values()].sort((a,b)=>a.start.localeCompare(b.start));
}

function flowChart(data,filters,grouping,page,mode,money,esc){
  if(mode==='full')return '<p class="of-chart-placeholder">Gráfico oculto em privacidade total.</p>';
  const series=(data.series||[]).filter(point=>point.product==='BANK');
  if(!series.length)return '<p class="of-chart-placeholder">'+(data.flow.BANK.coverage_state==='COMPLETE'?'Sem movimentações no período.':'Sem movimentações registradas para exibir. A cobertura do período pode estar incompleta.')+'</p>';
  const buckets=flowBuckets(series,filters,grouping);
  const pageSize=12,offset=page*pageSize;
  const displayed=buckets.slice(offset,offset+pageSize);
  const allValues=buckets.flatMap(bucket=>[bucket.incoming??0n,bucket.outgoing??0n]);
  const maximum=allValues.reduce((max,value)=>value>max?value:max,0n);
  const axis=mode==='visible'?'<div class="of-chart-axis" aria-hidden="true">'+[maximum,maximum/2n,0n].map(value=>'<span>'+esc(money(decimal(value)))+'</span>').join('')+'</div>':'';
  const navigation=buckets.length>pageSize?'<div class="of-chart-nav"><button type="button" class="of-link" data-chart-page="-1" '+(page?'':'disabled')+'>Anterior</button><span>'+esc(dateBR(displayed[0].start))+' a '+esc(dateBR(displayed.at(-1).end))+'</span><button type="button" class="of-link" data-chart-page="1" '+(offset+pageSize<buckets.length?'':'disabled')+'>Próximo</button></div>':'';
  const columns=displayed.map((bucket,index)=>{
    const period=dateBR(bucket.start)+(bucket.start===bucket.end?'':' a '+dateBR(bucket.end));
    const bars=Object.entries(directionLabels).map(([direction,label])=>{
      const value=bucket[direction];
      if(value===undefined)return '<span class="of-chart-gap" aria-hidden="true"></span>';
      const summary=label+' · '+period+(mode==='visible'?' · '+money(decimal(value)):'');
      return '<button type="button" class="of-column '+direction+'" style="--height:'+(fraction(value,maximum)*100)+'%" data-bucket="'+index+'" data-direction="'+direction+'" title="'+esc(summary)+'" aria-label="'+esc(summary)+'"></button>';
    }).join('');
    return '<div class="of-chart-group"><div class="of-column-pair">'+bars+'</div><time datetime="'+bucket.start+'" aria-hidden="true">'+esc(dateBR(bucket.start).slice(0,5))+'</time></div>';
  }).join('');
  const alternative='<details class="of-chart-alternative"><summary>Ver dados do gráfico em texto</summary><ul>'+displayed.map(bucket=>{
    const period=dateBR(bucket.start)+(bucket.start===bucket.end?'':' a '+dateBR(bucket.end));
    const values=Object.entries(directionLabels).map(([direction,label])=>label+' '+(bucket[direction]===undefined?(data.flow.BANK.coverage_state==='COMPLETE'?'sem movimentos':'sem registro'):(mode==='visible'?money(decimal(bucket[direction])):'com registros'))).join(' · ');
    return '<li>'+esc(period+' · '+values)+'</li>';
  }).join('')+'</ul></details>';
  return '<div class="of-chart-legend"><span>Entradas</span><span>Saídas</span></div><div class="of-chart-frame">'+axis+'<div class="of-chart-groups">'+columns+'</div></div>'+navigation+alternative;
}

function allocation(investments,mode,amount,esc){
  if(mode==='full')return '<p class="of-chart-placeholder">Composição oculta em privacidade total.</p>';
  const classes=investments.by_class||[];
  if(!classes.length)return '<p class="of-chart-placeholder">Distribuição indisponível para esta moeda.</p>';
  const values=classes.map(item=>item.value==null?null:scaled(item.value));
  const total=values.reduce((sum,value)=>sum+(value??0n),0n);
  const proportional=total>0n&&values.every(value=>value===null||value>=0n)
    && !(investments.items||[]).some(item=>item.value!=null&&scaled(item.value)<0n);
  let cumulative=0n;
  const bands=values.flatMap((value,index)=>{
    if(!proportional||!value)return [];
    const start=100*fraction(cumulative,total);
    cumulative+=value;
    return [palette[index%palette.length]+' '+start+'% '+(100*fraction(cumulative,total))+'%'];
  });
  const chart=proportional?'<div class="of-allocation-ring" style="--segments:conic-gradient('+bands.join(',')+')"><div><small>Total representado</small><strong>'+amount(decimal(total))+'</strong></div></div>':'';
  const legend=classes.map((item,index)=>{
    const share=values[index]===null||!proportional?'':'<small>'+esc(percentBR.format(fraction(values[index],total)))+'</small>';
    return '<li><span class="of-allocation-dot" aria-hidden="true" style="--dot:'+palette[index%palette.length]+'"></span><button type="button" class="of-link" data-investment-class="'+esc(item.type)+'">'+esc(classLabel(item.type))+'</button><strong>'+amount(item.value)+'</strong>'+share+'</li>';
  }).join('');
  return '<div class="of-allocation-layout">'+chart+'<ul class="of-allocation-legend">'+legend+'</ul></div>'+
    (!proportional?'<p>Os valores informados aparecem na lista. A distribuição proporcional está indisponível.</p>':'');
}

function categoryRanking(data,mode,amount,esc){
  if(mode==='full')return '<p class="of-chart-placeholder">Ranking oculto em privacidade total.</p>';
  const rows=[...(data.category_ranking?.BANK||[])].sort((a,b)=>scaled(a.value)>scaled(b.value)?-1:scaled(a.value)<scaled(b.value)?1:0);
  if(!rows.length)return '<p class="of-chart-placeholder">Nenhuma saída informada para os filtros selecionados.</p>';
  const total=rows.reduce((sum,row)=>sum+scaled(row.value),0n);
  return '<ul class="of-ranking">'+rows.map(row=>{
    const value=scaled(row.value);
    const label=esc(categoryLabel(row));
    const control=row.key==='other'?'<span>'+label+'</span>':'<button type="button" class="of-link" data-overview-category="'+esc(row.key)+'">'+label+'</button>';
    return '<li><div>'+control+'<strong>'+amount(row.value)+'</strong>'+(total>0n?'<small>'+esc(percentBR.format(fraction(value,total)))+'</small>':'')+'</div><span aria-hidden="true" class="of-ranking-track"><i style="width:'+(100*fraction(value,total))+'%"></i></span></li>';
  }).join('')+'</ul>';
}

function positionRows(data,catalog,amount,esc){
  const current=(data.institutions||[]).filter(row=>row.current);
  if(!current.length)return '<p class="of-chart-placeholder">Nenhuma conexão ativa neste escopo.</p>';
  const active=activeConnections(catalog);
  return '<div class="of-position-list">'+current.map(row=>{
    const connection=active.find(c=>c.id===row.connection_id);
    const name=connection?connectionLabel(connection,active):institutionName(row.institution);
    const groups=[['Saldo em contas',row.accounts],['Investimentos',row.investments]];
    const rows=groups.flatMap(([,position])=>position.items);
    const detail=rows.map(item=>'<li><strong>'+esc(item.name||'Nome não informado')+'</strong><span>'+amount(item.value)+'</span><small>Data financeira '+esc(dateBR(item.reference_date))+' · Atualização informada pelo provedor '+esc(dateBR(item.provider_updated_at))+' · Coleta '+esc(dateBR(item.observed_at))+(item.freshness?.state==='STALE'?' · Desatualização informada':'')+'</small></li>').join('');
    const stale=rows.some(item=>item.freshness?.state==='STALE');
    return '<article class="of-position" data-position-connection="'+esc(row.connection_id)+'"><div class="of-position-identity"><span class="of-monogram" aria-hidden="true">'+esc(name.slice(0,2).toLocaleUpperCase('pt-BR'))+'</span><div><h4>'+esc(name)+'</h4><span>Conexão ativa'+(stale?' · Desatualização informada':'')+'</span></div></div>'+
      groups.map(([title,position])=>'<div class="of-position-value"><span>'+title+'</span><strong>'+amount(position.value)+'</strong><small>'+esc(coverageLabel(position.coverage_state))+'</small></div>').join('')+
      '<div class="of-position-actions"><button type="button" class="of-link" data-overview-institution="'+esc(row.connection_id)+'">Ver movimentações</button>'+(detail?'<details><summary>Ver posições e datas</summary><ul class="of-category-list">'+detail+'</ul></details>':'')+'</div></article>';
  }).join('')+'</div>';
}

export function mountAnalyticsOverview({host,api,esc,catalog,navigation,state,today,onNavigate=()=>{},onAssets=()=>{},onCards=()=>{},onConnections=()=>{}}) {
  const panel=host.querySelector('#of-panel-overview');
  today ||= new Intl.DateTimeFormat('sv-SE',{timeZone:'America/Sao_Paulo'}).format(new Date());
  const [first,last]=periodRange('month',today);
  state.start ||= first;
  state.end ||= last;
  state.currency ||= 'BRL';
  const active=activeConnections(catalog);
  const options=active.map(c=>'<option value="'+esc(c.id)+'">'+esc(connectionLabel(c,active))+'</option>').join('');
  const presets=Object.entries(periodLabels).map(([value,label])=>'<option value="'+value+'">'+label+'</option>').join('');
  panel.innerHTML='<div class="of-overview"><form class="of-dashboard-filters" aria-label="Filtros da visão geral"><div class="of-overview-header"><div><h2>Visão geral</h2></div><label>Privacidade<select name="privacy" aria-label="Privacidade">'+Object.entries(PRIVACY_MODES).map(([value,label])=>'<option value="'+value+'">'+label+'</option>').join('')+'</select></label></div>'+
    '<div class="of-overview-filters"><label>Instituição<select name="connection_id" aria-label="Instituição"><option value="">Todas as ativas</option>'+options+'<option value="!history">Histórico completo</option></select></label><label>Moeda<input name="currency" pattern="[A-Z]{3}" maxlength="3" required></label><label>Período<select name="preset" aria-label="Período">'+presets+'</select></label><label>De<input type="date" name="start" required></label><label>Até<input type="date" name="end" required></label><button type="submit">Aplicar</button></div></form><div data-overview-result aria-live="polite"></div></div>';
  const form=panel.querySelector('form'),result=panel.querySelector('[data-overview-result]');
  const people=form.elements.connection_id,privacy=form.elements.privacy;
  const queries=createQueryGeneration(navigation);
  const fields=['start','end','currency'];
  let filters,loaded=null,grouping,chartPage=0,flowMode='gross';
  const bucketFor=()=>flowMode==='adjusted'?'operating':'internal';
  function chartData(){
    if(flowMode==='gross'||!loaded.insights)return loaded;
    return {flow:{BANK:{coverage_state:loaded.insights.coverage==='COMPLETE_BANK_SCOPE'?'COMPLETE':'PARTIAL'}},
      series:loaded.insights.series.filter(row=>row.bucket===bucketFor()).map(row=>({...row,product:'BANK'}))};
  }
  host.dataset.ofPrivacyHost='';
  function paint(){
    const mode=privacyMode(host.ownerDocument);
    privacy.value=mode;
    if(!loaded)return;
    const accounts=loaded.positions.accounts,investments=loaded.positions.investments,flow=loaded.flow.BANK;
    const money=value=>bankMoney(value,filters.currency);
    const amount=value=>value==null?'Indisponível':mode==='visible'?esc(money(value)):'<span aria-label="Valor oculto">••••••</span>';
    const metric=(icon,title,value,detail)=>'<article class="of-metric of-kpi"><div><span class="of-kpi-icon '+icon+'"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="'+icons[icon]+'"></path></svg></span><h3><button type="button" class="of-link" data-metric="'+icon+'">'+title+'</button></h3></div><strong>'+amount(value)+'</strong><small>'+esc(detail)+'</small></article>';
    const positionNote=position=>countBR.format(position.known||0)+' '+(position.known===1?'posição informada':'posições informadas')+' · '+coverageLabel(position.coverage_state);
    const insights=loaded.insights,showAdjusted=insights&&flowMode==='adjusted',showInternal=insights&&flowMode==='internal';
    const flowTitle=showAdjusted?'Resultado econômico identificado':showInternal?'Movimentações internas':'Fluxo bancário líquido';
    const net=showAdjusted?insights.known.net:showInternal?null:flow.net??flow.observed_net;
    const netNote=showAdjusted?(insights.coverage==='COMPLETE_BANK_SCOPE'?'Cobertura integral da janela bancária':'Cobertura parcial dos movimentos bancários') :showInternal?'Transferências e movimentações internas confirmadas':flow.net!=null?'Entradas menos saídas':net!=null?'Saldo dos movimentos conhecidos · cobertura parcial':'Resultado indisponível para a cobertura deste período';
    const comparison=flow.comparison?'<p class="of-comparison">Diferença frente a '+esc(dateBR(flow.comparison.start))+' a '+esc(dateBR(flow.comparison.end))+' · Entradas '+amount(flow.comparison.incoming)+' · Saídas '+amount(flow.comparison.outgoing)+' · Fluxo '+amount(flow.comparison.net)+'</p>':'<p class="of-comparison">Comparação com período anterior indisponível.</p>';
    const coverage=loaded.coverage||[];
    const lastCollection=coverage.map(point=>point.observed_at).filter(Boolean).sort().at(-1);
    const quality=Object.entries(resources).map(([kind,label])=>{
      const points=coverage.filter(point=>point.resource===kind);
      return '<li><strong>'+label+'</strong><span>'+esc(coverageLabel(kind==='transactions'?flow.coverage_state:loaded.positions[kind].coverage_state))+'</span>'+(points.some(point=>point.state==='FAILED'||point.state==='NOT_AVAILABLE'||point.state==='NOT_AUTHORIZED')?'<small>Há recursos com indisponibilidade neste escopo.</small>':'')+'</li>';
    }).join('');
    result.innerHTML=(filters.history==='1'?'<p class="of-notice">Histórico completo · O fluxo inclui conexões arquivadas. As posições abaixo têm como referência somente conexões ativas.</p>':'')+
      '<div class="of-metrics">'+metric('accounts','Saldo em contas',accounts.value,positionNote(accounts))+metric('investments','Investimentos',investments.value,positionNote(investments))+metric('incoming','Entradas bancárias',flow.reported?.incoming,coverageLabel(flow.coverage_state))+metric('outgoing','Saídas bancárias',flow.reported?.outgoing,coverageLabel(flow.coverage_state))+'</div>'+
      '<section class="of-summary-card of-bank-flow"><div class="of-section-heading"><div><h3>'+flowTitle+'</h3>'+
      (showInternal?'<p>Entradas '+amount(insights.bridge.internal.incoming)+' · Saídas '+amount(insights.bridge.internal.outgoing)+'</p>':'<strong class="of-net-value">'+amount(net)+'</strong>')+
      '<p>'+netNote+'</p></div><div class="actions of-insight-selects">'+(insights?'<label>Visão do fluxo<select data-financial-flow aria-label="Visão do fluxo"><option value="gross">Fluxo bancário bruto</option><option value="adjusted">Fluxo ajustado</option><option value="internal">Movimentações internas</option></select></label>':'')+
      '<label>Agrupar por<select data-grouping aria-label="Agrupar por"><option value="day">Dia</option><option value="week">Semana</option><option value="month">Mês</option></select></label></div></div>'+
      '<div data-flow-chart>'+flowChart(chartData(),filters,grouping,chartPage,mode,money,esc)+'</div>'+
      (flowMode==='gross'?comparison:'')+bridgePanel(insights,amount,esc)+
      (insights?.unresolved_scope?'<p>Há registros fora do recorte por falta de data, moeda ou situação comprovada.</p>':'')+
      (insights?'<button type="button" class="of-link" data-classification-pending>Ver '+countBR.format(insights.pending)+' movimentações pendentes de classificação</button>':'')+
      '</section>'+
      '<div class="of-overview-grid"><section class="of-summary-card"><div class="of-section-heading"><div><h3>Composição da carteira</h3><p>'+esc(coverageLabel(investments.coverage_state))+'</p></div><button type="button" class="of-link" data-open-assets>Ver investimentos</button></div>'+allocation(investments,mode,amount,esc)+'</section><section class="of-summary-card"><h3>Principais categorias de saída</h3><p>Participação nas saídas informadas</p>'+categoryRanking(loaded,mode,amount,esc)+'</section></div>'+
      '<div class="of-overview-grid"><section class="of-summary-card" data-current-positions tabindex="-1"><h3>Posições por instituição</h3><p>Últimas posições conhecidas. O período selecionado vale para movimentações.</p>'+positionRows(loaded,catalog,amount,esc)+'</section>'+cardPanel(loaded.cards,amount,mode,esc)+'</div>'+incomePanel(insights,amount,mode,esc)+
      '<details class="of-summary-card of-quality"><summary>Qualidade dos dados</summary><ul class="of-category-list">'+quality+'</ul><p>Última coleta registrada no escopo '+esc(dateBR(lastCollection))+'. Consulte as posições para ver a data financeira e a atualização informada pelo provedor.</p><p>Movimentos brutos incluem transferências e pagamentos. Posições e saldos podem se sobrepor.</p><div class="actions"><button type="button" class="of-link" data-open-connections>Conexões</button><button type="button" class="of-link" data-open-diagnostics>Diagnóstico</button></div></details>';
    result.querySelector('[data-grouping]').value=grouping;
    const kind=result.querySelector('[data-financial-flow]');
    if(kind)kind.value=flowMode;
  }

  function syncForm(){
    for(const key of fields)form.elements[key].value=state[key];
    people.value=state.history==='1'?'!history':active.some(c=>c.id===state.connection_id)?state.connection_id:'';
    form.elements.preset.value=Object.keys(periodLabels).filter(key=>key!=='custom').find(key=>{
      const [start,end]=periodRange(key,today);
      return start===state.start&&end===state.end;
    })||'custom';
  }
  async function load(){
    const query=queries.begin();
    filters={start:form.elements.start.value,end:form.elements.end.value,currency:form.elements.currency.value,
      history:people.value==='!history'?'1':'0',connection_id:people.value==='!history'?'':people.value};
    Object.assign(state,filters);
    const days=(+asDate(filters.end)-+asDate(filters.start))/dayMs+1;
    grouping=days<=14?'day':days<=90?'week':'month';
    chartPage=0;
    loaded=null;
    result.innerHTML='<p role="status" class="of-chart-placeholder">Carregando resumo bancário…</p>';
    result.setAttribute('aria-busy','true');
    const params=new URLSearchParams({...filters,product:'BANK',status:'POSTED'});
    if(!filters.connection_id)params.delete('connection_id');
    try{
      const response=await api('/open-finance/analytics?'+params,{queryScope:query});
      if(!query.current()||!host.isConnected)return;
      loaded=response;
      paint();
    }catch(_){
      if(query.current()&&host.isConnected){
        loaded=null;
        result.innerHTML='<p role="alert" class="attention">Não foi possível carregar o resumo bancário.</p><button type="button" data-retry-summary>Tentar novamente</button>';
      }
    }finally{if(query.current())result.removeAttribute('aria-busy')}
  }

  function filtersChanged(){
    queries.cancel();
    loaded=null;
    result.removeAttribute('aria-busy');
    result.innerHTML='<p role="status" class="of-chart-placeholder">Filtros alterados. Aplique para consultar.</p>';
  }
  people.onchange=filtersChanged;
  form.elements.currency.oninput=filtersChanged;
  form.onsubmit=event=>{
    event.preventDefault();
    if(form.elements.start.value>form.elements.end.value){
      form.elements.end.setCustomValidity('A data final deve ser igual ou posterior à inicial.');
      form.elements.end.reportValidity();
      return;
    }
    load();
  };
  for(const key of ['start','end'])form.elements[key].oninput=()=>{
    form.elements.end.setCustomValidity('');
    form.elements.preset.value='custom';
    filtersChanged();
  };
  form.elements.preset.onchange=()=>{
    if(form.elements.preset.value==='custom'){form.elements.start.focus();return}
    const [start,end]=periodRange(form.elements.preset.value,today);
    form.elements.start.value=start;form.elements.end.value=end;
    form.elements.end.setCustomValidity('');
    form.requestSubmit();
  };
  privacy.value=privacyMode(host.ownerDocument);
  privacy.onchange=()=>host.ownerDocument.dispatchEvent(new CustomEvent('finance-privacy-request',{detail:privacy.value}));
  host.addEventListener('finance-privacy-changed',paint);
  host.addEventListener('of-tab-selected',event=>{
    if(event.detail==='overview'){syncForm();load()}
    else queries.cancel();
  });
  result.onchange=event=>{
    if(event.target.matches('[data-financial-flow]')){
      flowMode=event.target.value;chartPage=0;paint();result.querySelector('[data-financial-flow]').focus();return;
    }
    if(!event.target.matches('[data-grouping]'))return;
    grouping=event.target.value;chartPage=0;paint();
    result.querySelector('[data-grouping]').focus();
  };
  result.onclick=event=>{
    const button=event.target.closest('button');
    if(!button)return;
    if(button.matches('[data-retry-summary]')){load();return}
    const context={...filters,account_id:'',product:'BANK',status:'POSTED',direction:'all',category:'',search:'',bill_id:''};
    if(button.dataset.metric==='accounts'){
      const target=result.querySelector('[data-current-positions]');target.focus();target.scrollIntoView({block:'start'});
    }else if(button.matches('[data-open-income]')){
      onAssets({...context,income:true});
    }else if(button.matches('[data-overview-card],[data-all-overview-cards]')){
      const card=button.dataset.overviewCard===undefined?null:loaded.cards.items[Number(button.dataset.overviewCard)];
      onCards({connection_id:card?.connection_id||filters.connection_id,account_id:card?.account_id||'',currency:filters.currency});
    }else if(button.matches('[data-classification-pending]')){
      onNavigate({...context,bucket:'pending',openClassification:true});
    }else if(button.dataset.insightBucket){
      onNavigate({...context,bucket:button.dataset.insightBucket,direction:button.dataset.insightDirection});
    }else if(button.matches('[data-investment-class],[data-open-assets],[data-metric="investments"]')){
      onAssets({connection_id:filters.connection_id,currency:filters.currency,type:button.dataset.investmentClass||''});
    }else if(button.matches('[data-open-connections],[data-open-diagnostics]')){
      onConnections(filters.connection_id,button.matches('[data-open-diagnostics]'));
    }else if(button.dataset.metric){
      onNavigate({...context,direction:button.dataset.metric});
    }else if(button.dataset.overviewCategory){
      const row=loaded.category_ranking.BANK.find(item=>item.key===button.dataset.overviewCategory);
      onNavigate({...context,direction:'outgoing',category:row.key,categoryLabel:categoryLabel(row)});
    }else if(button.dataset.overviewInstitution){
      onNavigate({...context,connection_id:button.dataset.overviewInstitution,history:'0'});
    }else if(button.dataset.bucket){
      const bucket=flowBuckets(chartData().series,filters,grouping)[chartPage*12+Number(button.dataset.bucket)];
      onNavigate({...context,start:bucket.start,end:bucket.end,direction:button.dataset.direction,...(flowMode==='gross'?{}:{bucket:bucketFor()})});
    }else if(button.dataset.chartPage){
      chartPage+=Number(button.dataset.chartPage);paint();
      const next=result.querySelector('[data-chart-page="'+button.dataset.chartPage+'"]:not(:disabled)')||result.querySelector('[data-chart-page]:not(:disabled)');
      next?.focus();
    }
  };
  syncForm();
  if(!panel.hidden)load();
}
