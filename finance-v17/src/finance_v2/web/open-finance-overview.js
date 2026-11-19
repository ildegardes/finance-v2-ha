import {bankMark,cardIdentity} from './open-finance-identity.js';
import {overviewWealth,wealthMoney} from './open-finance-wealth.js';
import {presentationPreference,savePresentation,presentationControl,metricValue,metricNote,
  institutionPositions,portfolioQuality,unifiedIncomeMarkup,cardKpi,cardUsage} from './open-finance-consolidated.js';
import {portfolioPanel} from './open-finance-portfolio.js';
import {automaticPanel,bridgePanel,cardPanel,incomePanel} from './open-finance-insights.js';
import {createQueryGeneration} from './query-generation.js';
import {bankMoney,dateBR,privacyMode} from './privacy.js';
import {activeConnections,connectionLabel} from './open-finance-status.js';
import {categoryLabel,classLabel,investmentClassLabel,countBR,coverageLabel,institutionName,percentBR} from './open-finance-labels.js';

const dayMs=86400000;
const iso=date=>date.toISOString().slice(0,10);
const asDate=value=>new Date(value+'T00:00:00Z');
const shift=(value,days)=>iso(new Date(+asDate(value)+dayMs*days));
const monthStart=value=>value.slice(0,7)+'-01';
const minDate=(a,b)=>a<b?a:b;
const maxDate=(a,b)=>a>b?a:b;
const directionLabels={incoming:'Entradas',outgoing:'Saídas'};
const palette=['#08765f','#377db8','#9461aa','#c57925','#6e8320','#95705c','#5a737e'];
const resources={accounts:'Contas',investments:'Investimentos',transactions:'Movimentações'};
const icons={
  accounts:'M3 7h18v12H3z M3 11h18 M7 15h3',
  cards:'M3 6h18v13H3z M3 10h18 M6 15h4',
  income:'M4 18l5-5 4 2 6-7 M14 8h5v5',
  investments:'M4 19V5 M4 19h16 M8 14l4-4 3 2 5-6',
  incoming:'M6 6l12 12 M9 18h9V9',
  outgoing:'M6 18 18 6 M9 6h9v9',
};

