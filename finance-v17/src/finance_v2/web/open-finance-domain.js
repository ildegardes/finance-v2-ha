import {createQueryGeneration} from './query-generation.js';
import {bankMoney,dateBR} from './privacy.js';
import {openFinanceError} from './open-finance-errors.js';
import {activeConnections,connectionLabel,runSummary,consentNotice,collectionDiagnostic} from './open-finance-status.js';

const kinds={accounts:'Contas e saldos',item:'Instituição e conexão',resources:'Recursos declarados',consents:'Consentimentos',transactions:'Movimentações completas',investments:'Posições de investimentos',investment_transactions:'Movimentos de investimentos',loans:'Crédito e obrigações',bills:'Faturas e pagamentos registrados',statements:'Referências de extratos'};
const states={COMPLETE:'Consulta completa',EMPTY:'Consulta completa sem registros',NOT_AUTHORIZED:'Acesso não autorizado',NOT_AVAILABLE:'Recurso não disponível',NOT_COLLECTED:'Ainda não coletado pelo provedor',NOT_QUERIED:'Consulta não realizada',RUNNING:'Leitura em andamento',FAILED:'Leitura falhou',INTERRUPTED:'Leitura interrompida'};
const relations={MATCHED:'Vínculo com fatura comprovado',MISSING_REFERENCE:'Sem vínculo de fatura informado; nenhuma associação inferida',UNRESOLVED:'Referência de fatura ainda não resolvida',HISTORICAL_NOT_ESTABLISHED:'Vínculo histórico não estabelecido'};
const consentStates={NOT_QUERIED:'Consentimento não consultado',ASSOCIATION_INCONSISTENT:'Associação inconsistente; consentimento rejeitado pela guarda de escopo',QUERY_FAILED:'Consulta de consentimentos falhou',NO_CONSENT_OBSERVED:'Nenhum consentimento observado',ASSOCIATION_VALIDATED_IN_LAST_SCAN:'Associação validada na última consulta; não comprova autorização atual',NOT_CURRENTLY_ESTABLISHED:'Associação atual não estabelecida'};

export function temporalHtml(row,esc){
  const t=row.temporal||{},date=value=>value?esc(dateBR(value)):'Não informada';
  const observation=Object.values(t.financial_observation||{}).map(date).join(' · ')||'Não informada';
  return `<dl class="of-temporal-provenance"><dt>Data financeira informada</dt><dd>${observation}</dd><dt>Coleta da revisão</dt><dd>${date(t.collected_at)}</dd><dt>Primeira coleta deste conteúdo</dt><dd>${date(t.content_first_collected_at)}</dd><dt>Última presença observada no staging</dt><dd>${date(t.last_seen_at)}</dd><dt>Ausência observada no staging</dt><dd>${date(t.absence_observed_at)}</dd><dt>Atualização deste registro no provedor</dt><dd>${date(t.provider_updated_at)}</dd><dt>Sincronização atual (contexto separado)</dt><dd>${esc(t.current_sync?.state||'Não consultada')}</dd><dt>Frescor financeiro efetivo</dt><dd>${t.effective_freshness==='STALE'?'Desatualização informada na coleta':'Não estabelecido; coleta recente não comprova data financeira recente'}</dd></dl>`;
}

