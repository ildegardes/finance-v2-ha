import {privacyMode,bankMoney,exchangeRate,dateBR} from './privacy.js';
import {createQueryGeneration} from './query-generation.js';
import {bankMark} from './open-finance-identity.js';
import {countBR,classLabel,investmentClassLabel} from './open-finance-labels.js';

const countries={BR:'Brasil',US:'Estados Unidos',UNKNOWN:'Mercado não informado'};
const resources={balances:'Saldos',positions:'Posições',activities:'Atividades'};
const outcomes={AVAILABLE:'Disponível',PARTIAL:'Parcial',FAILED:'Falha na leitura',UNAVAILABLE:'Indisponível',
  REAUTH_REQUIRED:'Reautenticação necessária na SnapTrade',UNKNOWN:'Estado da conexão não informado',NOT_SEEN:'Ausente na última descoberta'};
const kindNames={stock:'Ações',etf:'ETF',mutualfund:'Fundos',adr:'ADR',bond:'Renda fixa',option:'Opção',
  preferred_stock:'Ações preferenciais',reit:'REITs',DIVIDEND:'Dividendo',INTEREST:'Juros',TAX:'Retenção ou tributo',
  FEE:'Taxa',CAPITAL:'Capital',REINVESTMENT:'Reinvestimento',TRANSFER:'Transferência',
  CORPORATE_ACTION:'Evento corporativo',REVIEW:'A revisar'};
const statusNames={
  SNAPTRADE_AUTH:'A SnapTrade recusou a autenticação. Confira as credenciais Personal na configuração do add-on.',
  SNAPTRADE_SIGNATURE:'A SnapTrade recusou a assinatura. Confira se o Client ID e o Consumer Key pertencem à mesma chave Personal.',
  SNAPTRADE_FORBIDDEN:'A SnapTrade recusou o acesso ao recurso. Confira as permissões e a conexão na SnapTrade.',
  SNAPTRADE_RATE_LIMIT:'Limite de chamadas. Aguarde o horário indicado antes de tentar de novo.',
  SNAPTRADE_ACCOUNT_RATE_LIMIT:'Uma conta atingiu o limite de chamadas. Consulte o horário no diagnóstico da conta.',
  SNAPTRADE_BUSY:'Uma coleta está em andamento. Atualize o diagnóstico ao término.',
  SNAPTRADE_TRANSPORT:'Falha de comunicação com a SnapTrade. Confira a conectividade do add-on e tente novamente.',
  SNAPTRADE_CREDENTIALS_LOCKED:'A chave local de credenciais está indisponível. Confira a configuração da administração privada.',
  SNAPTRADE_DISABLED:'Habilite a integração e preencha as credenciais Personal nas opções do add-on.',
  SNAPTRADE_INVALID_DATA:'A SnapTrade devolveu dados fora do formato esperado. Consulte o campo no diagnóstico.',
  SNAPTRADE_INVALID_JSON:'A resposta da SnapTrade não pôde ser lida como JSON. Consulte o diagnóstico e tente novamente.',
  SNAPTRADE_INVALID_PAGINATION:'A página de atividades veio inconsistente. Atualize novamente para retomar a coleta.',
  SNAPTRADE_SDK_CALL:'O cliente SnapTrade falhou antes de entregar os dados. Confira a versão do add-on e copie o diagnóstico.',
  SNAPTRADE_SDK_RESPONSE:'O cliente SnapTrade devolveu uma resposta incompatível. Copie o diagnóstico para investigação.',
  SNAPTRADE_SCOPE_MISMATCH:'A vinculação entre conta e conexão veio inconsistente. Confira as contas na SnapTrade e copie o diagnóstico.',
  SNAPTRADE_STORAGE:'Falha ao salvar os dados locais. Verifique o armazenamento do add-on antes de tentar novamente.',
  SNAPTRADE_RESPONSE_LIMIT:'A resposta da SnapTrade ultrapassou o limite de leitura. Copie o diagnóstico para investigação.',
  SNAPTRADE_INTERRUPTED:'A coleta foi interrompida. Atualize novamente para retomar a leitura.',
  SNAPTRADE_UNAVAILABLE:'O recurso está indisponível na SnapTrade. Confira a conexão e a cobertura da conta.',
  SNAPTRADE_LEASE_LOST:'A execução perdeu o controle da coleta. Atualize o diagnóstico antes de tentar novamente.',
  SNAPTRADE_OPERATION_DENIED:'O Finance bloqueou a operação. Copie o diagnóstico para investigação.',
  SNAPTRADE_IMPORT_FAILED:'A coleta falhou no add-on. Copie o diagnóstico para investigação.',
  SNAPTRADE_REMOTE:'A SnapTrade informou uma falha no serviço. Tente novamente mais tarde.',
  PTAX_UNAVAILABLE:'O Banco Central está indisponível. Tente atualizar as cotações mais tarde.',
  HTTP_RESPONSE_UNAVAILABLE:'A resposta da coleta não pôde ser lida. Atualize o diagnóstico para consultar o último resultado gravado.',
  CSRF_INVALID:'A sessão precisa ser renovada. Recarregue a página e tente novamente.',
  STORAGE_UNAVAILABLE:'O armazenamento do add-on está indisponível. Consulte o Supervisor.'
};
const presentOptions=[['original','Moedas originais'],['BRL','Converter para BRL'],['USD','Converter para USD']];
const kinds=['stock','reit','etf','mutualfund','bond','option','FIXED_INCOME','EQUITY','TREASURY'];
const mode=()=>privacyMode();
const labelKind=key=>String(key).startsWith('PLUGGY:')?investmentClassLabel(key):kindNames[key]||classLabel(key);
const formatDate=value=>value?dateBR(value):'Indisponível';
const errorText=error=>statusNames[error?.code]||'Não foi possível confirmar a operação. Atualize o diagnóstico antes de repetir.';

