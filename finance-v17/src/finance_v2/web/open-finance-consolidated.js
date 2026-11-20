import {bankMark} from './open-finance-identity.js';
import {dateBR} from './privacy.js';
import {countBR,institutionName} from './open-finance-labels.js';
import {proventNames} from './open-finance-classification-ui.js';
import {wealthMoney,wealthRate} from './open-finance-wealth.js';

const storageKey='finance-v17.open-finance.presentation';
const currencies=[['BRL','BRL — Real brasileiro'],['USD','USD — Dólar americano'],['original','Moedas originais']];
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
    const metric=(label,item)=>{
      const alternate=view.currency!=='original'&&Object.keys(item.original).some(key=>key!==view.currency);
      const reasons=item.missing_reasons||{};
      const conversionNote=reasons.REFERENCE_UNAVAILABLE?'Referência financeira ausente':
        reasons.RATE_UNAVAILABLE?'Cotação PTAX indisponível':reasons.CURRENCY_UNSUPPORTED?'Moeda sem conversão':'Conversão indisponível';
      const converted=Object.keys(item.amounts).length?
        '<span>'+(Object.keys(item.conversion_excluded||{}).length?'Subtotal em ':'Equivalente em ')+view.currency+
        '</span>'+metricValue(item,esc):conversionNote;
      return '<div class="of-position-value"><span>'+label+'</span><strong class="of-native-value">'+metricValue(item,esc,'original')+'</strong>'+
        (alternate?'<small class="of-converted-value">'+converted+'</small>':'')+
        '<small>'+esc(metricNote({...item,included:Object.keys(item.original).length,missing:0}))+'</small></div>';
    };
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
    wealthRate(quote.rate,esc)+' por USD</span>'+(quote.lag_days?'<small>Até '+quote.lag_days+' dias de defasagem</small>':'')+'</li>').join('');
  const notes=[
    data.mixed_dates?'Referências de '+dateBR(data.first)+' a '+dateBR(data.last)+'. Os valores representam datas diferentes.':'',
    data.overlap?'Possível sobreposição patrimonial. Consulte cada instituição ou revise as exclusões em Conexões.':'',
    view.investments.missing_reasons?.VALUE_UNAVAILABLE?'Há posições sem valor financeiro informado.':'',
    view.investments.missing_reasons?.RATE_UNAVAILABLE?'Há posições sem cotação PTAX elegível.':'',
    view.investments.undated?'Há posições sem data financeira comprovada.':'',
    view.investments.stale?'Há referências patrimoniais com mais de sete dias.':'',
  ].filter(Boolean);
  const excluded=view.investments.conversion_excluded||{};
  return notes.map(note=>'<p>'+esc(note)+'</p>').join('')+
    (Object.keys(excluded).length?'<p>Valores originais fora da conversão '+metricValue(view.investments,esc,'conversion_excluded')+'</p>':'')+
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

export function cardDiagnostics(cards,esc){
  if(!cards?.diagnostics?.length)return '';
  const lines=['FINANCE_V17_CARD_DIAGNOSTICS/1',...cards.diagnostics.map(row=>
    row.usage+' | '+(row.limit||'—')+' | '+row.count)];
  const consentMismatch=cards.diagnostics.some(row=>row.usage==='CONSENT_ITEM_MISMATCH');
  return '<details class="of-card-diagnostics" data-card-diagnostics><summary>Diagnóstico de cartões</summary>'+
    (consentMismatch?'<p>Consentimento associado a outro Item</p>':'')+
    '<label>Código de saldo, código de limite e quantidade<textarea readonly rows="4">'+esc(lines.join('\n'))+
    '</textarea></label><button type="button" class="quiet" data-copy-card-diagnostics>Copiar diagnóstico</button>'+
    '<p role="status" data-card-copy-status></p></details>';
}

const cardPercent=new Intl.NumberFormat('pt-BR',{style:'percent',maximumFractionDigits:2});

