import {bankMark} from './open-finance-identity.js';
import {dateBR} from './privacy.js';
import {countBR,institutionName} from './open-finance-labels.js';
import {proventNames} from './open-finance-classification-ui.js';
import {wealthMoney} from './open-finance-wealth.js';

const storageKey='finance-v17.open-finance.presentation';
const currencies=[['BRL','BRL — Real brasileiro'],['USD','USD — Dólar americano'],['original','Moedas originais']];
export const classes={FIXED_INCOME:'Renda fixa',BRAZIL_STOCK:'Ações brasileiras',FII:'FIIs',STOCK:'Stocks',
  REIT:'REITs',ETF:'ETFs',FUND:'Fundos de investimento',OTHER:'Outros instrumentos',UNKNOWN:'Não classificado'};
const incomes={...proventNames,stock_dividend:'Dividendos de Stocks',reit_distribution:'Distribuições de REITs',
  etf_distribution:'Distribuições de ETFs',foreign_dividend:'Dividendos internacionais',foreign_interest:'Juros internacionais',
  foreign_tax:'Tributos no exterior',foreign_withholding:'Impostos retidos no exterior'};

export function presentationPreference(){
  try{
    const value=localStorage.getItem(storageKey);
    return currencies.some(([key])=>key===value)?value:'BRL';
  }catch(_){return 'BRL';}
}
export function savePresentation(currency){
  try{localStorage.setItem(storageKey,currency);}catch(_){}
}
export function presentationControl(currency){
  return '<label>Moeda de apresentação<select name="presentation">'+currencies.map(([key,label])=>
    '<option value="'+key+'" '+(currency===key?'selected':'')+'>'+label+'</option>').join('')+'</select></label>';
}
export function metricValue(metric,esc,key='amounts'){
  const list=Object.entries(metric?.[key]||{});
  return list.length?list.map(([currency,value])=>'<span class="of-money-line">'+wealthMoney(value,currency,esc)+'</span>').join(''):
    'Indisponível';
}
export function metricNote(metric){
  if(metric?.overlap)return 'Possível sobreposição';
  if(!metric?.included)return metric?.missing?'Conversão ou valor indisponível':'Sem valores comprovados';
  if(metric.mixed_dates)return 'Subtotal · datas diferentes';
  if(metric.stale)return 'Subtotal · referência desatualizada';
  if(metric.partial)return 'Subtotal identificado · cobertura parcial';
  return metric.dates.length===1?'Referência '+dateBR(metric.dates[0]):'Cobertura informada';
}

export function institutionPositions(view,esc){
  if(!view.institutions.length)return '<p class="of-chart-placeholder">Nenhuma conexão ativa neste escopo.</p>';
  return '<div class="of-position-list of-consolidated-positions">'+view.institutions.map(row=>{
    const broker=row.provider==='SNAPTRADE';
    const metric=(label,item)=>'<div class="of-position-value"><span>'+label+'</span><strong>'+metricValue(item,esc)+
      '</strong><small>'+esc(metricNote(item))+'</small>'+(view.currency!=='original'&&Object.keys(item.original).some(key=>key!==view.currency)?
      '<small>Original '+metricValue(item,esc,'original')+'</small>':'')+'</div>';
    const detail=row.details.map(item=>'<li><strong>'+esc(item.label||'Nome não informado')+'</strong><span>'+
      wealthMoney(item.amount,item.currency,esc)+'</span><small>'+esc(item.account?item.account+' · ':'')+
      'Referência '+esc(item.reference?dateBR(item.reference):'Indisponível')+' · Coleta '+esc(dateBR(item.observed_at))+'</small></li>').join('');
    return '<article class="of-position" data-position-connection="'+esc(row.connection_id)+'"><div class="of-position-identity">'+
      bankMark(row.institution,esc)+'<div><h4>'+esc(institutionName(row.institution))+'</h4><span>'+ (row.connection_state==='PAUSED'?'Coleta pausada':'Conexão ativa')+' · '+
      esc(broker?'SnapTrade':'Pluggy')+'</span></div></div>'+
      metric(broker?'Caixa em corretora':'Saldo em contas',row.liquid)+metric('Investimentos',row.investments)+
      '<div class="of-position-actions"><button type="button" class="of-link" data-overview-institution="'+esc(row.connection_id)+'" '+
      (broker?'data-broker-activity':'')+'>Movimentações</button>'+
      '<button type="button" class="of-link" data-institution-assets="'+esc(row.connection_id)+'">Investimentos</button>'+
      '<button type="button" class="of-link" data-institution-connection="'+esc(row.connection_id)+'" '+(broker?'data-broker-connection':'')+'>Conexão</button>'+
      (detail?'<details><summary>Ver posições e datas</summary><ul class="of-category-list">'+detail+'</ul></details>':'')+
      '</div></article>';
  }).join('')+'</div>';
}