export function wealthMoney(value,currency,esc){
  return privateValue(value,esc,amount=>bankMoney(amount,currency));
}

export function wealthRate(value,esc){
  return privateValue(value,esc,exchangeRate);
}

function privateValue(value,esc,format){
  if(value==null)return 'Indisponível';
  if(mode()!=='visible')return '<span aria-label="Valor oculto">••••••</span>';
  return esc(format(value));
}

function optionList(entries,esc){
  return entries.map(([value,label])=>'<option value="'+esc(value)+'">'+esc(label)+'</option>').join('');
}

export function wealthPresentation(value,esc,attribute='data-wealth-presentation'){
  return '<label>Moeda de apresentação<select '+attribute+'>'+presentOptions.map(([key,label])=>
    '<option value="'+key+'" '+(key===value?'selected':'')+'>'+esc(label)+'</option>').join('')+'</select></label>';
}

export function wealthSummary(data,esc,{compositionDetails=true}={}){
  if(!data?.summary)return '<p>Resumo patrimonial indisponível.</p>';
  const summary=data.summary;
  const money=(value,currency)=>wealthMoney(value,currency,esc);
  const original=Object.entries(summary.original).map(([currency,item])=>'<li><strong>'+esc(currency)+'</strong>'+
    '<span>Posições '+money(item.positions,currency)+'</span><span>Caixa em corretora '+money(item.cash,currency)+'</span></li>').join('');
  const countriesList=Object.entries(summary.regions).map(([country,currencies])=>'<li><strong>'+esc(countries[country]||country)+'</strong>'+
    Object.entries(currencies).map(([currency,value])=>'<span>'+esc(currency)+' '+money(value,currency)+'</span>').join('')+'</li>').join('');
  const composition=Object.entries(summary.composition||{}).map(([key,groups])=>
    Object.keys(groups).length?'<details><summary>'+({kind:'Por classe',provider:'Por provedor',institution:'Por instituição'})[key]+
      '</summary><ul class="of-category-list">'+(key==='kind'&&summary.allocation?.length?
        summary.allocation.map(row=>[row.class,row.metric.amounts]):Object.entries(groups)).map(([name,values])=>
        '<li><strong>'+esc(key==='kind'?investmentClassLabel(name):name)+'</strong>'+Object.entries(values).map(([currency,value])=>
          '<span>'+esc(currency)+' '+money(value,currency)+'</span>').join('')+'</li>').join('')+'</ul></details>':'').join('');
  const target=summary.presentation;
  const display=summary.converted.positions!=null?summary.converted.positions:summary.converted_subtotal.positions;
  const converted=target!=='original'?'<p>'+(
    summary.converted.positions==null?'Subtotal convertido quando disponível':'Posições convertidas')+
    ' <strong>'+money(display,target)+'</strong></p>':'';
  const rates=summary.quote_dates.map(quote=>'<li>PTAX de venda · '+formatDate(quote.date)+' · '+wealthRate(quote.rate,esc)+
    ' por USD'+(quote.lag_days?' · '+quote.lag_days+' dias de defasagem':'')+'</li>').join('');
  const excluded=Object.entries(summary.investment_metric?.conversion_excluded||{});
  const exclusion=excluded.length?'<p>Valores originais fora da conversão '+excluded.map(([currency,value])=>money(value,currency)).join(' · ')+'</p>':'';
  return converted+exclusion+(summary.overlap?'<p class="attention">Possível sobreposição. Use uma conexão ou ajuste as fontes em Conexões.</p>':'')+
    (Object.keys(summary.original).length&&!summary.date_comparable?'<p>Datas financeiras diferentes. Consolidação incompleta.</p>':'')+
    (summary.stale?'<p>Há posições com referência desatualizada.</p>':'')+
    (summary.missing||summary.partial_resources?'<p>Há dados parciais. Consulte a origem e a referência das posições.</p>':'')+
    '<ul class="of-category-list of-wealth-currencies">'+(original||'<li>Sem posições ou caixa no escopo.</li>')+'</ul>'+
    (countriesList?'<details><summary>País de negociação informado</summary><p>Distribuição por mercado informado e moeda original.</p>'+
    '<ul class="of-category-list">'+countriesList+'</ul></details>':'')+
    (compositionDetails?composition:'')+(rates?'<details><summary>Taxas e datas da conversão</summary><ul>'+rates+'</ul></details>':'');
}