export function cardKpi(cards){
  const open=cards.open_balance.applicable||!cards.items.length;
  const last=!cards.metric.included&&cards.preserved?.metric.included;
  const metric=open?cards.open_balance:last?cards.preserved.metric:cards.metric;
  const label=open?'Saldo em aberto dos cartões':'Crédito utilizado nos cartões';
  const dates=metric.dates;
  const context=[(open?metric.preserved:last)?'Inclui posições preservadas':'',metric.partial?'Cobertura parcial':''];
  if(dates.length)context.push(dates.length===1?dateBR(dates[0]):dateBR(dates[0])+' a '+dateBR(dates.at(-1)));
  return {metric,label,open,note:context.filter(Boolean).join(' · ')||'Sem referência informada'};
}

export function cardUsage(cards,esc,mode,identity){
  if(!cards)return '';
  const primary=cardKpi(cards);
  const list=cards.items.map((card,index)=>{
    const visual=identity(card,esc);
    return '<li><button type="button" class="of-card-compact" data-overview-card="'+index+'">'+visual.mark+
      '<span><strong>'+esc(visual.label)+'</strong><small>'+esc(institutionName(card.institution))+
      (visual.network?' · <span class="of-card-network">'+esc(visual.network)+'</span>':'')+
      (visual.tail&&mode!=='full'?' · •••• '+esc(visual.tail):'')+'</small>'+
      (card.reference_date||card.position_state==='PRESERVED'?'<small>'+
        (card.position_state==='PRESERVED'?'Última posição conhecida · ':'Referência · ')+
        esc(card.reference_date?dateBR(card.reference_date):'coleta de '+dateBR(card.observed_at))+'</small>':'')+
      '</span><span><strong data-card-open-balance>'+wealthMoney(primary.open?card.reported_balance:card.used??card.preserved_used,card.currency,esc)+'</strong>'+
      '<small>'+(primary.open?'Saldo em aberto':'Crédito utilizado')+'</small></span></button></li>';
  }).join('');
  const totals=(position,label)=>{
    const ratios=Object.entries(position.utilization_by_currency);
    const utilization=mode==='visible'?ratios.map(([currency,value])=>{
      const percent=Number(value);
      return '<div class="of-card-utilization"><label>Utilização em '+esc(currency)+' '+esc(cardPercent.format(percent))+
        '<progress max="100" value="'+Math.min(100,Math.max(0,100*percent))+'"></progress></label></div>';
    }).join(''):'';
    return '<p>'+label+(position.metric.partial?' · cobertura parcial':'')+'</p><strong class="of-card-used-total">'+
      metricValue(position.metric,esc)+'</strong>'+
      (ratios.length?'<p>Limite consolidado <strong>'+metricValue(position.limit_metric,esc)+'</strong></p>':'')+utilization;
  };
  const preserved=cards.preserved;
  return '<section class="of-summary-card of-card-insight"><div class="of-section-heading"><div><h3>Cartões de crédito</h3><p>'+
    countBR.format(cards.active_count)+' cartões ativos informados</p></div><button type="button" class="of-link" data-all-overview-cards>Ver todos</button></div>'+
    '<p>'+primary.label+'</p><strong class="of-card-open-total">'+metricValue(primary.metric,esc)+'</strong>'+
    '<small>'+esc(primary.note)+'</small>'+
    (list?'<ul class="of-compact-cards">'+list+'</ul>':'<p>Nenhum cartão encontrado neste escopo.</p>')+
    (cards.metric.included||preserved?.metric.included?'<details><summary>Crédito utilizado e limites</summary>'+
      (cards.metric.included?totals(cards,'Crédito utilizado na posição atual'):'')+
      (preserved?.metric.included?totals(preserved,'Crédito utilizado na última posição conhecida'):'')+'</details>':'')+
    cardDiagnostics(cards,esc)+'</section>';
}
