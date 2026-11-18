import {bankMoney,dateBR,privacyMode} from './privacy.js';
import {countBR,institutionName,statusLabel} from './open-finance-labels.js';
import {proventNames} from './open-finance-classification-ui.js';
import {createQueryGeneration} from './query-generation.js';

const bridgeNames={operating:'Receitas e despesas identificadas',capital:'Movimentações de capital',internal:'Movimentações internas',
  settlement:'Liquidações de obrigações',pending:'Em revisão ou com evidência insuficiente'};
const volumeNames={applied:'Total aplicado',redeemed:'Total resgatado',capital_flow:'Fluxo líquido das aplicações',
  credited:'Rendimentos creditados',tax:'Tributos identificados',charge:'Encargos identificados'};
const percent=new Intl.NumberFormat('pt-BR',{maximumFractionDigits:2});
const date=value=>value?dateBR(value):'Indisponível';

export function bridgePanel(insights,amount,esc){
  if(!insights)return '';
  const rows=Object.entries(bridgeNames).map(([key,label])=>{
    const item=insights.bridge[key];
    return '<li><span>'+esc(label)+'</span><div><button type="button" class="of-link" data-insight-bucket="'+key+'" data-insight-direction="incoming">Entradas '+amount(item?.incoming)+'</button>'+
      '<button type="button" class="of-link" data-insight-bucket="'+key+'" data-insight-direction="outgoing">Saídas '+amount(item?.outgoing)+'</button></div></li>';
  });
  return '<details class="of-class-options"><summary>Como o fluxo bruto se decompõe</summary><ul class="of-category-list of-insight-bridge">'+rows.join('')+'</ul>'+
    '<p>O resultado utiliza somente receitas e despesas bancárias identificadas. Pagamentos de fatura e resgates sem decomposição ficam separados.</p></details>';
}

export function cardPanel(cards,amount,mode,esc){
  if(!cards)return '';
  const showRatio=mode!=='full';
  const list=cards.items.map((card,index)=>{
    const available=card.available!=null?'<div><dt>Limite disponível informado</dt><dd>'+amount(card.available)+'</dd></div>':'';
    return '<li class="of-insight-card-row"><div><strong>'+esc(card.name)+'</strong><small>'+esc(institutionName(card.institution))+' · '+
      esc(card.brand||'Bandeira não informada')+' · '+esc(statusLabel(card.status))+
      (card.holder==='ADDITIONAL'?' · Adicional':card.holder==='MAIN'?' · Titular':'')+'</small></div><span>'+amount(card.balance)+'</span>'+
      '<details><summary>Limite e posição</summary><dl class="of-class-fields"><div><dt>Saldo informado</dt><dd>'+amount(card.balance)+'</dd></div>'+
      '<div><dt>Saldo utilizado identificado</dt><dd>'+amount(card.used)+'</dd></div><div><dt>Limite informado</dt><dd>'+amount(card.limit)+'</dd></div>'+
      available+(showRatio&&card.utilization!=null?'<div><dt>Utilização individual</dt><dd>'+esc(percent.format(Number(card.utilization)))+'%</dd></div>':'')+
      '<div><dt>Vencimento informado</dt><dd>'+esc(date(card.due))+'</dd></div><div><dt>Última observação</dt><dd>'+esc(date(card.observed_at))+'</dd></div></dl></details>'+
      '<button type="button" class="of-link" data-overview-card="'+index+'">Ver cartão</button></li>';
  }).join('');
  return '<section class="of-summary-card of-card-insight"><div class="of-section-heading"><h3>Cartões de crédito</h3>'+
    '<button type="button" class="of-link" data-all-overview-cards>Ver todos os cartões</button></div><p>'+
    esc(countBR.format(cards.active_count))+' com situação ativa informada'+
    (cards.active_count!==cards.count?' · '+esc(countBR.format(cards.count-cards.active_count))+' sem situação confirmada':'')+'</p>'+
    (cards.used!=null?'<p>Saldo utilizado identificado <strong>'+amount(cards.used)+'</strong></p>':'')+
    (cards.next_reported_due?'<p>Próximo vencimento informado '+esc(date(cards.next_reported_due))+'</p>':'')+
    (list?'<ul class="of-category-list">'+list+'</ul><p>Limite consolidado indisponível sem comprovação de linhas distintas. Compras e faturas têm valores próprios na aba Cartões.</p>':'<p>Nenhum cartão encontrado neste escopo.</p>')+'</section>';
}