export function overviewWealth(data,esc,presentation){
  return '<section class="of-summary-card of-wealth-overview"><div class="of-section-heading"><div><h3>Distribuição geográfica e por moeda</h3></div>'+
    wealthPresentation(presentation,esc)+'</div>'+wealthSummary(data,esc,{compositionDetails:false})+
    '<button type="button" class="of-link" data-open-unified-portfolio>Ver carteira unificada</button></section>';
}

export function mountWealth({host,api,esc,navigation,state,today,getPeriod,snaptrade=true}){
  const panel=host.querySelector('#of-panel-assets'),section=document.createElement('section');
  section.className='panel of-wealth';
  const legacy=document.createElement('details');
  legacy.className='panel of-wealth-legacy';
  legacy.innerHTML='<summary>Dados detalhados da Pluggy</summary>';
  legacy.append(...panel.children);
  panel.append(legacy);
  panel.prepend(section);
  const options=(entries)=>optionList(entries,esc);
  section.innerHTML='<h2>Carteira unificada</h2><form class="of-overview-filters" aria-label="Filtros da carteira">'+
    '<label>Visualizar<select name="view">'+options([['portfolio','Posições'],...(snaptrade?[['activities','Atividades da corretora'],['income','Proventos internacionais']]:[]),['history','Histórico patrimonial']])+'</select></label>'+
    '<label>Moeda de apresentação<select name="presentation">'+options(presentOptions)+'</select></label>'+
    '<details class="of-wealth-advanced"><summary>Filtros e ordenação</summary><div class="of-overview-filters">'+
    '<label hidden>Agrupar proventos<select name="group">'+options([['month','Por mês'],['year','Por ano']])+'</select></label>'+
    '<label>Mercado<select name="market">'+options([['','Todos'],['BR','Brasil'],['INTERNATIONAL','Internacional'],['UNKNOWN','Não informado']])+'</select></label>'+
    '<label>Provedor<select name="provider">'+options([['','Todos'],['PLUGGY','Pluggy'],...(snaptrade?[['SNAPTRADE','SnapTrade']]:[])])+'</select></label>'+
    '<label>Instituição<select name="connection_id"><option value="">Todas</option></select></label>'+
    '<label>Conta<select name="account_id"><option value="">Todas</option></select></label>'+
    '<label>Moeda original<input name="currency" maxlength="3" pattern="[A-Z]{3}" placeholder="Todas"></label>'+
    '<label>Classe<select name="kind">'+options([['','Todas'],...kinds.map(key=>[key,labelKind(key)])])+'</select></label>'+
    '<label>Ordem<select name="sort">'+options([['name','Nome ou ticker'],['value','Valor'],['participation','Participação']])+'</select></label>'+
    '<label>Buscar<input name="search" type="search" maxlength="160"></label>'+
    '<label>De<input name="start" type="date"></label><label>Até<input name="end" type="date"></label>'+
    '<label><input name="history" type="checkbox"> Incluir histórico arquivado</label></div></details><button type="submit">Aplicar</button></form>'+
    '<div data-wealth-class hidden></div><div data-wealth-result aria-live="polite"></div>';
  const form=section.querySelector('form'),result=section.querySelector('[data-wealth-result]'),queries=createQueryGeneration(navigation);
  const classFilter=section.querySelector('[data-wealth-class]');
  const names=['view','market','provider','connection_id','account_id','currency','presentation','kind','sort','search','start','end','group'];
  state.group||='month';state.view||='portfolio';state.presentation||='original';state.sort||='name';
  let loaded=null,filters={},accounts=[],page=1,asset=null;
  const money=(value,currency)=>wealthMoney(value,currency,esc);
  function fields(){
    const refs=accounts.filter(row=>!form.elements.provider.value||row.provider===form.elements.provider.value);
    const connections=[...new Map(refs.map(row=>[row.connection_id,row.institution])).entries()];
    const cid=form.elements.connection_id.value||state.connection_id||'';
    form.elements.connection_id.innerHTML=options([['','Todas'],...connections]);
    if(connections.some(([key])=>key===cid))form.elements.connection_id.value=cid;
    const aid=form.elements.account_id.value||state.account_id||'';
    const available=refs.filter(row=>!form.elements.connection_id.value||row.connection_id===form.elements.connection_id.value);
    form.elements.account_id.innerHTML=options([['','Todas'],...available.map(row=>[row.id,row.label])]);
    if(available.some(row=>row.id===aid))form.elements.account_id.value=aid;
  }
  function controlMode(){
    form.elements.group.closest('label').hidden=form.elements.view.value!=='income';
    const hidden=mode()==='full';
    for(const option of form.elements.sort.options)option.disabled=hidden&&option.value!=='name';
    form.elements.sort.value=hidden?'name':state.sort;
  }
  function ownedActivity(row){
    return '<article class="of-flow-item"><div><strong>'+esc(row.description||labelKind(row.kind))+'</strong>'+
      '<p>'+esc(row.institution)+' · '+esc(row.ticker||row.provider_kind)+' · '+formatDate(row.date)+'</p>'+
      '<small>'+esc(labelKind(row.kind))+(row.classification_source==='OWNER_RULE'?' · Regra confirmada':'')+'</small>'+
      (row.rule_eligible?'<p>Revisão disponível na Central de classificação.</p>':'')+'</div><div><strong>'+
      money(row.amount,row.currency)+'</strong>'+(row.presented_amount!=null?'<p>'+money(row.presented_amount,filters.presentation)+
      (row.fx?' · PTAX '+formatDate(row.fx.date):'')+'</p>':'')+'</div></article>';
  }
  function cashRows(){
    if(!loaded?.cash?.length)return '';
    return '<details><summary>Caixa, poder de compra e margem</summary><ul class="of-category-list">'+loaded.cash.map(row=>
      '<li><strong>'+esc(row.institution+' · '+row.currency)+'</strong>'+
      '<span>Caixa '+money(row.cash,row.currency)+'</span><span>Poder de compra '+money(row.buying_power,row.currency)+'</span>'+
      '<span>Margem devedora '+money(row.margin_debit,row.currency)+'</span>'+
      '<small>Referência '+formatDate(row.reference_at)+'</small></li>').join('')+'</ul></details>';
  }
  function positionRows(){
    return loaded.items.map((row,index)=>'<article class="of-flow-item"><div><strong>'+esc(row.ticker||row.label)+'</strong>'+
      '<p>'+bankMark(row.institution,esc)+esc(row.institution)+' · '+esc(row.provider)+' · '+esc(row.asset_class?investmentClassLabel(row.asset_class):labelKind(row.kind))+
      (row.exchange?' · '+esc(row.exchange):'')+(row.state!=='AVAILABLE'?' · Histórico':'')+'</p>'+
      '<button type="button" class="of-link" data-wealth-asset="'+index+'">Ver posição</button></div>'+
      '<div><strong>'+money(row.market_value,row.currency)+'</strong>'+
      (row.presented_value!=null?'<p>'+money(row.presented_value,filters.presentation)+'</p>':'')+
      (mode()==='visible'&&row.participation!=null?'<small>'+esc(row.participation)+'% de '+esc(row.currency)+'</small>':'')+
      '</div></article>').join('');
  }
  function detail(row){
    const quantities=value=>privateValue(value,esc,String);
    return '<div class="of-summary-card" tabindex="-1" data-wealth-detail><h3>'+esc(row.ticker||row.label)+'</h3>'+
      '<p>'+[row.provider,row.institution,row.account_label,labelKind(row.kind),row.currency,row.exchange].filter(Boolean).map(esc).join(' · ')+'</p>'+
      '<dl class="of-wealth-grid"><div><dt>Posição</dt><dd>'+money(row.market_value,row.currency)+'</dd></div>'+
      '<div><dt>Quantidade</dt><dd>'+quantities(row.units)+'</dd></div><div><dt>Preço por unidade</dt><dd>'+money(row.price,row.currency)+'</dd></div>'+
      '<div><dt>Custo por unidade informado</dt><dd>'+money(row.cost,row.currency)+'</dd></div>'+
      '<div><dt>Resultado não realizado informado</dt><dd>'+money(row.unrealized,row.currency)+'</dd></div>'+
      '<div><dt>Referência financeira</dt><dd>'+formatDate(row.reference_at)+'</dd></div>'+
      '<div><dt>Coleta</dt><dd>'+formatDate(row.observed_at)+'</dd></div></dl>'+
      (row.lots?.length?'<details><summary>Lotes informados</summary><ul>'+row.lots.map(lot=>
        '<li>'+formatDate(lot.date)+' · '+quantities(lot.units)+' unidades · '+money(lot.cost,row.currency)+'</li>').join('')+'</ul></details>':
        '<p>Lotes indisponíveis para esta posição.</p>')+
      '<div class="actions"><button type="button" data-asset-view="activities">Operações do ativo</button>'+
      '<button type="button" data-asset-view="income">Proventos do ativo</button>'+
      '<button type="button" data-asset-view="history">Histórico da posição</button>'+
      '<button type="button" class="quiet" data-close-asset>Voltar à carteira</button></div></div>';
  }
  function history(){
    const points=loaded.points||[];
    const note=loaded.state==='OVERLAP'?'Selecione uma conexão para resolver a possível sobreposição.':
      loaded.basis==='COLLECTION_DATE'?'Posições por data de coleta (UTC). As referências financeiras dos ativos podem diferir.':
      loaded.state==='FORMING'?'Histórico patrimonial em formação.':'Observações com referências comparáveis.';
    const rows=mode()==='full'?'':points.map(point=>'<li><span>'+formatDate(point.date)+'</span>'+
      (point.original?Object.entries(point.original).map(([currency,value])=>'<strong>'+money(value,currency)+'</strong>').join(''):
        '<strong>'+money(point.value,filters.presentation)+'</strong>')+
      (point.fx?'<small>PTAX '+formatDate(point.fx.date)+'</small>':'')+'</li>').join('');
    return '<h3>Evolução patrimonial</h3><p>'+note+'</p>'+
      (rows?'<ul class="of-category-list">'+rows+'</ul>':'');
  }
  function paint(){
    if(!loaded)return;
    const view=filters.view;
    if(view==='history'){result.innerHTML=(asset?detail(asset):'')+history();return;}
    const incomes=view==='income'&&loaded.income?.length?'<ul class="of-category-list">'+loaded.income.map(row=>
      '<li><strong>'+esc(row.month+' · '+row.currency)+'</strong>'+
      Object.entries(row.components).map(([key,value])=>'<span>'+esc(labelKind(key))+' '+money(value,row.currency)+'</span>').join('')+'</li>').join('')+'</ul>':'';
    const contents=view==='portfolio'?wealthSummary(loaded,esc)+cashRows():incomes;
    const rows=view==='portfolio'?positionRows():loaded.items.map(ownedActivity).join('');
    const pagination=loaded.total_pages>1?'<div class="actions of-pagination"><button type="button" data-wealth-page="-1" '+(page<=1?'disabled':'')+'>Anterior</button>'+
      '<span>Página '+page+' de '+loaded.total_pages+'</span><button type="button" data-wealth-page="1" '+(page>=loaded.total_pages?'disabled':'')+'>Próxima</button></div>':'';
    result.innerHTML=(asset?detail(asset):'')+contents+'<p>'+countBR.format(loaded.total)+' registros encontrados</p>'+
      (rows||'<p>Nenhum registro para o escopo.</p>')+pagination;
  }
  async function load(){
    const query=queries.begin();
    filters={};
    for(const name of names)if(form.elements[name].value)filters[name]=form.elements[name].value;
    if(!accounts.length){
      for(const key of ['connection_id','account_id'])if(state[key])filters[key]=state[key];
    }
    if(form.elements.history.checked)filters.history='1';
    if(asset){
      filters.account_id=asset.account_id;
      filters.asset=asset.instrument_id;
    }
    if(filters.view==='history'){
      for(const key of ['kind','market','search'])delete filters[key];
    }
    if(filters.view!=='income')delete filters.group;
    if(filters.view==='portfolio'){
      delete filters.start;delete filters.end;
      if(state.asset_class)filters.asset_class=state.asset_class;
    }
    classFilter.hidden=!filters.asset_class;
    classFilter.innerHTML=filters.asset_class?'<p>Classe · '+esc(investmentClassLabel(filters.asset_class))+
      ' <button type="button" class="of-link">Remover filtro da classe</button></p>':'';
    const clear=classFilter.querySelector('button');
    if(clear)clear.onclick=()=>{
      state.asset_class='';page=1;load();form.elements.kind.focus();
    };
    const params=new URLSearchParams({...filters,page:String(page)});
    if(mode()==='full')params.set('sort','name');
    loaded=null;
    result.innerHTML='<p role="status">Carregando carteira…</p>';
    result.setAttribute('aria-busy','true');
    try{
      const data=await api('/open-finance/portfolio?'+params,{queryScope:query});
      if(!query.current()||!host.isConnected)return;
      if(data.accounts){accounts=data.accounts;fields();}
      loaded=data;
      paint();
    }catch(_){
      if(query.current())result.innerHTML='<p role="alert">Não foi possível consultar a carteira.</p><button type="button" data-wealth-retry>Tentar novamente</button>';
    }finally{if(query.current())result.removeAttribute('aria-busy');}
  }
  function setView(view){form.elements.view.value=view;state.view=view;page=1;controlMode();load();}
  form.elements.view.onchange=controlMode;
  form.elements.provider.onchange=()=>{state.connection_id='';state.account_id='';fields()};
  form.elements.connection_id.onchange=()=>{state.account_id='';fields()};
  form.onsubmit=event=>{
    event.preventDefault();
    for(const name of names)if(mode()!=='full'||name!=='sort')state[name]=form.elements[name].value;
    state.history=form.elements.history.checked;
    if(form.elements.view.value!=='portfolio'||form.elements.kind.value)state.asset_class='';
    asset=null;page=1;load();
  };
  result.onclick=event=>{
    const button=event.target.closest('button');
    if(!button)return;
    if(button.dataset.wealthAsset!=null){asset=loaded.items[Number(button.dataset.wealthAsset)];paint();result.querySelector('[data-wealth-detail]').focus();}
    else if(button.dataset.closeAsset!=null){asset=null;setView('portfolio');}
    else if(button.dataset.assetView){setView(button.dataset.assetView);}
    else if(button.dataset.wealthPage){page+=Number(button.dataset.wealthPage);load();}
    else if(button.dataset.wealthRetry!=null)load();
  };
  let prior=mode();
  host.addEventListener('finance-privacy-changed',()=>{
    const current=mode(),needsOrder=(prior==='full')!==(current==='full')&&state.sort!=='name';
    prior=current;controlMode();
    if(needsOrder&&!panel.hidden){page=1;load();}else paint();
  });
  host.addEventListener('of-tab-selected',event=>{
    if(event.detail!=='assets'){queries.cancel();return;}
    const period=getPeriod();
    if(period.presentation)state.presentation=period.presentation;
    for(const name of names)if(name!=='sort'&&name!=='connection_id'&&name!=='account_id')form.elements[name].value=state[name]||(
      name==='start'?period.start||'':name==='end'?period.end||today:'');
    form.elements.history.checked=Boolean(state.history);
    fields();controlMode();load();
  });
  return {show(context){
    if(state.asset_class&&!context.asset_class)state.currency='';
    Object.assign(state,{asset_class:''},context);
    for(const key of ['connection_id','account_id'])form.elements[key].value='';
    asset=null;page=1;
  },showLegacy(){legacy.open=true;}};
}