function decimalMath(values){
  // Use one scale for every operand in the graph. This retains the full FX
  // decimal through chart totals and allows an exact half tick on the axis.
  const precision=values.reduce((max,value)=>Math.max(max,String(value).split('.')[1]?.length||0),0)+1;
  const scale=10n**BigInt(precision);
  const scaled=value=>{
    const text=String(value);
    const [whole,decimals='']=text.replace(/^-/,'').split('.');
    const magnitude=BigInt(whole)*scale+BigInt(decimals.padEnd(precision,'0'));
    return text.startsWith('-')?-magnitude:magnitude;
  };
  const decimal=value=>{
    const magnitude=value<0n?-value:value;
    const digits=(magnitude%scale).toString().padStart(precision,'0').replace(/0+$/,'');
    return (value<0n?'-':'')+(magnitude/scale).toString()+(digits?'.'+digits:'');
  };
  return {scaled,decimal};
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

function flowBuckets(series,filters,grouping,scaled){
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
  const {scaled,decimal}=decimalMath(series.map(point=>point.value));
  const buckets=flowBuckets(series,filters,grouping,scaled);
  const pageSize=12,offset=page*pageSize;
  const displayed=buckets.slice(offset,offset+pageSize);
  const allValues=buckets.flatMap(bucket=>[bucket.incoming??0n,bucket.outgoing??0n]);
  const maximum=allValues.reduce((max,value)=>value>max?value:max,0n);
  const axis=mode==='visible'?'<div class="of-chart-axis" aria-hidden="true">'+[maximum,maximum/2n,0n].map(value=>'<span>'+esc(money(decimal(value)))+'</span>').join('')+'</div>':'';
  const navigation=buckets.length>pageSize?'<div class="of-chart-nav"><button type="button" class="of-link" data-chart-page="-1" '+(page?'':'disabled')+'>Anterior</button><span>'+esc(dateBR(displayed[0].start))+' a '+esc(dateBR(displayed.at(-1).end))+'</span><button type="button" class="of-link" data-chart-page="1" '+(offset+pageSize<buckets.length?'':'disabled')+'>Próximo</button></div>':'';
  const columns=displayed.map(bucket=>{
    const period=dateBR(bucket.start)+(bucket.start===bucket.end?'':' a '+dateBR(bucket.end));
    const bars=Object.entries(directionLabels).map(([direction,label])=>{
      const value=bucket[direction];
      if(value===undefined)return '<span class="of-chart-gap" aria-hidden="true"></span>';
      const summary=label+' · '+period+(mode==='visible'?' · '+money(decimal(value)):'');
      return '<button type="button" class="of-column '+direction+'" style="--height:'+(fraction(value,maximum)*100)+'%" data-bucket-start="'+bucket.start+'" data-bucket-end="'+bucket.end+'" data-bucket-currency="'+esc(filters.currency)+'" data-direction="'+direction+'" title="'+esc(summary)+'" aria-label="'+esc(summary)+'"></button>';
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

function allocation(investments,mode,amount,esc,unified=false){
  if(mode==='full')return '<p class="of-chart-placeholder">Composição oculta em privacidade total.</p>';
  const classes=investments.by_class||[];
  if(!classes.length)return '<p class="of-chart-placeholder">Distribuição indisponível para esta moeda.</p>';
  const {scaled,decimal}=decimalMath([...classes,...(investments.items||[])].map(row=>row.value));
  const values=classes.map(item=>item.value==null?null:scaled(item.value));
  const total=values.reduce((sum,value)=>sum+(value??0n),0n);
  const proportional=total>0n&&values.every(value=>value===null||value>=0n)
    && !investments.negative && !(investments.items||[]).some(item=>item.value!=null&&scaled(item.value)<0n);
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
    const label=unified?'<span>'+esc(investmentClassLabel(item.type))+'</span>':'<button type="button" class="of-link" data-investment-class="'+esc(item.type)+'">'+esc(classLabel(item.type))+'</button>';
    return '<li><span class="of-allocation-dot" aria-hidden="true" style="--dot:'+palette[index%palette.length]+'"></span>'+label+'<strong>'+amount(item.value)+'</strong>'+share+'</li>';
  }).join('');
  return '<div class="of-allocation-layout">'+chart+'<ul class="of-allocation-legend">'+legend+'</ul></div>'+
    (!proportional?'<p>Os valores informados aparecem na lista. A distribuição proporcional está indisponível.</p>':'');
}

function moneyGroups(groups,render,grouped){
  return groups.map(([currency,view])=>'<div class="of-currency-group">'+(grouped?'<h4>'+escCurrency(currency)+'</h4>':'')+render(view,currency)+'</div>').join('');
}

function escCurrency(currency){return /^[A-Z]{3}$/.test(currency)?currency:'';}

function unifiedAllocation(view,mode,esc){
  if(mode==='full')return '<p class="of-chart-placeholder">Composição oculta em privacidade total.</p>';
  const groups=new Map();
  for(const row of view.composition){
    for(const [currency,value] of Object.entries(row.metric.amounts)){
      if(!groups.has(currency))groups.set(currency,{by_class:[],negative:false});
      const group=groups.get(currency);
      group.by_class.push({type:row.class,value});
      group.negative||=row.negative;
    }
  }
  return (view.investments.partial?'<p>'+esc(metricNote(view.investments))+'</p>':'')+
    (groups.size?moneyGroups([...groups],(data,currency)=>allocation(data,mode,value=>wealthMoney(value,currency,esc),esc,true),view.currency==='original'):
      '<p class="of-chart-placeholder">Composição indisponível para este escopo.</p>');
}

function categoryRanking(data,mode,amount,esc,economic){
  if(mode==='full')return '<p class="of-chart-placeholder">Ranking oculto em privacidade total.</p>';
  const rows=[...((economic?data.economic_category_ranking:data.category_ranking?.BANK)||[])];
  const {scaled}=decimalMath(rows.map(row=>row.value));
  rows.sort((a,b)=>scaled(a.value)>scaled(b.value)?-1:scaled(a.value)<scaled(b.value)?1:0);
  if(!rows.length){
    const note=economic&&data.insights?.pending?'Há movimentações pendentes de classificação.':
      data.flow.BANK.coverage_state!=='COMPLETE'&&!data.flow.BANK.reported?.outgoing?'Cobertura insuficiente para determinar as despesas.':
      !data.total?'Nenhuma movimentação no período.':economic?'Nenhuma despesa econômica identificada.':'Nenhuma saída bancária no período.';
    return '<p class="of-chart-placeholder">'+note+'</p>';
  }
  const total=rows.reduce((sum,row)=>sum+scaled(row.value),0n);
  return '<ul class="of-ranking">'+rows.map(row=>{
    const value=scaled(row.value);
    const label=esc(categoryLabel(row));
    const control=row.key==='other'?'<span>'+label+'</span>':'<button type="button" class="of-link" data-overview-category="'+esc(row.key)+'">'+label+'</button>';
    const suggested=row.review?.includes('SUGGESTED')?'<small>Inclui sugestões</small>':row.count?'<small>'+countBR.format(row.count)+' movimentos</small>':'';
    return '<li><div>'+control+suggested+'<strong>'+amount(row.value)+'</strong>'+(total>0n?'<small>'+esc(percentBR.format(fraction(value,total)))+'</small>':'')+'</div><span aria-hidden="true" class="of-ranking-track"><i style="width:'+(100*fraction(value,total))+'%"></i></span></li>';
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
    return '<article class="of-position" data-position-connection="'+esc(row.connection_id)+'"><div class="of-position-identity">'+bankMark(row.institution,esc)+'<div><h4>'+esc(name)+'</h4><span>Conexão ativa'+(stale?' · Desatualização informada':'')+(row.last_sync?' · '+esc(dateBR(row.last_sync)):'')+'</span></div></div>'+
      groups.map(([title,position])=>'<div class="of-position-value"><span>'+title+'</span><strong>'+amount(position.value)+'</strong><small>'+esc(coverageLabel(position.coverage_state))+'</small></div>').join('')+
      '<div class="of-position-actions"><button type="button" class="of-link" data-overview-institution="'+esc(row.connection_id)+'">Movimentações</button><button type="button" class="of-link" data-institution-assets="'+esc(row.connection_id)+'">Investimentos</button><button type="button" class="of-link" data-institution-connection="'+esc(row.connection_id)+'">Conexão</button>'+(detail?'<details><summary>Ver posições e datas</summary><ul class="of-category-list">'+detail+'</ul></details>':'')+'</div></article>';
  }).join('')+'</div>';
}

export function mountAnalyticsOverview({host,api,esc,catalog,navigation,state,today,international=false,consolidated=false,onUnified=()=>{},onPeriod=()=>{},onNavigate=()=>{},onAssets=()=>{},onCards=()=>{},onConnections=()=>{}}) {
  const panel=host.querySelector('#of-panel-overview');
  today ||= new Intl.DateTimeFormat('sv-SE',{timeZone:'America/Sao_Paulo'}).format(new Date());
  const [first,last]=periodRange('month',today);
  state.start ||= first;
  state.end ||= last;
  state.currency ||= 'BRL';
  if(consolidated)state.presentation=presentationPreference();
  const active=activeConnections(catalog);
  const options=active.map(c=>'<option value="'+esc(c.id)+'">'+esc(connectionLabel(c,active))+'</option>').join('');
  panel.innerHTML='<div class="of-overview"><form class="of-dashboard-filters'+(consolidated?' of-global-filters':'')+'" aria-label="Filtros da visão geral">'+
    '<div class="of-timebar"><label>Período<select name="preset" aria-label="Período"><option value="month">Mensal</option><option value="year">Anual</option><option value="custom">Personalizado</option><optgroup label="Atalhos"><option value="previous">Mês anterior</option><option value="days30">Últimos 30 dias</option><option value="days90">Últimos 90 dias</option><option value="yearRolling">Últimos 12 meses</option></optgroup></select></label>'+
    '<div class="of-period-step"><button type="button" class="quiet" data-period-step="-1" aria-label="Período anterior">‹</button>'+
    '<input type="month" name="month" aria-label="Mês e ano selecionados"><input type="number" name="year" min="1900" aria-label="Ano selecionado" hidden>'+
    '<button type="button" class="quiet" data-period-step="1" aria-label="Próximo período">›</button></div>'+
    '<button type="button" class="quiet" data-period-now>Período atual</button>'+
    (consolidated?presentationControl(state.presentation):'')+'</div>'+
    '<div class="of-overview-filters"><label>Instituição<select name="connection_id" aria-label="Instituição"><option value="">Todas as ativas</option>'+options+'<option value="!history">Histórico completo</option></select></label>'+
    (consolidated?'<input name="currency" type="hidden">':'<label>Moeda<input name="currency" pattern="[A-Z]{3}" maxlength="3" required></label>')+'<label>De<input type="date" name="start" required></label><label>Até<input type="date" name="end" required></label><button type="submit">Aplicar</button></div></form><div data-overview-result aria-live="polite"></div></div>';
  const form=panel.querySelector('form'),result=panel.querySelector('[data-overview-result]');
  const people=form.elements.connection_id;
  const nativeOptions=new Set([...people.options].map(option=>option.value));
  const queries=createQueryGeneration(navigation);
  const fields=['start','end','currency'];
  let filters,loaded=null,grouping,chartPage=0,flowMode=state.perspective==='gross'?'gross':'adjusted';
  const bucketFor=()=>'operating';
  function chartData(view){
    if(flowMode==='gross'||!view.insights)return view;
    return {flow:{BANK:{coverage_state:view.insights.coverage==='COMPLETE_BANK_SCOPE'?'COMPLETE':'PARTIAL'}},
      series:view.insights.series.filter(row=>row.bucket===bucketFor()).map(row=>({...row,product:'BANK'}))};
  }
  host.dataset.ofPrivacyHost='';
  function paint(){
    const mode=privacyMode(host.ownerDocument);
    if(!loaded)return;
    const shared=loaded.presentation_view;
    const views=shared?Object.entries(shared.movements):[[filters.currency,loaded]];
    const grouped=shared?.currency==='original';
    const preferred=views.find(([currency])=>currency===(grouped?filters.currency:shared?.currency))||views[0];
    const secondary=preferred?.[1]||loaded;
    const displayCurrency=preferred?.[0]||(shared?.currency==='USD'?'USD':filters.currency);
    const accounts=loaded.positions.accounts,investments=loaded.positions.investments,flow=secondary.flow.BANK;
    const cards=shared?.cards||loaded.cards,history=shared?.history||loaded.portfolio_history;
    const money=value=>bankMoney(value,displayCurrency);
    const amount=value=>value==null?'Indisponível':mode==='visible'?esc(money(value)):'<span aria-label="Valor oculto">••••••</span>';
    const metric=(icon,title,value,detail,override)=>'<article class="of-metric of-kpi"><div><span class="of-kpi-icon '+icon+'"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="'+icons[icon]+'"></path></svg></span><h3><button type="button" class="of-link" data-metric="'+icon+'">'+title+'</button></h3></div><strong>'+(override??amount(value))+'</strong><small>'+esc(detail)+'</small></article>';
    const currentWealth=loaded.wealth?.summary;
    const wealthCurrency=state.wealthPresentation||'original';
    const wealthValue=wealthCurrency==='original'?currentWealth?.original[filters.currency]?.positions:
      currentWealth?.converted.positions;
    const wealthMetric=wealthCurrency==='original'?wealthMoney(wealthValue,filters.currency,esc):
      wealthMoney(wealthValue??currentWealth?.converted_subtotal.positions,wealthCurrency,esc);
    const wealthDetail=wealthCurrency==='original'?'Posições em '+filters.currency:
      wealthValue==null?'Subtotal em '+wealthCurrency+' · cobertura incompleta':'Convertido para '+wealthCurrency;
    const positionNote=position=>{
      const dates=(position.items||[]).map(item=>item.reference_date).filter(Boolean).sort();
      return dates.length?'Última referência '+dateBR(dates.at(-1)):countBR.format(position.known||0)+' posições informadas';
    };
    const insights=secondary.insights,showAdjusted=insights&&flowMode==='adjusted';
    const economicNote=insights?.coverage==='COMPLETE_BANK_SCOPE'?'Janela bancária coberta':'Subtotal identificado · cobertura bancária parcial';
    const flowTitle=showAdjusted?'Resultado econômico identificado':'Fluxo bancário líquido';
    const net=showAdjusted?insights.known.net:flow.net??flow.observed_net;
    const netNote=showAdjusted?(economicNote) :flow.net!=null?'Entradas menos saídas':net!=null?'Saldo dos movimentos conhecidos · cobertura parcial':'Resultado indisponível para a cobertura deste período';
    const comparable=shared?null:showAdjusted?insights.comparison:flow.comparison;
    const comparison=comparable?'<p class="of-comparison">Diferença frente a '+esc(dateBR(comparable.start))+' a '+esc(dateBR(comparable.end))+' · Entradas '+amount(comparable.incoming)+' · Saídas '+amount(comparable.outgoing)+' · Fluxo '+amount(comparable.net)+'</p>':'<p class="of-comparison">Comparação com período anterior indisponível.</p>';
    const coverage=loaded.coverage||[];
    const lastCollection=coverage.map(point=>point.observed_at).filter(Boolean).sort().at(-1);
    const quality=Object.entries(resources).map(([kind,label])=>{
      const points=coverage.filter(point=>point.resource===kind);
      return '<li><strong>'+label+'</strong><span>'+esc(coverageLabel(kind==='transactions'?flow.coverage_state:loaded.positions[kind].coverage_state))+'</span>'+(points.some(point=>point.state==='FAILED'||point.state==='NOT_AVAILABLE'||point.state==='NOT_AUTHORIZED')?'<small>Há recursos com indisponibilidade neste escopo.</small>':'')+'</li>';
    }).join('');
    const shown=(entry)=>shared?metricValue(entry,esc):undefined;
    const charts=views.length?moneyGroups(views,(view,currency)=>flowChart(chartData(view),{...filters,currency},grouping,chartPage,
      mode,value=>bankMoney(value,currency),esc),grouped):'<p class="of-chart-placeholder">Nenhuma movimentação elegível no período.</p>';
    const groupNet=shared?views.map(([currency,view])=>'<span class="of-money-line">'+wealthMoney(
      flowMode==='adjusted'?view.insights.known.net:view.flow.BANK.observed_net,currency,esc)+'</span>').join('')||'Indisponível':amount(net);
    const breakdown=shared?moneyGroups(views,(view,currency)=>bridgePanel(view.insights,value=>wealthMoney(value,currency,esc),esc),grouped):
      bridgePanel(insights,amount,esc);
    const rankings=views.length?moneyGroups(views,(view,currency)=>categoryRanking(view,mode,
      value=>wealthMoney(value,currency,esc),esc,showAdjusted),grouped):categoryRanking(secondary,mode,amount,esc,showAdjusted);
    const incomeCard=shared?'<section class="of-summary-card of-income-insight"><div class="of-section-heading"><div><h3>Rendimentos de investimentos</h3>'+
      '<p>Créditos identificados no período</p></div><button type="button" class="of-link" data-open-income>Ver rendimentos e proventos</button></div>'+
      unifiedIncomeMarkup(shared.income,esc)+moneyGroups(views.filter(([,view])=>Object.keys(view.insights.automatic.counts).length||view.insights.automatic.position!=null),
        (view,currency)=>automaticPanel(view.insights.automatic,value=>wealthMoney(value,currency,esc),esc),grouped)+'</section>':incomePanel(insights,amount,mode,esc);
    result.innerHTML=(filters.history==='1'?'<p class="of-notice">Histórico completo · O fluxo inclui conexões arquivadas. As posições abaixo têm como referência somente conexões ativas.</p>':'')+
      '<div class="of-six-kpis"><section><h3>Posição financeira atual</h3><div class="of-metrics of-kpi-group">'+
      metric('accounts','Saldo em contas',accounts.value,shared?metricNote(shared.accounts):positionNote(accounts),shown(shared?.accounts))+
      metric('investments','Investimentos',investments.value,shared?metricNote(shared.investments):currentWealth?wealthDetail:positionNote(investments),
        shared?shown(shared.investments):currentWealth?wealthMetric:undefined)+
      metric('cards','Cartões de crédito',cards?.consolidated??cards?.used,shared?
        cardKpi(cards).note:cards?.consolidated!=null?
        (cards.included_count+' de '+cards.count+' considerados'):(cards?.active_count||0)+' ativos informados',shown(shared?cardKpi(cards).metric:undefined))+
      '</div></section><section><h3>Resultados do período</h3><div class="of-metrics of-kpi-group">'+
      metric('incoming',flowMode==='adjusted'?'Receitas identificadas':'Entradas bancárias',showAdjusted?insights.known.incoming:flow.reported?.incoming,
        shared?metricNote(shared[flowMode==='gross'?'gross_incoming':'incoming']):showAdjusted?economicNote:coverageLabel(flow.coverage_state),
        shown(shared?.[flowMode==='gross'?'gross_incoming':'incoming']))+
      metric('outgoing',flowMode==='adjusted'?'Despesas identificadas':'Saídas bancárias',showAdjusted?insights.known.outgoing:flow.reported?.outgoing,
        shared?metricNote(shared[flowMode==='gross'?'gross_outgoing':'outgoing']):showAdjusted?economicNote:coverageLabel(flow.coverage_state),
        shown(shared?.[flowMode==='gross'?'gross_outgoing':'outgoing']))+
      metric('income','Rendimentos',insights?.income.value,'Créditos de investimento identificados',shown(shared?.income.credits))+'</div></section></div>'+
      (shared?.quality.mixed_dates?'<p class="of-notice">Os valores patrimoniais têm datas de referência diferentes.</p>':'')+
      '<section class="of-summary-card of-bank-flow"><div class="of-section-heading"><div><h3>'+flowTitle+'</h3>'+
      '<strong class="of-net-value">'+groupNet+'</strong>'+
      '<p>'+netNote+'</p></div><div class="actions of-insight-selects">'+(insights?'<label>Visão do fluxo<select data-financial-flow aria-label="Visão do fluxo"><option value="adjusted">Econômica</option><option value="gross">Bancária</option></select></label>':'')+
      '<label>Agrupar por<select data-grouping aria-label="Agrupar por"><option value="day">Dia</option><option value="week">Semana</option><option value="month">Mês</option></select></label></div></div>'+
      '<div data-flow-chart>'+charts+'</div>'+
      comparison+breakdown+
      (showAdjusted&&insights.card_activity?.purchases!=null?'<p><button type="button" class="of-link" data-card-expenses>Compras de cartão identificadas</button> '+amount(insights.card_activity.purchases)+' · '+countBR.format(insights.card_activity.installments)+' parcelas. Subtotal pelas datas lançadas no cartão.</p>':'')+
      (showAdjusted&&insights.card_activity?.credits!=null?'<p><button type="button" class="of-link" data-card-credits>Estornos identificados no cartão</button> '+amount(insights.card_activity.credits)+'</p>':'')+
      (showAdjusted&&insights.card_activity?.unresolved?'<p>'+countBR.format(insights.card_activity.unresolved)+' movimentos de cartão sem natureza econômica comprovada.</p>':'')+
      (insights?.unresolved_scope?'<p>Há registros fora do recorte por falta de data, moeda ou situação comprovada.</p>':'')+
      (insights?'<button type="button" class="of-link" data-classification-pending>Ver '+countBR.format(insights.pending)+' movimentações pendentes de classificação</button>':'')+
      '</section>'+
      (international&&!shared?overviewWealth(loaded.wealth,esc,state.wealthPresentation||'original'):'')+
      portfolioPanel(history,shared?value=>wealthMoney(value,shared.currency,esc):amount,mode,esc,(value,currency)=>wealthMoney(value,currency,esc))+
      '<div class="of-overview-grid"><section class="of-summary-card"><div class="of-section-heading"><div><h3>Composição da carteira</h3></div><button type="button" class="of-link" data-open-assets>Ver investimentos</button></div>'+(shared?unifiedAllocation(shared,mode,esc):allocation(investments,mode,amount,esc))+'</section>'+incomeCard+'</div>'+
      '<div class="of-overview-grid"><section class="of-summary-card"><h3>'+(showAdjusted?'Principais categorias de despesas':'Principais categorias de saída')+'</h3>'+rankings+'</section>'+(shared?cardUsage(cards,esc,mode,cardIdentity):cardPanel(cards,amount,mode,esc))+'</div>'+
      '<section class="of-summary-card" data-current-positions tabindex="-1"><h3>Posições por instituição</h3><p>Últimas posições conhecidas</p>'+(shared?institutionPositions(shared,esc):positionRows(loaded,catalog,amount,esc))+'</section>'+
      '<details class="of-summary-card of-quality"><summary>Qualidade dos dados</summary>'+
      (shared?portfolioQuality(shared,esc):'')+'<ul class="of-category-list">'+quality+'</ul><p>'+countBR.format((loaded.institutions||[]).filter(row=>row.current).length)+' conexões ativas no escopo · '+countBR.format(insights?.pending||0)+' movimentos em revisão.</p><p>Posições patrimoniais '+countBR.format(history?.points.length||0)+' no intervalo. Limites de cartão exigem comprovação de linhas distintas. A cobertura das despesas de cartões permanece em análise separada.</p><p>Última coleta registrada no escopo '+esc(dateBR(lastCollection))+'. Consulte as posições para ver a data financeira e a atualização informada pelo provedor.</p><p>Movimentos brutos incluem transferências e pagamentos. Posições e saldos podem se sobrepor.</p><div class="actions"><button type="button" class="of-link" data-open-connections>Conexões</button><button type="button" class="of-link" data-open-diagnostics>Diagnóstico</button></div></details>';
    result.querySelector('[data-grouping]').value=grouping;
    const kind=result.querySelector('[data-financial-flow]');
    if(kind)kind.value=flowMode;
  }

  function syncForm(){
    for(const key of fields)form.elements[key].value=state[key];
    people.value=state.history==='1'?'!history':[...people.options].some(option=>option.value===state.connection_id)?state.connection_id:'';
    if(consolidated)form.elements.presentation.value=state.presentation;
    form.elements.preset.value=state.periodMode||'month';
    form.elements.month.value=state.start.slice(0,7);
    form.elements.month.max=today.slice(0,7);
    form.elements.year.value=state.start.slice(0,4);
    form.elements.year.max=today.slice(0,4);
    syncPeriodControls();
  }
  function syncPeriodControls(){
    const mode=form.elements.preset.value;
    form.elements.month.hidden=mode!=='month';
    form.elements.year.hidden=mode!=='year';
    form.querySelector('.of-period-step').hidden=!['month','year'].includes(mode);
    form.querySelector('[data-period-now]').hidden=!['month','year'].includes(mode);
    form.querySelector('[data-period-step="1"]').disabled=mode==='year'?form.elements.year.value>=today.slice(0,4):form.elements.month.value>=today.slice(0,7);
  }
  function choosePeriod(step=0,reset=false){
    const mode=form.elements.preset.value;
    if(mode==='custom')return;
    let start,end;
    if(mode==='year'){
      const year=reset?Number(today.slice(0,4)):Number(form.elements.year.value)+step;
      if(year<1900||year>Number(today.slice(0,4)))return;
      form.elements.year.value=year;
      start=year+'-01-01';end=year+'-12-31';
    }else if(mode==='month'){
      const selection=reset?today.slice(0,7):form.elements.month.value;
      if(!/^\d{4}-\d{2}$/.test(selection))return;
      const cursor=asDate(selection+'-01');
      cursor.setUTCMonth(cursor.getUTCMonth()+step);
      start=iso(cursor);if(start>today||start<'1900-01-01')return;
      form.elements.month.value=start.slice(0,7);
      cursor.setUTCMonth(cursor.getUTCMonth()+1,0);
      end=iso(cursor);
    }else [start,end]=periodRange(mode,today);
    form.elements.start.value=start;form.elements.end.value=minDate(end,today);
    form.elements.end.setCustomValidity('');
    syncPeriodControls();form.requestSubmit();
  }
  async function load(){
    const query=queries.begin();
    filters={start:form.elements.start.value,end:minDate(form.elements.end.value,today),currency:form.elements.currency.value,
      history:people.value==='!history'?'1':'0',connection_id:people.value==='!history'?'':people.value};
    Object.assign(state,filters,{periodMode:form.elements.preset.value});
    if(consolidated)state.presentation=form.elements.presentation.value;
    onPeriod(filters);
    const days=(+asDate(filters.end)-+asDate(filters.start))/dayMs+1;
    grouping=days<=14?'day':days<=90?'week':'month';
    chartPage=0;
    loaded=null;
    result.innerHTML='<p role="status" class="of-chart-placeholder">Carregando resumo financeiro…</p>';
    result.setAttribute('aria-busy','true');
    const params=new URLSearchParams({...filters,product:'ALL',status:'POSTED',portfolio_window:state.portfolioWindow||'6'});
    if(state.portfolioConnection&&(consolidated||active.some(item=>item.id===state.portfolioConnection)))params.set('portfolio_connection',state.portfolioConnection);
    if(consolidated)params.set('presentation',state.presentation);
    if(!filters.connection_id)params.delete('connection_id');
    try{
      const bank=api('/open-finance/analytics?'+params,{queryScope:query});
      const wealthParams=new URLSearchParams({presentation:state.wealthPresentation||'original',page_size:'25'});
      if(filters.connection_id)wealthParams.set('connection_id',filters.connection_id);
      const wealth=international&&!consolidated?api('/open-finance/portfolio?'+wealthParams,{queryScope:query}).catch(()=>null):null;
      const [response,wealthData]=await Promise.all([bank,wealth]);
      if(!query.current()||!host.isConnected)return;
      loaded=international&&!consolidated?{...response,wealth:wealthData}:response;
      if(consolidated){
        for(const option of [...people.options])if(!nativeOptions.has(option.value))option.remove();
        for(const row of (response.presentation_view?.history.connections||[])){
          if(!nativeOptions.has(row.id))people.add(new Option(institutionName(row.label),row.id));
        }
        people.value=filters.history==='1'?'!history':filters.connection_id;
      }
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
  if(consolidated)form.elements.presentation.onchange=()=>{
    state.presentation=form.elements.presentation.value;
    savePresentation(state.presentation);
    form.requestSubmit();
  };
  form.onsubmit=event=>{
    event.preventDefault();
    if(form.elements.start.value>minDate(form.elements.end.value,today)){
      form.elements.end.setCustomValidity('A data final deve ser igual ou posterior à inicial.');
      form.elements.end.reportValidity();
      return;
    }
    load();
  };
  for(const key of ['start','end'])form.elements[key].oninput=()=>{
    form.elements.end.setCustomValidity('');
    form.elements.preset.value='custom';
    syncPeriodControls();filtersChanged();
  };
  form.elements.preset.onchange=()=>{
    syncPeriodControls();
    if(form.elements.preset.value==='custom'){form.elements.start.focus();return;}
    choosePeriod(0,true);
  };
  form.elements.month.onchange=()=>choosePeriod();
  form.elements.year.onchange=()=>choosePeriod();
  form.querySelector('[data-period-now]').onclick=()=>choosePeriod(0,true);
  form.querySelectorAll('[data-period-step]').forEach(button=>button.onclick=()=>choosePeriod(Number(button.dataset.periodStep)));
  host.addEventListener('finance-privacy-changed',paint);
  host.addEventListener('of-tab-selected',event=>{
    if(event.detail==='overview'){syncForm();load()}
    else queries.cancel();
  });
  result.onchange=event=>{
    if(event.target.matches('[data-portfolio-connection]')){state.portfolioConnection=event.target.value;load();return;}
    if(event.target.matches('[data-wealth-presentation]')){state.wealthPresentation=event.target.value;load();return;}
    if(event.target.matches('[data-portfolio-window]')){state.portfolioWindow=event.target.value;load();return;}
    if(event.target.matches('[data-financial-flow]')){
      flowMode=event.target.value;state.perspective=flowMode;chartPage=0;paint();result.querySelector('[data-financial-flow]').focus();return;
    }
    if(!event.target.matches('[data-grouping]'))return;
    grouping=event.target.value;chartPage=0;paint();
    result.querySelector('[data-grouping]').focus();
  };
  result.onclick=event=>{
    const button=event.target.closest('button');
    if(!button)return;
    if(button.matches('[data-retry-summary]')){load();return}
    if(button.matches('[data-copy-card-diagnostics]')){
      const box=button.closest('[data-card-diagnostics]');
      const field=box.querySelector('textarea'),status=box.querySelector('[data-card-copy-status]');
      const select=()=>{field.select();status.textContent='Texto selecionado. Use o comando de copiar do dispositivo.';};
      if(navigator.clipboard?.writeText){
        navigator.clipboard.writeText(field.value).then(()=>{status.textContent='Diagnóstico copiado.';},select);
      }else select();
      return;
    }
    const shared=loaded?.presentation_view;
    const presented=shared?.currency||state.wealthPresentation||'original';
    const context={...filters,account_id:'',product:'BANK',status:'POSTED',direction:'all',category:'',search:'',bill_id:''};
    if(button.dataset.metric==='accounts'){
      const target=result.querySelector('[data-current-positions]');target.focus();target.scrollIntoView({block:'start'});
    }else if(button.matches('[data-open-income],[data-metric="income"]')){
      onAssets({...context,income:true});
    }else if(button.matches('[data-overview-card],[data-all-overview-cards],[data-metric="cards"]')){
      const card=button.dataset.overviewCard===undefined?null:(shared?.cards||loaded.cards).items[Number(button.dataset.overviewCard)];
      onCards({connection_id:card?.connection_id||filters.connection_id,account_id:card?.account_id||'',currency:card?.currency||filters.currency});
    }else if(button.matches('[data-classification-pending]')){
      onNavigate({...context,bucket:'pending',openClassification:true});
    }else if(button.dataset.insightBucket){
      onNavigate({...context,bucket:button.dataset.insightBucket,direction:button.dataset.insightDirection});
    }else if((consolidated||international)&&button.matches('[data-open-unified-portfolio],[data-open-assets],[data-metric="investments"]')){
      onUnified({view:'portfolio',presentation:presented,
        connection_id:(button.closest('.of-portfolio')?shared?.history.connection_id:filters.connection_id)||'',account_id:''});
    }else if(button.closest('.of-portfolio')&&button.matches('[data-open-assets]')){
      onAssets({connection_id:loaded.portfolio_history?.connection_id||'',currency:filters.currency,type:''});
    }else if(button.matches('[data-investment-class],[data-open-assets],[data-metric="investments"]')){
      onAssets({connection_id:filters.connection_id,currency:filters.currency,type:button.dataset.investmentClass||''});
    }else if(button.dataset.institutionAssets){
      if(consolidated)onUnified({view:'portfolio',presentation:presented,connection_id:button.dataset.institutionAssets,account_id:''});
      else onAssets({connection_id:button.dataset.institutionAssets,currency:filters.currency,type:''});
    }else if(button.dataset.institutionConnection){
      onConnections(button.dataset.institutionConnection,true,button.hasAttribute('data-broker-connection'));
    }else if(button.matches('[data-card-expenses],[data-card-credits]')){
      onNavigate({...context,product:'CREDIT',direction:button.matches('[data-card-expenses]')?'outgoing':'incoming',
        card_economic:button.matches('[data-card-expenses]')?'recognized_purchase':'credit'});
    }else if(button.dataset.flowComponent){
      onNavigate({...context,direction:button.dataset.insightDirection,flow_component:button.dataset.flowComponent});
    }else if(button.dataset.autoCategory){
      const key=button.dataset.autoCategory;
      const nature={applied:'APPLICATION',redeemed:'REDEMPTION',credited:'INVESTMENT_INCOME',tax:'TAX',charge:'CHARGE',pending:'REDEMPTION'}[key];
      onNavigate({...context,investment:'Aplic Aut Mais',nature,review:'CONFIRMED',direction:['redeemed','credited','pending'].includes(key)?'incoming':'outgoing',
        ...(key==='pending'?{bucket:'pending'}:{})});
    }else if(button.dataset.provent){
      onNavigate({...context,direction:'incoming',bucket:'operating',nature:'INVESTMENT_INCOME',provent:button.dataset.provent});
    }else if(button.matches('[data-open-connections],[data-open-diagnostics]')){
      onConnections(filters.connection_id,button.matches('[data-open-diagnostics]'));
    }else if(button.dataset.metric){
      onNavigate({...context,direction:button.dataset.metric,...(flowMode==='gross'||!loaded.insights?{}:{bucket:bucketFor()})});
    }else if(button.dataset.overviewCategory){
      const economic=Boolean(loaded.insights&&flowMode==='adjusted');
      const source=shared?Object.values(shared.movements).flatMap(view=>economic?view.economic_category_ranking:view.category_ranking.BANK):
        (economic?loaded.economic_category_ranking:loaded.category_ranking.BANK);
      const row=source.find(item=>item.key===button.dataset.overviewCategory);
      if(row)onNavigate({...context,direction:'outgoing',effective_key:row.key,effectiveLabel:categoryLabel(row),...(economic?{bucket:'operating'}:{})});
    }else if(button.hasAttribute('data-broker-activity')){
      onUnified({view:'activities',presentation:presented,connection_id:button.dataset.overviewInstitution,account_id:''});
    }else if(button.dataset.overviewInstitution){
      onNavigate({...context,connection_id:button.dataset.overviewInstitution,history:'0'});
    }else if(button.dataset.bucketStart){
      onNavigate({...context,start:button.dataset.bucketStart,end:button.dataset.bucketEnd,
        currency:shared?.currency==='original'?button.dataset.bucketCurrency:filters.currency,
        direction:button.dataset.direction,...(flowMode==='gross'||!loaded.insights?{}:{bucket:bucketFor()})});
    }else if(button.dataset.chartPage){
      chartPage+=Number(button.dataset.chartPage);paint();
      const next=result.querySelector('[data-chart-page="'+button.dataset.chartPage+'"]:not(:disabled)')||result.querySelector('[data-chart-page]:not(:disabled)');
      next?.focus();
    }
  };
  syncForm();
  if(!panel.hidden)load();
}