function proportions(rows,mode,amount,esc){
  if(mode==='full')return '<p class="of-chart-placeholder">Valores e proporções ocultos em privacidade total.</p>';
  if(!rows.length)return '<p class="of-chart-placeholder">Nenhum rendimento identificado neste período.</p>';
  const max=rows.reduce((found,row)=>Math.max(found,Number(row.value)),0);
  return '<ul class="of-ranking">'+rows.map(row=>'<li><div><span>'+esc(row.label)+'</span><strong>'+amount(row.value)+'</strong></div>'+
    '<span class="of-ranking-track" aria-hidden="true"><i style="width:'+(max>0?100*Number(row.value)/max:0)+'%"></i></span></li>').join('')+'</ul>';
}

export function incomePanel(insights,amount,mode,esc){
  if(!insights)return '';
  const rows=Object.entries(insights.income.by_kind).map(([key,value])=>({label:proventNames[key]||key,value}));
  return '<section class="of-summary-card of-income-insight"><div class="of-section-heading"><div><h3>Rendimentos de investimentos</h3>'+
    '<p>Créditos bancários identificados no período</p></div><button type="button" class="of-link" data-open-income>Ver rendimentos e proventos</button></div>'+
    '<strong class="of-net-value">'+amount(insights.income.value)+'</strong>'+proportions(rows,mode,amount,esc)+
    '<p>A cobertura depende dos registros disponíveis e das classificações confirmadas.</p>'+'</section>';
}

