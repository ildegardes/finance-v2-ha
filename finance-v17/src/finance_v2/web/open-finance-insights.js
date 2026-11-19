import {unifiedIncomeMarkup} from './open-finance-consolidated.js';
import {cardIdentity} from './open-finance-identity.js';
import {bankMoney,dateBR,privacyMode} from './privacy.js';
import {countBR,institutionName,statusLabel} from './open-finance-labels.js';
import {proventNames} from './open-finance-classification-ui.js';
import {createQueryGeneration} from './query-generation.js';

const bridgeNames={operating:'Receitas e despesas identificadas',internal:'Transferências entre contas próprias',
  application:'Aplicações financeiras',redemption:'Resgates financeiros',card_payment:'Liquidações de cartão',
  other:'Outras movimentações não econômicas',pending:'Em revisão ou com evidência insuficiente'};
const volumeNames={applied:'Total aplicado',redeemed:'Total resgatado',capital_flow:'Fluxo líquido das aplicações',
  credited:'Rendimentos creditados',tax:'Tributos identificados',charge:'Encargos identificados'};
const percent=new Intl.NumberFormat('pt-BR',{maximumFractionDigits:2});
const date=value=>value?dateBR(value):'Indisponível';

export function bridgePanel(insights,amount,esc){
  if(!insights)return '';
  if(insights.breakdown){
    const rows=Object.entries(bridgeNames).map(([key,label])=>{
      const records=insights.breakdown.filter(row=>row.component===key);
      return records.map(row=>'<li><span>'+esc(key==='operating'?(row.direction==='incoming'?'Receitas identificadas':'Despesas identificadas'):label)+'</span>'+
        '<button type="button" class="of-link" data-flow-component="'+key+'" data-insight-direction="'+esc(row.direction)+'">'+
        (row.direction==='incoming'?'Entradas':row.direction==='outgoing'?'Saídas':'Direção não informada')+' · '+countBR.format(row.count)+' · '+amount(row.value)+'</button></li>').join('');
    }).join('');
    return '<details class="of-class-options"><summary>Como o fluxo bruto se decompõe</summary>'+
      (rows?'<ul class="of-category-list">'+rows+'</ul>':'<p>Nenhuma movimentação bancária no período.</p>')+'</details>';
  }
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
  const reasons={OBLIGATION_UNVERIFIED:'Obrigação independente não comprovada',OBLIGATION_OVERLAP:'Possível obrigação repetida',
    AMOUNT_UNAVAILABLE:'Saldo ausente',DIFFERENT_BASIS:'Tipo de saldo diferente',REFERENCE_DATE_MISMATCH:'Data não comparável'};
  const list=cards.items.map((card,index)=>{
    const identity=cardIdentity(card,esc);
    const suffix=identity.tail&&mode!=='full'?' · •••• '+esc(identity.tail):'';
    return '<li><button type="button" class="of-card-compact" data-overview-card="'+index+'">'+identity.mark+
      '<span><strong>'+esc(identity.label)+'</strong><small>'+esc(institutionName(card.institution))+
      (identity.network?' · <span class="of-card-network">'+esc(identity.network)+'</span>':'')+suffix+'</small>'+
      (card.consolidation_reason?'<small>'+esc(reasons[card.consolidation_reason]||'Fora do subtotal')+'</small>':'')+'</span><span><strong>'+amount(card.used??card.balance)+'</strong><small>'+
      (card.used!=null?'Utilizado':'Saldo informado')+'</small></span></button></li>';
  }).join('');
  return '<section class="of-summary-card of-card-insight"><div class="of-section-heading"><div><h3>Cartões de crédito</h3><p>'+
    esc(countBR.format(cards.active_count))+(cards.active_count===1?' cartão ativo informado':' cartões ativos informados')+'</p></div><button type="button" class="of-link" data-all-overview-cards>Ver todos</button></div>'+
    (cards.consolidated!=null?'<p>'+(cards.basis==='ACCOUNT_BALANCE'?'Saldo informado':'Saldo utilizado')+
      ' <strong>'+amount(cards.consolidated)+'</strong> · '+countBR.format(cards.included_count)+' de '+countBR.format(cards.count)+' considerados</p>':
      cards.count?'<p>Consolidação não comprovada</p>':'')+
    (list?'<ul class="of-compact-cards">'+list+'</ul>':'<p>Nenhum cartão encontrado neste escopo.</p>')+'</section>';
}

function proportions(rows,mode,amount,esc){
  if(mode==='full')return '<p class="of-chart-placeholder">Valores e proporções ocultos em privacidade total.</p>';
  if(!rows.length)return '<p class="of-chart-placeholder">Nenhum rendimento identificado neste período.</p>';
  const max=rows.reduce((found,row)=>Math.max(found,Number(row.value)),0);
  return '<ul class="of-ranking">'+rows.map(row=>'<li><div>'+(row.key?'<button type="button" class="of-link" data-provent="'+esc(row.key)+'">'+esc(row.label)+'</button>':'<span>'+esc(row.label)+'</span>')+'<strong>'+amount(row.value)+'</strong></div>'+
    '<span class="of-ranking-track" aria-hidden="true"><i style="width:'+(max>0?100*Number(row.value)/max:0)+'%"></i></span></li>').join('')+'</ul>';
}