export function mountSnapTradeConnections({host,panel,api,esc,navigation,today,enabled}){
  if(!enabled)return;
  const section=document.createElement('section');
  section.className='panel of-snaptrade-connections';
  section.innerHTML='<h2>SnapTrade</h2><div data-snaptrade-result></div><p role="status" data-snaptrade-feedback></p>';
  panel.append(section);
  const body=section.querySelector('[data-snaptrade-result]'),feedback=section.querySelector('[data-snaptrade-feedback]');
  const queries=createQueryGeneration(navigation);
  let data=null,busy=false,lastReply=null,diagnosisOpen=false;
  const diagnosisLabels={request_id:'Identificador da tentativa',phase:'Operação',state:'Resultado',attempted_at:'Data da tentativa',
    stage:'Etapa',resource:'Recurso',reason:'Motivo',field:'Campo',remote_status:'HTTP da SnapTrade',error_code:'Código'};
  function diagnosis(raw){
    if(!raw||!(/^[a-f0-9]{32}$/).test(raw.request_id||''))return null;
    const detail={request_id:raw.request_id};
    for(const field of ['phase','state','stage','resource','reason','field','error_code']){
      if(typeof raw[field]==='string'&&/^[a-zA-Z_][a-zA-Z_0-9]{0,63}$/.test(raw[field]))detail[field]=raw[field];
    }
    if(typeof raw.attempted_at==='string'&&/^\d{4}-\d{2}-\d{2}T[0-9:]+Z$/.test(raw.attempted_at))detail.attempted_at=raw.attempted_at;
    if(Number.isInteger(raw.remote_status)&&raw.remote_status>=100&&raw.remote_status<=599)detail.remote_status=raw.remote_status;
    return detail;
  }
  async function copyDiagnosis(){
    const detail=diagnosis(lastReply||data?.last_attempt_result);
    if(!detail)return;
    const value=JSON.stringify(detail,null,2);
    try{
      await navigator.clipboard.writeText(value);
      feedback.textContent='Diagnóstico copiado.';
    }catch(_){
      const output=body.querySelector('[data-snap-copy-text]');
      if(output){output.hidden=false;output.value=value;output.focus();output.select();}
      feedback.textContent='Diagnóstico selecionado. Use o atalho de copiar.';
    }
  }
  const fmt=value=>value?new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short'}).format(new Date(value)):'Indisponível';
  function paint(){
    if(!data)return;
    const policy=(row,name,label)=>'<label><input type="checkbox" name="'+name+'" '+(row[name]?'checked':'')+'> '+label+'</label>';
    const rows=data.connections.map(row=>'<article class="of-summary-card"><h3>'+bankMark(row.institution,esc)+esc(row.institution)+'</h3>'+
      '<p>'+esc(row.archived?'Arquivada localmente':outcomes[row.provider_state]||'Estado não disponível')+' · '+countBR.format(row.accounts.length)+' contas'+
      (row.permission?' · '+(row.permission==='read'?'Somente leitura na corretora':'Permissão informada de negociação'):'')+'</p>'+
      '<details><summary>Contas e diagnóstico</summary><ul class="of-category-list">'+row.accounts.map(account=>
        '<li><strong>'+esc(account.label)+'</strong><span>'+
        (account.suffix&&mode()!=='full'?'•••• '+esc(account.suffix)+' · ':'')+
        countBR.format(account.positions)+' posições'+(account.currencies?' · '+esc(account.currencies):'')+'</span>'+
        '<small>Atualização conhecida pela SnapTrade '+fmt(account.provider_updated_at)+'</small>'+
        '<small>Leitura local '+fmt(account.observed_at)+'</small>'+
        (account.coverage.length?'<ul>'+account.coverage.map(item=>'<li>'+esc(resources[item.resource])+' · '+esc(outcomes[item.state]||'Não consultado')+
           (item.first_date?' · '+formatDate(item.first_date)+' a '+formatDate(item.last_date):'')+
           (item.retry_at?' · Próxima tentativa a partir de '+fmt(item.retry_at):'')+'</li>').join('')+'</ul>':'<small>Recursos ainda não consultados</small>')+
        '</li>').join('')+'</ul></details>'+
      '<form data-snap-policy="'+esc(row.id)+'" aria-label="Política de '+esc(row.institution)+'" class="of-presentation">'+
      policy(row,'paused','Pausar coleta automática')+policy(row,'archived','Arquivar localmente')+
      policy(row,'excluded','Excluir da consolidação')+
      '<button type="submit" class="quiet">Salvar política</button></form>'+
      '<button type="button" data-snap-sync="'+esc(row.id)+'" '+(row.archived||!data.configured?'disabled':'')+'>Atualizar esta conexão</button></article>').join('');
    const diagnostic=diagnosis(lastReply||data.last_attempt_result);
    const diagnosticBox=diagnostic?'<details data-snap-diagnosis '+(diagnosisOpen?'open':'')+'><summary>Diagnóstico técnico</summary>'+
      '<dl class="of-wealth-grid">'+Object.entries(diagnostic).map(([key,value])=>'<div><dt>'+diagnosisLabels[key]+
        '</dt><dd>'+esc(value)+'</dd></div>').join('')+'</dl>'+
      '<button type="button" data-snap-copy>Copiar diagnóstico</button>'+
      '<textarea data-snap-copy-text aria-label="Diagnóstico sanitizado" readonly hidden></textarea></details>':'';
    body.innerHTML='<p>'+(data.configured?'Credenciais configuradas.':'Informe as credenciais nas opções do add-on.')+'</p>'+
      (data.error_code?'<p class="attention">'+esc(statusNames[data.error_code]||'Última coleta incompleta')+'</p>':'')+
      '<dl class="of-wealth-grid"><div><dt>Última tentativa local</dt><dd>'+fmt(data.last_attempt)+'</dd></div>'+
      '<div><dt>Última coleta bem-sucedida</dt><dd>'+fmt(data.last_success)+'</dd></div>'+
      '<div><dt>Próxima coleta local</dt><dd>'+fmt(data.next_attempt)+'</dd></div></dl>'+
      '<p>Resultado da última tentativa '+esc(data.last_result==='RUNNING'?'Em andamento':outcomes[data.last_result]||'Indisponível')+'</p>'+
      diagnosticBox+'<div class="actions"><button type="button" data-snap-retry class="quiet">Atualizar diagnóstico</button>'+
      '<button type="button" data-snap-discover '+(data.configured?'':'disabled')+'>Testar credenciais e descobrir contas</button>'+
      '<button type="button" data-snap-sync="" '+(data.configured?'':'disabled')+'>Atualizar dados</button></div>'+
      '<form data-snap-preferences aria-label="Preferências SnapTrade" class="of-presentation">'+
      '<label><input type="checkbox" name="auto" '+(data.auto_enabled?'checked':'')+' '+(data.configured?'':'disabled')+'> Coleta automática</label>'+
      '<label>Intervalo SnapTrade<select name="hours">'+data.options.map(hours=>'<option value="'+hours+'" '+(hours===data.interval_hours?'selected':'')+'>'+hours+' h</option>').join('')+'</select></label>'+
      '<button type="submit">Salvar configuração</button></form>'+
      '<details><summary>Cotações PTAX</summary><form data-snap-fx class="of-presentation">'+
      '<label>De<input name="start" type="date" value="'+esc(today.slice(0,7)+'-01')+'" required></label>'+
      '<label>Até<input name="end" type="date" value="'+esc(today)+'" required></label>'+
      '<button type="submit">Atualizar cotações do Banco Central</button></form></details>'+
      (data.registry_admin_available?'<details><summary>Credenciais protegidas</summary><form data-snap-credentials class="of-presentation">'+
        '<label>Client ID<input name="client_id" type="password" autocomplete="off" maxlength="256" required></label>'+
        '<label>Consumer Key<input name="consumer_key" type="password" autocomplete="new-password" maxlength="256" required></label>'+
        '<button type="submit">Salvar credenciais protegidas</button></form></details>':'')+
      '<div class="of-connection-grid">'+rows+'</div>';
    const details=body.querySelector('[data-snap-diagnosis]');
    if(details)details.ontoggle=()=>{if(details.isConnected)diagnosisOpen=details.open;};
  }
  async function load(){
    const query=queries.begin();
    body.setAttribute('aria-busy','true');
    try{
      const next=await api('/open-finance/snaptrade',{queryScope:query});
      if(query.current()&&host.isConnected){
        data=next;
        if(next.last_attempt_result?.request_id)lastReply=null;
        paint();
        return next;
      }
    }catch(_){if(query.current()&&!data)body.innerHTML='<p role="alert">Diagnóstico SnapTrade indisponível.</p><button data-snap-retry>Tentar novamente</button>';}
    finally{if(query.current())body.removeAttribute('aria-busy');}
  }
  async function submit(path,payload){
    if(busy)return;
    busy=true;feedback.textContent='Processando…';
    const refresh=['snaptrade/discovery','snaptrade/sync'].includes(path);
    const previous=data?.last_attempt_result?.request_id;
    try{
      const answer=await api('/open-finance/'+path,{method:'POST',body:payload});
      if(!panel.hidden&&host.isConnected){
        lastReply=diagnosis(answer.diagnostic);
        await load();
        feedback.textContent=answer.state==='PARTIAL'?(answer.error_code?errorText({code:answer.error_code}):
          'Coleta parcial. Execute novamente para continuar a leitura.'):
          answer.state==='AVAILABLE'&&refresh?'Leitura concluída.':'Operação concluída.';
      }
    }catch(error){
      if(!panel.hidden&&host.isConnected){
        const fromResponse=diagnosis(error.diagnostic);
        const latest=refresh?await load():null;
        const recovered=latest?.last_attempt_result?.request_id!==previous?diagnosis(latest?.last_attempt_result):null;
        lastReply=fromResponse||recovered;
        if(lastReply)paint();
        feedback.textContent=errorText({code:lastReply?.error_code||error.code});
      }
    }finally{busy=false;}
  }
  body.onclick=event=>{
    const button=event.target.closest('button');
    if(!button)return;
    if(button.hasAttribute('data-snap-discover'))submit('snaptrade/discovery',{});
    if(button.hasAttribute('data-snap-sync'))submit('snaptrade/sync',button.dataset.snapSync?{connection_id:button.dataset.snapSync}:{});
    if(button.hasAttribute('data-snap-retry'))load();
    if(button.hasAttribute('data-snap-copy'))copyDiagnosis();
  };
  body.onsubmit=event=>{
    event.preventDefault();
    const form=event.target,fields=form.elements;
    if(form.matches('[data-snap-preferences]'))submit('snaptrade/preferences',
       {auto_enabled:fields.auto.checked,interval_hours:Number(fields.hours.value),revision:data.revision});
    if(form.matches('[data-snap-policy]'))submit('snaptrade/policy',
       {connection_id:form.dataset.snapPolicy,paused:fields.paused.checked,archived:fields.archived.checked,excluded:fields.excluded.checked});
    if(form.matches('[data-snap-fx]'))submit('portfolio/fx',{start:fields.start.value,end:fields.end.value});
    if(form.matches('[data-snap-credentials]')){
      const credentials={client_id:fields.client_id.value,consumer_key:fields.consumer_key.value};
      form.reset();submit('snaptrade/credentials',credentials);
    }
  };
  host.addEventListener('of-tab-selected',event=>{if(event.detail==='connections')load();else queries.cancel()});
  host.addEventListener('finance-privacy-changed',()=>{if(!panel.hidden)paint();});
}
