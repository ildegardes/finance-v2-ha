import {bankMoney,dateBR} from './privacy.js';

const kinds={accounts:'Contas e saldos',item:'Instituição e conexão',resources:'Recursos autorizados',consents:'Consentimentos',transactions:'Movimentações completas',investments:'Posições de investimentos',investment_transactions:'Movimentos de investimentos',loans:'Crédito e obrigações',bills:'Faturas e pagamentos registrados',statements:'Referências de extratos'};
const states={AVAILABLE:'Consulta completa',EMPTY:'Consulta completa sem registros',NOT_AUTHORIZED:'Acesso não autorizado',NOT_AVAILABLE:'Recurso não disponível',NOT_COLLECTED:'Ainda não coletado pelo provedor',RUNNING:'Leitura em andamento',FAILED:'Leitura falhou'};
const labels={balance:'Saldo informado',availableCreditLimit:'Limite disponível',creditLimit:'Limite contratado',minimumPayment:'Pagamento mínimo',balanceCloseDate:'Fechamento',balanceDueDate:'Vencimento',totalAmount:'Valor total',minimumPaymentAmount:'Pagamento mínimo',dueDate:'Vencimento',billClosingDate:'Fechamento',currencyCode:'Moeda',totalAmountCurrencyCode:'Moeda da fatura',amount:'Valor',value:'Preço informado',netAmount:'Valor líquido',amountProfit:'Resultado informado',amountOriginal:'Valor original',amountWithdrawal:'Resgate informado',quantity:'Quantidade',rate:'Taxa',annualRate:'Taxa anual',lastMonthRate:'Rentabilidade do último mês informada',lastTwelveMonthsRate:'Rentabilidade dos últimos 12 meses informada',type:'Tipo',subtype:'Subtipo',status:'Estado informado',name:'Nome',description:'Descrição',descriptionRaw:'Descrição original',date:'Data',updatedAt:'Atualizado no provedor',createdAt:'Criado no provedor',lastUpdatedAt:'Última atualização',creditData:'Dados do cartão',bankData:'Dados bancários',contractAmount:'Valor contratado',contractRemainingNumber:'Parcelas restantes',totalNumberOfInstallments:'Total de parcelas',paidInstallments:'Parcelas pagas',dueInstallments:'Parcelas a vencer',pastDueInstallments:'Parcelas vencidas',payments:'Pagamentos informados',installments:'Parcelas',interestRates:'Taxas de juros',CET:'Custo efetivo total',financeCharges:'Encargos',contractedFees:'Tarifas contratadas',contractedFinanceCharges:'Encargos contratados',warranties:'Garantias',balanceForeignCurrency:'Saldo em moeda estrangeira',closingBalance:'Saldo de fechamento',automaticallyInvestedBalance:'Saldo aplicado automaticamente',overdraftContractedLimit:'Cheque especial contratado',overdraftUsedLimit:'Cheque especial utilizado',resourcesCollectedAt:'Recursos coletados em',consentExpiresAt:'Consentimento vence em',products:'Produtos',openFinancePermissionsGranted:'Permissões autorizadas',revokedAt:'Revogado em',expiresAt:'Vencimento da autorização',monthYear:'Competência do extrato',isUpdated:'Atualizado na última coleta',statusDetail:'Qualidade por produto'};
const privateNumbers=/balance|amount|value|limit|payment|profit|tax|rate|CET|quantity|price/i;