export function automaticPanel(automatic,amount,esc){
  return automatic&&(Object.keys(automatic.counts).length||automatic.position!=null)?'<details class="of-automatic-card"><summary>Aplic Aut Mais</summary><ul class="of-category-list">'+
    Object.entries(volumeNames).map(([key,label])=>'<li>'+
      (key==='capital_flow'?'<span>'+label+'</span>':'<button type="button" class="of-link" data-auto-category="'+key+'">'+label+'</button>')+
      '<strong>'+amount(automatic.value[key])+'</strong>'+
      (automatic.counts[key]?'<small>'+esc(countBR.format(automatic.counts[key]))+' movimentos</small>':'')+'</li>').join('')+
      '<li><button type="button" class="of-link" data-auto-category="pending">Resgates pendentes</button><strong>'+amount(automatic.pending?.incoming)+'</strong></li>'+
      '<li><span>Posição informada do produto</span><strong>'+amount(automatic.position)+'</strong></li></ul></details>':'';
}

export function incomePanel(insights,amount,mode,esc){
  if(!insights)return '';
  const auto=automaticPanel(insights.automatic,amount,esc);
  const monthlyNote=insights.income.comparison==null?'':'<p>Diferença de rendimentos frente ao período anterior '+amount(insights.income.comparison)+'.</p>';
  const rows=Object.entries(insights.income.by_kind).map(([key,value])=>({key,label:proventNames[key]||key,value}));
  return '<section class="of-summary-card of-income-insight"><div class="of-section-heading"><div><h3>Rendimentos de investimentos</h3>'+
    '<p>Créditos bancários identificados no período</p></div><button type="button" class="of-link" data-open-income>Ver rendimentos e proventos</button></div>'+
    '<strong class="of-net-value">'+amount(insights.income.value)+'</strong>'+proportions(rows,mode,amount,esc)+
    monthlyNote+'<p>A cobertura depende dos registros disponíveis e das classificações confirmadas.</p>'+auto+'</section>';
}

export function mountInvestmentIncome({host,api,esc,navigation,getScope,consolidated=false}){
  const panel=host.querySelector('#of-panel-assets');
  const section=document.createElement('section');
  section.className='panel of-investment-income';
  section.innerHTML='<details><summary>Rendimentos e proventos</summary><form class="of-overview-filters" aria-label="Período de rendimentos">'+
    '<label>De<input name="start" type="date" required></label><label>Até<input name="end" type="date" required></label>'+
    (consolidated?'<input name="currency" type="hidden">':
      '<label>Moeda<input name="currency" maxlength="3" pattern="[A-Z]{3}" required></label>'+
      '<label>Ordenar por<select name="order"><option value="date">Data</option><option value="asset">Código</option><option value="count">Ocorrências</option><option value="value">Valor acumulado</option></select></label>')+
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
    if(consolidated){
      if(snapshot)result.innerHTML=unifiedIncomeMarkup(snapshot.income,esc,{details:true})+
        Object.entries(snapshot.movements).map(([currency,view])=>automaticPanel(view.insights.automatic,
          value=>value==null?'Indisponível':mode==='visible'?esc(bankMoney(value,currency)):'<span aria-label="Valor oculto">••••••</span>',esc)).join('');
      return;
    }
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
      '<p>Posição do produto '+amount(automatic.position)+' · Resgates pendentes '+amount(automatic.pending?.incoming)+'</p><h4>Histórico mensal da aplicação automática</h4><ul class="of-category-list">'+autMonths+'</ul>'+
      '<p>A rentabilidade e a composição dos resgates dependem de dados adicionais.</p></details>';
  }
  async function load(){
    const query=queries.begin();
    const filters={start:form.elements.start.value,end:form.elements.end.value,currency:form.elements.currency.value,product:'BANK',status:'POSTED'};
    if(consolidated)filters.presentation=scope.presentation||'BRL';
    if(scope.connection_id)filters.connection_id=scope.connection_id;
    if(scope.history==='1')filters.history='1';
    scope={...scope,...filters};
    snapshot=null;
    result.setAttribute('aria-busy','true');
    result.innerHTML='<p role="status">Consultando rendimentos…</p>';
    try{
      const data=await api('/open-finance/analytics?'+new URLSearchParams(filters),{queryScope:query});
      if(!query.current()||!host.isConnected)return;
      snapshot=consolidated?data.presentation_view:data.insights;
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
  if(form.elements.order)form.elements.order.onchange=paint;
  host.addEventListener('finance-privacy-changed',paint);
  host.addEventListener('of-tab-selected',event=>{
    if(event.detail!=='assets'){queries.cancel();details.open=false;}
  });
  return {open:()=>{details.open=true;queryCurrentPeriod();details.querySelector('summary').focus();section.scrollIntoView({block:'start'});}};
}