export function fieldHtml(node,esc){
  if(node.state!=='VALUE')return `<span>${esc({ABSENT:'Campo não fornecido',NULL:'Não informado pelo provedor',UNSUPPORTED:'Formato não suportado'}[node.state]||'Estado não reconhecido')}</span>`;
  if(node.kind==='SECTION')return fieldsHtml(node.children||[],esc);
  if(node.kind==='COLLECTION')return node.items.length?`<ul>${node.items.map(n=>`<li>${fieldHtml(n,esc)}</li>`).join('')}</ul>`:'Nenhum componente informado';
  if(node.kind==='MONEY')return `<span data-private-financial>${esc(bankMoney(node.value,node.currency))}</span>`;
  if(node.kind==='RATE'||node.kind==='QUANTITY')return `<span data-private-financial>${esc(String(node.value).replace('.',','))}${node.kind==='RATE'?' (unidade informada pelo provedor)':''}</span>`;
  if(node.kind==='CIVIL_DATE'||node.kind==='INSTANT')return esc(dateBR(node.value))+(node.kind==='INSTANT'?` <small>Horário e fuso da origem: ${esc(String(node.value).slice(11))}</small>`:'');
  if(node.kind==='BOOLEAN')return node.value?'Sim':'Não';
  return esc(String(node.value));
}
function fieldsHtml(nodes,esc){
  const list=values=>`<dl class="of-resource-fields">${values.map(n=>`<div><dt>${esc(n.label)}</dt><dd>${fieldHtml(n,esc)}</dd></div>`).join('')}</dl>`;
  const absent=nodes.filter(n=>n.state==='ABSENT'),present=nodes.filter(n=>n.state!=='ABSENT');
  return list(present)+(absent.length?`<details class="of-absent-fields"><summary>Campos não fornecidos (${absent.length})</summary>${list(absent)}</details>`:'');
}

export function productSummary(row,esc){
  const choices={CREDIT_CARD:['balance','creditLimit','availableCreditLimit','balanceDueDate','balanceCloseDate','brand','status'],CREDIT_BILL:['totalAmount','totalAmountCurrencyCode','dueDate','billClosingDate','minimumPaymentAmount','status'],INVESTMENT_POSITION:['type','balance','quantity','currencyCode','date','status'],CREDIT_CONTRACT:['type','productName','contractAmount','contractOutstandingBalance','contractRemainingNumber','totalNumberOfInstallments','firstInstallmentDueDate','settlementDate','CET','status']};
  const wanted=choices[row.kind];if(!wanted)return '';
  const found=[];
  function visit(nodes){for(const node of nodes||[]){if(wanted.includes(node.key)&&node.state==='VALUE'&&node.kind!=='SECTION'&&node.kind!=='COLLECTION')found.push(node);if(node.kind==='SECTION')visit(node.children)}}
  visit(row.fields);return found.length?`<dl class="of-product-summary">${found.map(node=>`<div><dt>${esc(node.label)}</dt><dd>${fieldHtml(node,esc)}</dd></div>`).join('')}</dl>`:'<p class="muted">Dados resumidos indisponíveis; consulte os detalhes.</p>';
}