export function mountCoverage({host,api,esc,catalog}){
  const areas={overview:'accounts',cards:'accounts',assets:'investments',credit:'loans',connections:'item'};
  const controllers=[];
  function valueHtml(value,key,currency,depth=0){
    if(depth>8)return 'Detalhamento indisponível';
    if(value===null)return '<span>Não informado pelo provedor</span>';
    if(typeof value==='boolean')return value?'Sim':'Não';
    if(Array.isArray(value))return value.length?`<ul>${value.map(v=>`<li>${valueHtml(v,key,currency,depth+1)}</li>`).join('')}</ul>`:'Nenhum registro informado';
    if(typeof value==='object')return fields(value,key==='balanceForeignCurrency'?null:currency,depth+1);
    if(/Date$|At$|^date$|^purchaseDate$|^tradeDate$/.test(key))return esc(dateBR(value));
    if(privateNumbers.test(key)&&/^-?\d+(\.\d+)?$/.test(String(value))){
      const rate=/rate|CET|quantity/i.test(key);
      return `<span data-private-financial>${esc(rate?String(value).replace('.',','):bankMoney(value,currency))}</span>`;
    }
    return esc(String(value));
  }
  function fields(data,currency=null,depth=0){
    const hidden=new Set(['id','itemId','accountId','resourceId','billId','providerId','providerCode','code','isin','order','transactions']);
    currency=data.currencyCode||data.totalAmountCurrencyCode||currency;
    return `<dl class="of-resource-fields">${Object.entries(data).filter(([k])=>!hidden.has(k)).map(([k,v])=>`<div><dt>${esc(labels[k]||k.replace(/([a-z])([A-Z])/g,'$1 $2'))}</dt><dd>${valueHtml(v,k,currency,depth)}</dd></div>`).join('')}</dl>`;
  }
  for(const [area,defaultResource]of Object.entries(areas)){
    const panel=host.querySelector('#of-panel-'+area);if(!panel)continue;
    if(area==='overview'||area==='assets')panel.replaceChildren();
    const section=document.createElement('section');section.className='panel of-coverage';
    section.innerHTML=`<h2>${esc(area==='overview'?'Contas, saldos e cobertura':area==='assets'?'Carteira e movimentações':area==='cards'?'Cartões e faturas':area==='credit'?'Crédito e obrigações':'Diagnóstico de cobertura')}</h2><p class="of-notice">Somente dados já disponibilizados em cache pela instituição. Ausência, indisponibilidade e zero são distintos. Saldos de contas e investimentos não são somados como patrimônio: moedas e possíveis sobreposições não estão comprovadas.</p><form class="of-resource-filter form-grid"><label>Recurso<select name="resource">${Object.entries(kinds).map(([id,label])=>`<option value="${id}">${label}</option>`).join('')}</select></label><label>Instituição<select name="connection_id"><option value="">Todas</option>${catalog.connections.map(c=>`<option value="${esc(c.id)}">${esc(c.institution)}</option>`).join('')}</select></label><button type="submit">Consultar staging</button></form><div class="of-resource-result" aria-live="polite"></div>`;
    panel.append(section);
    const form=section.querySelector('form'),result=section.querySelector('.of-resource-result');form.elements.resource.value=defaultResource;
    const historyLabel=document.createElement('label');historyLabel.innerHTML='<input type="checkbox" name="history"> Histórico de observações (não é rentabilidade calculada)';form.append(historyLabel);
    const typeLabel=document.createElement('label');typeLabel.innerHTML='<span>Tipo / classe informado</span><input name="type" maxlength="64" pattern="[A-Za-z0-9_-]*" placeholder="Ex.: FIXED_INCOME">';form.append(typeLabel);
    const currencyLabel=document.createElement('label');currencyLabel.innerHTML='<span>Moeda</span><input name="currency" maxlength="3" pattern="[A-Z]{3}" placeholder="Ex.: BRL">';form.append(currencyLabel);
    let page=1,generation=0;
    async function load(){
      const current=++generation;result.innerHTML='<p role="status">Consultando dados importados…</p>';
      const q=new URLSearchParams({resource:form.elements.resource.value,page:String(page),page_size:'25'});
      if(form.elements.connection_id.value)q.set('connection_id',form.elements.connection_id.value);
      if(form.elements.history.checked)q.set('history','1');
      if(form.elements.type.value)q.set('type',form.elements.type.value);
      if(form.elements.currency.value)q.set('currency',form.elements.currency.value);
      if(area==='cards'&&form.elements.resource.value==='accounts')q.set('type','CREDIT');
      try{
        const response=await api('/open-finance/resources?'+q);
        if(!host.isConnected||current!==generation)return;
        let items=response.items;
        // Filtering is never applied to a partial page: cards use the server-side type filter.
        const diagnostics=response.coverage.map(c=>`${states[c.state]||'Estado não reconhecido'} · ${c.record_count} registros · ${c.page_count} páginas · ${dateBR(c.observed_at)}${c.omitted_field_count?' · Há campos privados/não contratados omitidos':''}`).join(' | ');
        result.innerHTML=`<p>${esc(diagnostics||'Recurso ainda não consultado para este escopo.')} · Página ${page} · ${response.total} registros preservados</p>${items.length?items.map(row=>`<article class="of-resource-card"><h3>${esc(row.data.name||row.data.productName||row.data.description||kinds[response.resource])}</h3><p>${esc(catalog.connections.find(c=>c.id===row.connection_id)?.institution||'Instituição histórica')} · ${row.state==='NOT_SEEN'?'Não observado na última consulta completa; não significa exclusão':'Registro preservado'} · Observado em ${dateBR(row.observed_at)}</p>${fields(row.data)}<details><summary>Proveniência do novo registro</summary><p>Observação registrada no staging por execução identificada. Não altera a proveniência F07 dos registros legados. O histórico não representa rentabilidade calculada.</p></details></article>`).join(''):'<p class="empty">Nenhum registro importado neste escopo. Isso não comprova ausência do produto na instituição.</p>'}<div class="actions"><button type="button" data-resource-prev ${page===1?'disabled':''}>Anterior</button><button type="button" data-resource-next ${!response.has_more?'disabled':''}>Próxima</button></div>`;
        result.querySelector('[data-resource-prev]').onclick=()=>{page--;load()};result.querySelector('[data-resource-next]').onclick=()=>{page++;load()};
      }catch(_){if(host.isConnected&&current===generation)result.innerHTML='<p role="alert">Não foi possível consultar a cobertura. Nenhum valor foi estimado. Verifique schema e armazenamento.</p>'}
    }
    form.onsubmit=event=>{event.preventDefault();page=1;load()};
    controllers.push({area,load});
    if(area==='overview')load();
  }
  host.addEventListener('of-tab-selected',event=>controllers.find(c=>c.area===event.detail)?.load());
  const panel=host.querySelector('#of-panel-connections'),manual=document.createElement('section');manual.className='panel';
  manual.innerHTML=`<h2>Leitura manual de todos os produtos em cache</h2><p>Não atualiza Item, saldo em tempo real, consentimento ou instituição. Não promove dados a lançamentos oficiais. A primeira consulta pode emitir uma chave temporária com a configuração privada existente.</p>${catalog.connections.filter(c=>c.enabled&&!c.historical).map(c=>`<button type="button" data-coverage-sync="${esc(c.id)}">Consultar cache: ${esc(c.institution)}</button>`).join('')}<p role="status" data-coverage-progress>Nenhuma coleta iniciada.</p>`;
  panel.append(manual);
  manual.querySelectorAll('[data-coverage-sync]').forEach(button=>button.onclick=async()=>{
    if(!window.confirm('Consultar os produtos já disponíveis no cache Pluggy? Nenhuma atualização bancária será disparada.'))return;
    const buttons=[...manual.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
    const progress=manual.querySelector('[data-coverage-progress]');progress.textContent='Leitura manual em andamento…';
    const poll=setInterval(async()=>{try{const r=await api('/open-finance/coverage');if(manual.isConnected)progress.textContent=`${r.coverage.filter(c=>c.state==='RUNNING').length} coleções em andamento; consulte os estados por recurso.`}catch(_){}},1500);
    try{const r=await api('/open-finance/coverage-sync',{method:'POST',body:{connection_id:button.dataset.coverageSync}});progress.textContent=r.run.state==='SUCCEEDED'?'Coleta concluída. Confira cobertura e permissões de cada produto.':'Coleta terminou com falha. Dados anteriores preservados; confira o histórico.';}
    catch(_){progress.textContent='Coleta não confirmada. Consulte o histórico antes de repetir.'}
    finally{clearInterval(poll);buttons.forEach(b=>b.disabled=false)}
  });
}