export function portfolioQuality(view,esc){
  const data=view.quality;
  const rates=data.rates.map(quote=>'<li><strong>PTAX de venda</strong><span>'+esc(dateBR(quote.date))+' · '+
    wealthMoney(quote.rate,'BRL',esc)+' por USD</span>'+(quote.lag_days?'<small>Até '+quote.lag_days+' dias de defasagem</small>':'')+'</li>').join('');
  const notes=[
    data.mixed_dates?'Referências de '+dateBR(data.first)+' a '+dateBR(data.last)+'. Os valores representam datas diferentes.':'',
    data.overlap?'Possível sobreposição patrimonial. Consulte cada instituição ou revise as exclusões em Conexões.':'',
    view.investments.missing?'Posições sem valor ou cotação elegível ficaram fora do subtotal convertido.':'',
    view.investments.undated?'Há posições sem data financeira comprovada.':'',
    view.investments.stale?'Há referências patrimoniais com mais de sete dias.':'',
  ].filter(Boolean);
  return notes.map(note=>'<p>'+esc(note)+'</p>').join('')+
    (rates?'<ul class="of-category-list">'+rates+'</ul>':'');
}

export function unifiedIncomeMarkup(income,esc,{details=false}={}){
  const hasCredits=Object.keys(income.credits.amounts).length;
  const lines=income.by_kind.map(row=>'<li><strong>'+esc(incomes[row.kind]||row.kind)+'</strong><span>'+
    wealthMoney(row.value,row.currency,esc)+'</span></li>').join('');
  const notes=(income.credits.partial?'<p>Subtotal dos créditos com valor e câmbio disponíveis. Possíveis sobreposições ficam fora da soma.</p>':'')+
    (income.tax.total?'<p>Tributos e retenções no exterior <strong>'+metricValue(income.tax,esc)+'</strong></p>':'')+
    (income.event_count?'<p>Rendimento líquido indisponível sem vínculo entre créditos e retenções.</p>':'');
  const events=details?'<details><summary>Créditos e tributos registrados</summary><p>Até 300 registros recentes.</p><ul class="of-category-list">'+
    income.events.map(row=>'<li><strong>'+esc(incomes[row.kind]||row.kind)+'</strong><span>'+
      wealthMoney(row.amount,row.currency,esc)+(row.presented!=null&&row.presentation_currency!==row.currency?
        ' · '+wealthMoney(row.presented,row.presentation_currency,esc):'')+'</span><small>'+
      esc([dateBR(row.date),row.institution,row.provider,row.asset,row.overlap?'Possível sobreposição':''].filter(Boolean).join(' · '))+
      '</small></li>').join('')+'</ul></details>':'';
  const months=details&&income.months.length?'<details><summary>Histórico mensal de rendimentos</summary><ul class="of-category-list">'+
    income.months.map(row=>'<li><span>'+esc(dateBR(row.month+'-01').slice(3))+'</span><strong>'+
      wealthMoney(row.value,row.currency,esc)+'</strong></li>').join('')+'</ul></details>':'';
  return '<strong class="of-net-value">'+metricValue(income.credits,esc)+'</strong>'+
    (lines?'<ul class="of-category-list">'+lines+'</ul>':hasCredits?'':'<p>Nenhum rendimento elegível no período.</p>')+notes+months+events;
}

export function cardBills(cards,esc,mode,identity){
  if(!cards)return '';
  const reasons={CURRENT_BILL_UNVERIFIED:'Fatura atual sem confirmação',AMOUNT_UNAVAILABLE:'Valor ou moeda da fatura indisponível',
    OBLIGATION_OVERLAP:'Possível fatura repetida'};
  const list=cards.items.map((card,index)=>{
    const visual=identity(card,esc);
    return '<li><button type="button" class="of-card-compact" data-overview-card="'+index+'">'+visual.mark+
      '<span><strong>'+esc(visual.label)+'</strong><small>'+esc(institutionName(card.institution))+
      (visual.network?' · <span class="of-card-network">'+esc(visual.network)+'</span>':'')+
      (visual.tail&&mode!=='full'?' · •••• '+esc(visual.tail):'')+'</small>'+
      (card.bill_due?'<small>Vencimento '+esc(dateBR(card.bill_due))+'</small>':'')+
      (card.consolidation_reason?'<small>'+esc(reasons[card.consolidation_reason]||'Fora do subtotal')+'</small>':'')+
      '</span><span><strong>'+wealthMoney(card.bill_value,card.bill_currency,esc)+'</strong><small>Fatura informada</small></span></button></li>';
  }).join('');
  return '<section class="of-summary-card of-card-insight"><div class="of-section-heading"><div><h3>Cartões de crédito</h3><p>'+
    countBR.format(cards.active_count)+' cartões ativos informados</p></div><button type="button" class="of-link" data-all-overview-cards>Ver todos</button></div>'+
    '<p>'+(cards.metric.partial?'Subtotal de faturas atuais':'Faturas atuais identificadas')+' <strong>'+metricValue(cards.metric,esc)+
    '</strong> · '+cards.included_count+' de '+cards.count+' considerados</p>'+
    (list?'<ul class="of-compact-cards">'+list+'</ul>':'<p>Nenhum cartão encontrado neste escopo.</p>')+'</section>';
}