export function mountDomains({host,api,esc,catalog,navigation=null,domainSelections={},onCardFlow=null,onBillFlow=null,analyticsState={}}){
  const active=activeConnections(catalog);
  const areas={overview:'accounts',cards:'accounts',assets:'investments',credit:'loans',connections:'item'},controllers=[];
  for(const [area,initial]of Object.entries(areas)){
    const panel=host.querySelector('#of-panel-'+area);if(!panel)continue;
    if(area==='overview'||area==='assets')panel.replaceChildren();
    const section=document.createElement('section');section.className='panel of-coverage';
    section.innerHTML=`<h2>${esc({overview:'Contas, saldos e cobertura',cards:'Cartões e faturas',assets:'Carteira e movimentações',credit:'Crédito e obrigações',connections:'Diagnóstico de cobertura'}[area])}</h2><p class="of-notice">Staging bancário, separado dos lançamentos oficiais. Cache completo não significa dados atualizados. Ausência, indisponibilidade e zero são distintos. Saldos e investimentos não são somados como patrimônio: moedas e possíveis sobreposições não estão comprovadas.</p><form class="of-resource-filter form-grid"><label>Recurso<select name="resource">${Object.entries(kinds).map(([id,label])=>`<option value="${id}">${label}</option>`).join('')}</select></label><label>Instituição<select name="connection_id"><option value="">Todas</option>${active.map(c=>`<option value="${esc(c.id)}">${esc(connectionLabel(c,active))}</option>`).join('')}</select></label><label>Tipo / classe informado<input name="type" maxlength="64" pattern="[A-Za-z0-9_-]*" placeholder="Ex.: FIXED_INCOME"></label><label>Moeda<input name="currency" maxlength="3" pattern="[A-Z]{3}" placeholder="Ex.: BRL"></label><label><input name="history" type="checkbox"> Histórico de observações (não é rentabilidade calculada)</label><button type="submit">Consultar staging</button></form><div class="of-resource-result" aria-live="polite"></div>`;
    panel.append(section);
    let loadInvestmentSummary=null;
    if(area==='assets'){
      const summary=document.createElement('section');summary.className='of-investment-overview';summary.innerHTML='<p role="status">Resumo de posições não consultado.</p>';section.before(summary);
      const summaryQueries=createQueryGeneration(navigation);
      loadInvestmentSummary=async function(){
        const query=summaryQueries.begin(),currency=form.elements.currency.value||'BRL';
        if(form.elements.type.value||form.elements.history.checked||form.elements.resource.value!=='investments'){
          summary.innerHTML='<p class="of-notice">Resumo consolidado indisponível para este filtro; consulte as posições listadas.</p>';
          return;
        }
        summary.innerHTML='<p role="status">Carregando posições…</p>';
        const params=new URLSearchParams({currency});if(form.elements.connection_id.value)params.set('connection_id',form.elements.connection_id.value);
        try{const data=await api('/open-finance/analytics?'+params,{queryScope:query});if(!query.current()||!host.isConnected)return;
          const positions=data.positions.investments,classes=positions.by_class||[];
          summary.innerHTML=`<div class="of-metric"><span>Investimentos informados · ${esc(currency)}</span><strong ${positions.value===null?'':'data-private-financial'}>${positions.value===null?'Indisponível':esc(bankMoney(positions.value,currency))}</strong><small>${positions.coverage_state==='COMPLETE'?'Cobertura informada como completa':'Cobertura parcial ou não estabelecida'}</small></div><section class="of-summary-card"><h3>Distribuição por classe informada</h3>${classes.length?`<ul class="of-category-list">${classes.map(c=>`<li><span>${esc(c.type)}</span><strong ${c.value===null?'':'data-private-financial'}>${c.value===null?'Indisponível':esc(bankMoney(c.value,currency))}</strong>${c.unavailable?'<small>Dados parciais nesta classe</small>':''}</li>`).join('')}</ul>`:'<p>Distribuição indisponível.</p>'}</section>`;
        }catch(_){if(query.current()&&host.isConnected)summary.innerHTML='<p role="alert">Resumo de investimentos indisponível.</p>'}
      };
      host.addEventListener('of-tab-selected',event=>{if(event.detail==='assets')loadInvestmentSummary()});
    }
    const form=section.querySelector('form'),result=section.querySelector('.of-resource-result');form.elements.resource.value=initial;if(area==='assets')form.elements.currency.value=analyticsState.currency||'BRL';
    if(['cards','assets','credit'].includes(area)){
      const details=document.createElement('details');details.className='of-domain-filters';
      const summary=document.createElement('summary');summary.textContent='Filtros e diagnóstico';
      form.before(details);details.append(summary,form);
    }

    const selected=domainSelections[area];
    form.elements.connection_id.value=active.some(c=>c.id===selected)?selected:'';
    domainSelections[area]=form.elements.connection_id.value;
    let page=1,generation=0,parent=null,parentConnection=null;const queries=createQueryGeneration(navigation);
    async function load(){
      const query=queries.begin(),mine=++generation;result.setAttribute('aria-busy','true');result.innerHTML='<p role="status" data-query-loading>Consultando dados importados…</p>';
      const q=new URLSearchParams({resource:form.elements.resource.value,page:String(page),page_size:'25'});
      for(const key of ['connection_id','type','currency'])if(form.elements[key].value)q.set(key,form.elements[key].value);
      if(form.elements.history.checked)q.set('history','1');
      if(parent){q.set('parent_id',parent);q.set('connection_id',parentConnection);}
      if(area==='cards'&&q.get('resource')==='accounts')q.set('type','CREDIT');
      try{
        const response=await api('/open-finance/domain?'+q,{queryScope:query});
        if(!query.current()||!host.isConnected||mine!==generation)return;
        const diagnostics=(response.checkpoints||[]).map(c=>`${collectionDiagnostic(c,response.consent_diagnostics||[],states[c.state]||'Estado não reconhecido')} · ${c.record_count} registros · ${c.page_count} páginas${c.error_code&&c.error_code!=='ITEM_ID_DIFFERENT'?' · '+openFinanceError(c.error_code):c.error_code==='ITEM_ID_DIFFERENT'&&!(c.resource==='consents'&&response.consent_diagnostics?.some(d=>d.connection_id===c.connection_id&&d.access_mode==='meupluggy_personal'))?' · '+openFinanceError(c.error_code):''}`).join(' | ');
        const consent=(response.consent_diagnostics||[]).map(c=>consentNotice(c,consentStates[c.state]||'Associação não estabelecida')).join(' | ');
        result.innerHTML=`<p>${esc(diagnostics||states.NOT_QUERIED)} · Página ${page} · ${response.total} registros preservados</p>${consent?`<p class="of-notice">${esc(consent)}</p>`:''}${parent?'<button type="button" data-domain-back>Remover filtro do produto</button>':''}${response.items.length?response.items.map((row,index)=>`${['cards','assets','credit'].includes(area)&&(index===0||response.items[index-1].identity.connection_id!==row.identity.connection_id)?`<h3 class="of-institution-group">${esc(catalog.connections.find(c=>c.id===row.identity.connection_id)?.institution||'Instituição histórica')}</h3>`:''}<article class="of-resource-card" data-domain-kind="${esc(row.kind)}"><h3>${esc(row.name)}</h3><p>${esc(catalog.connections.find(c=>c.id===row.identity.connection_id)?.institution||'Instituição histórica')} · ${row.record_state==='NOT_SEEN'?'Não observado na última consulta completa; não significa exclusão':'Registro preservado'}</p><p>${esc(row.freshness.state==='STALE'?'Desatualização informada na coleta de origem deste conteúdo':'Frescor financeiro não estabelecido')}${row.freshness.provider_execution_partial?' · Execução parcial no provedor na coleta de origem deste conteúdo':''} · ${row.freshness.warning_count||0} avisos de qualidade</p>${relations[row.relation.state]?`<p>${esc(relations[row.relation.state])}</p>`:''}${productSummary(row,esc)}<details class="of-resource-details"><summary>Detalhes do produto</summary>${fieldsHtml(row.fields,esc)}</details><div class="actions">${row.kind==='CREDIT_CARD'&&onCardFlow?`<button type="button" data-card-flow="${index}">Ver movimentações do cartão</button>`:''}${row.kind==='CREDIT_BILL'&&onBillFlow&&!form.elements.history.checked&&row.record_state==='PRESENT'?`<button type="button" data-bill-flow="${index}">Ver transações vinculadas</button>`:''}${row.children.map(child=>`<button type="button" data-domain-child="${child}" data-row="${index}">Ver ${esc(kinds[child])}</button>`).join('')}</div>${response.resource==='statements'?'<p>Somente metadados; download de documento não habilitado.</p>':''}<details><summary>Proveniência</summary><p>Fonte: staging externo. ${temporalHtml(row,esc)} Histórico de revisões não representa evolução patrimonial nem rentabilidade calculada. Nenhum lançamento oficial foi criado.</p></details></article>`).join(''):`<p class="empty">${response.checkpoints?.some(c=>c.state==='EMPTY')?'Consulta concluída sem registros neste escopo.':'Nenhum registro preservado neste escopo; isso não comprova ausência do produto. Confira o estado da consulta.'}</p>`}<div class="actions"><button type="button" data-resource-prev ${page===1?'disabled':''}>Anterior</button><button type="button" data-resource-next ${!response.has_more?'disabled':''}>Próxima</button></div>`;
        result.querySelector('[data-resource-prev]').onclick=()=>{page--;load()};result.querySelector('[data-resource-next]').onclick=()=>{page++;load()};
        result.querySelector('[data-domain-back]')?.addEventListener('click',()=>{parent=null;page=1;load()});
        result.querySelectorAll('[data-card-flow]').forEach(button=>button.onclick=()=>onCardFlow(response.items[Number(button.dataset.cardFlow)].identity));
        result.querySelectorAll('[data-bill-flow]').forEach(button=>button.onclick=()=>onBillFlow(response.items[Number(button.dataset.billFlow)].identity));
        result.querySelectorAll('[data-domain-child]').forEach(button=>button.onclick=()=>{const row=response.items[Number(button.dataset.row)];parent=row.identity.external_id;parentConnection=row.identity.connection_id;form.elements.connection_id.value=active.some(c=>c.id===parentConnection)?parentConnection:'';form.elements.resource.value=button.dataset.domainChild;form.elements.type.value='';form.elements.currency.value='';page=1;load()});
      }catch(_){if(query.current()&&host.isConnected&&mine===generation)result.innerHTML='<p role="alert">Não foi possível consultar a cobertura. Nenhum valor foi estimado. Verifique schema e armazenamento.</p>'}finally{if(query.current()&&mine===generation){result.removeAttribute('aria-busy');result.querySelector('[data-query-loading]')?.remove()}}
    }
    form.elements.connection_id.onchange=()=>{domainSelections[area]=form.elements.connection_id.value;parent=null;parentConnection=null;page=1};
    form.onsubmit=e=>{e.preventDefault();parent=null;page=1;load();if(loadInvestmentSummary)loadInvestmentSummary()};controllers.push({area,load});
  }
  host.addEventListener('of-tab-selected',event=>controllers.find(c=>c.area===event.detail)?.load());
  const connections=host.querySelector('#of-panel-connections');
  const actions=document.createElement('section');actions.className='panel';
  actions.innerHTML=`<h2>Reconciliação e retomada</h2><p>Incremental reaplica o cache completo com upsert apenas das alterações. Retomada recomeça as coleções com segurança, sem reutilizar cursor antigo. Não atualiza o Item nem promove dados oficiais.</p>${active.map(c=>`<fieldset><legend>${esc(c.institution)}</legend>${['INCREMENTAL','RESUME'].map(mode=>`<button type="button" data-domain-sync="${mode}" data-connection="${esc(c.id)}">${mode==='RESUME'?'Retomar':'Reconciliar alterações'}</button>`).join('')}</fieldset>`).join('')}<p role="status" data-domain-sync-status>Nenhuma reconciliação iniciada.</p>`;
  connections?.append(actions);
  actions.querySelectorAll('[data-domain-sync]').forEach(button=>button.onclick=async()=>{
    if(!window.confirm('Consultar o cache Pluggy e atualizar somente o staging desta instituição?'))return;
    const buttons=[...actions.querySelectorAll('button')],status=actions.querySelector('[data-domain-sync-status]');buttons.forEach(b=>b.disabled=true);status.textContent='Reconciliação em andamento…';
    try{const response=await api('/open-finance/domain-sync',{method:'POST',body:{connection_id:button.dataset.connection,mode:button.dataset.domainSync}});if(navigation&&!navigation.current())return;status.textContent=runSummary(response.run,response.run.state==='SUCCEEDED'?'Reconciliação concluída; confira a qualidade de cada coleção.':openFinanceError(response.run.error_code))}
    catch(error){if(!navigation||navigation.current())status.textContent=openFinanceError(error.code)}
    finally{if(!navigation||navigation.current())buttons.forEach(b=>b.disabled=false)}
  });
}