export function mountInvestmentIncome({host,api,esc,navigation,getScope}){
  const panel=host.querySelector('#of-panel-assets');
  const section=document.createElement('section');
  section.className='panel of-investment-income';
  section.innerHTML='<details><summary>Rendimentos e proventos</summary><form class="of-overview-filters" aria-label="Período de rendimentos">'+
    '<label>De<input name="start" type="date" required></label><label>Até<input name="end" type="date" required></label>'+
    '<label>Moeda<input name="currency" maxlength="3" pattern="[A-Z]{3}" required></label>'+
    '<label>Ordenar por<select name="order"><option value="date">Data</option><option value="asset">Código</option><option value="count">Ocorrências</option><option value="value">Valor acumulado</option></select></label>'+
    '<button type="submit">Consultar rendimentos</button></form><div data-income-result aria-live="polite"></div></details>';
  panel.append(section);
  const details=section.querySelector('details'),form=section.querySelector('form'),result=section.querySelector('[data-income-result]');
  const queries=createQueryGeneration(navigation);
  let snapshot=null,scope={};
  function paint(){
    const mode=privacyMode(),order=form.elements.order;
    const amount=value=>{
      if(value==null)return 'Indisponível';
      if(mode!=='visible')return '<span aria-label="Valor oculto">••••••</span>';
      return esc(bankMoney(value,scope.currency));
    };
    order.querySelector('[value=value]').disabled=mode==='full';
    if(mode==='full'&&order.value==='value')order.value='date';
    if(!snapshot)return;
    const {income,automatic}=snapshot;
    const assets=[...income.assets];
    assets.sort({
      date:(a,b)=>b.last_date.localeCompare(a.last_date),
      asset:(a,b)=>(a.asset||'').localeCompare(b.asset||''),
      count:(a,b)=>b.count-a.count,
      value:(a,b)=>Number(b.value)-Number(a.value),
    }[order.value]);
    const monthly=income.months.map(row=>({label:dateBR(row.month+'-01').slice(3),value:row.value}));
    const assetsHtml=assets.map(group=>'<li><div><strong>'+esc(group.asset||'Ativo não identificado')+'</strong><small>'+
      esc(group.resolution==='SUGGESTED'?'Código sugerido pela descrição':group.resolution==='USER_IDENTIFIED'?'Código informado pelo proprietário':'')+
      ' · '+esc(proventNames[group.provent]||'')+' · '+esc(institutionName(group.institution))+' · '+esc(date(group.last_date))+
      ' · '+esc(countBR.format(group.count))+' créditos</small></div><strong>'+amount(group.value)+'</strong></li>').join('');
    const events=income.events.map(row=>'<li><span>'+esc(date(row.date))+' · '+esc(row.asset||'Ativo não identificado')+' · '+esc(proventNames[row.provent]||'')+
      ' · '+esc(institutionName(row.institution))+'</span><strong>'+amount(row.value)+'</strong></li>').join('');
    const autTotals=Object.entries(volumeNames).map(([key,label])=>'<li><span>'+label+'</span><strong>'+amount(automatic.value[key])+'</strong>'+(
      automatic.counts[key]?' <small>'+esc(countBR.format(automatic.counts[key]))+' registros</small>':'')+'</li>').join('');
    const autMonths=automatic.months.map(month=>'<li><strong>'+esc(dateBR(month.month+'-01').slice(3))+'</strong><small>'+
      Object.entries(volumeNames).filter(([key])=>month[key]!=null).map(([key,label])=>label+' '+amount(month[key])).join(' · ')+'</small></li>').join('');
    result.innerHTML='<p>Créditos identificados <strong>'+amount(income.value)+'</strong> · '+esc(countBR.format(income.event_count))+' registros</p>'+
      '<h4>Histórico mensal de rendimentos</h4>'+proportions(monthly,mode,amount,esc)+
      '<details><summary>Valores mensais em texto</summary><ul class="of-category-list">'+monthly.map(row=>'<li><span>'+esc(row.label)+'</span><strong>'+amount(row.value)+'</strong></li>').join('')+'</ul></details>'+
      '<h4>Por ativo</h4>'+(assetsHtml?'<ul class="of-category-list">'+assetsHtml+'</ul>':'<p>Nenhum provento identificado neste período.</p>')+
      '<details><summary>Créditos registrados</summary><p>Até 300 registros recentes desta consulta.</p><ul class="of-category-list">'+events+'</ul></details>'+
      '<details><summary>Aplic Aut Mais</summary><ul class="of-category-list">'+autTotals+'</ul>'+
      '<h4>Histórico mensal da aplicação automática</h4><ul class="of-category-list">'+autMonths+'</ul>'+
      '<p>A rentabilidade e a composição dos resgates dependem de dados adicionais.</p></details>';
  }
  async function load(){
    const query=queries.begin();
    const filters={start:form.elements.start.value,end:form.elements.end.value,currency:form.elements.currency.value,product:'BANK',status:'POSTED'};
    if(scope.connection_id)filters.connection_id=scope.connection_id;
    if(scope.history==='1')filters.history='1';
    scope={...scope,...filters};
    snapshot=null;
    result.setAttribute('aria-busy','true');
    result.innerHTML='<p role="status">Consultando rendimentos…</p>';
    try{
      const data=await api('/open-finance/analytics?'+new URLSearchParams(filters),{queryScope:query});
      if(!query.current()||!host.isConnected)return;
      snapshot=data.insights;
      if(snapshot)paint();
      else result.innerHTML='<p>Consulta de rendimentos indisponível.</p>';
    }catch(_){if(query.current())result.innerHTML='<p role="alert">Não foi possível consultar os rendimentos.</p>';}
    finally{if(query.current())result.removeAttribute('aria-busy');}
  }
  function initialize(){
    scope={...getScope()};
    for(const key of ['start','end','currency'])form.elements[key].value=scope[key]||'';
  }
  function queryCurrentPeriod(){
    initialize();
    if(form.checkValidity())load();
  }
  details.querySelector('summary').addEventListener('click',()=>{
    if(details.open)queries.cancel();
    else queryCurrentPeriod();
  });
  form.onsubmit=event=>{event.preventDefault();load();};
  form.elements.order.onchange=paint;
  host.addEventListener('finance-privacy-changed',paint);
  host.addEventListener('of-tab-selected',event=>{
    if(event.detail!=='assets'){queries.cancel();details.open=false;}
  });
  return {open:()=>{details.open=true;queryCurrentPeriod();details.querySelector('summary').focus();section.scrollIntoView({block:'start'});}};
}
