import {bankMoney,dateBR,privacyMode} from './privacy.js';
import {categoryLabel,countBR,institutionName} from './open-finance-labels.js';
import {createQueryGeneration} from './query-generation.js';

const endpoint='/open-finance/classification/';
export const natureNames={
  INCOME:'Receita pessoal ou operacional',EXPENSE:'Despesa',SALARY:'Salário',INVESTMENT_INCOME:'Receita de investimento',
  APPLICATION:'Aplicação financeira',REDEMPTION:'Resgate financeiro',CAPITAL_RETURN:'Restituição de capital',
  INVESTMENT_SETTLEMENT:'Liquidação de operação de investimento',OWN_TRANSFER:'Transferência entre contas próprias',
  SETTLEMENT:'Liquidação de obrigação',CARD_PAYMENT:'Pagamento de fatura',BORROWING:'Crédito recebido',
  DEBT_PRINCIPAL:'Amortização de dívida',CHARGE:'Juros e encargos',TAX:'Tributo',REVERSAL:'Estorno',
  INTERNAL:'Movimentação interna',UNKNOWN:'Natureza não estabelecida',
};
export const originNames={MANUAL:'Manual',CUSTOM:'Regra personalizada',NATIVE:'Regra nativa',PROVIDER:'Provedor',UNCLASSIFIED:'Sem classificação'};
export const reviewNames={CONFIRMED:'Confirmada',SUGGESTED:'Sugerida',CONFLICT:'Em conflito',UNCLASSIFIED:'A revisar'};
const directionNames={incoming:'Entrada',outgoing:'Saída',unknown:'Direção não estabelecida'};
const batchNames={apply:'Alteráveis',manual:'Decisões manuais protegidas',conflict:'Conflitos',unchanged:'Já classificadas'};
const actionNames={MANUAL:'Classificação manual',BATCH:'Aplicação em lote',UNDO:'Reversão'};
const matchNames={exact:'Texto normalizado igual',original:'Texto original igual',contains:'Contém expressão',prefix:'Começa com',terms:'Todos os termos'};
export const proventNames={dividend:'Dividendos',interest_equity:'Juros sobre capital próprio',distribution:'Rendimentos',
  fund_distribution:'Rendimentos de FIIs',fixed_income:'Rendimentos de renda fixa',automatic:'Aplicação automática',other:'Outros proventos'};

const message=error=>({
  CLASSIFICATION_STALE:'Os dados mudaram. Atualize a consulta e simule outra vez.',
  CLASSIFICATION_SCOPE_REQUIRED:'Informe uma conexão e uma condição de descrição.',
  CLASSIFICATION_SCOPE_UNAVAILABLE:'A conexão está fora do escopo selecionado.',
  CLASSIFICATION_LIMIT:'A operação excedeu o limite. Reduza o intervalo ou revise as regras.',
  CLASSIFICATION_INVALID:'Revise os campos informados.',
  CLASSIFICATION_CONFIRMATION_REQUIRED:'Confirme explicitamente a operação.',
  FORBIDDEN:'Entre com uma sessão do proprietário.',
})[error?.code]||'Não foi possível concluir a operação. Tente novamente.';

export function classificationDetail(row,esc){
  const value=row.classification;
  if(!value)return '';
  const original=row.original_category;
  return '<dl class="of-class-fields"><div><dt>Categoria original</dt><dd>'+esc(original?.name||'Sem categoria')+'</dd></div>'+
    '<div><dt>Natureza</dt><dd>'+esc(natureNames[value.nature])+'</dd></div>'+
    '<div><dt>Origem</dt><dd>'+esc(originNames[value.origin])+'</dd></div>'+
    '<div><dt>Revisão</dt><dd>'+esc(reviewNames[value.review])+'</dd></div>'+
    (value.rule_id?'<div><dt>Regra e condição</dt><dd>'+esc(value.rule_id)+' · revisão '+esc(value.rule_revision)+' · '+esc(value.condition||'')+'</dd></div>':'')+
    (value.conflicts?.length?'<div><dt>Regras em conflito</dt><dd>'+esc(value.conflicts.join(', '))+'</dd></div>':'')+
    (value.note?'<div><dt>Evidência</dt><dd>'+esc(value.note)+'</dd></div>':'')+'</dl>';
}

function financial(value,currency,esc){
  if(value==null)return 'Indisponível';
  if(privacyMode()!=='visible')return '<span aria-label="Valor oculto">••••••</span>';
  return '<span data-private-financial data-private-mask="neutral">'+esc(bankMoney(value,currency))+'</span>';
}

export function mountClassification({host,panel,api,esc,catalog,navigation,getScope,reload}){
  const section=document.createElement('section');
  section.hidden=true;
  section.className='panel of-class-center';
  section.innerHTML='<h3>Classificação financeira</h3><div class="actions"><button type="button" class="quiet" data-rules>Gerenciar regras</button><button type="button" class="quiet" data-audit>Auditoria e reversão</button></div><div data-class-status aria-live="polite"></div><div data-class-groups></div><div data-class-management></div>';
  panel.querySelector('[data-flow-result]').before(section);
  const status=section.querySelector('[data-class-status]');
  const groupPanel=section.querySelector('[data-class-groups]');
  const manager=section.querySelector('[data-class-management]');
  const queries=createQueryGeneration(navigation);
  let catalogPromise=null,editor=null,lastCenter=null,pending=false;
  const opt=(value,text)=>'<option value="'+esc(value)+'">'+esc(text)+'</option>';
  const choices=(options)=>Object.entries(options).map(([key,label])=>opt(key,label)).join('');
  const post=(path,body)=>api(endpoint+path,{method:'POST',body});
  const report=(text,error=false)=>{status.innerHTML='<p role="'+(error?'alert':'status')+'">'+esc(text)+'</p>'};
  function getCatalog(){
    if(!catalogPromise)catalogPromise=api(endpoint+'catalog').catch(error=>{catalogPromise=null;throw error});
    return catalogPromise;
  }
  function closeEditor(){
    if(editor?.open)editor.close();
  }
  function dialog(title,content){
    closeEditor();
    const box=document.createElement('dialog');
    box.className='of-class-dialog';
    box.setAttribute('aria-labelledby','of-class-dialog-title');
    box.innerHTML='<h3 id="of-class-dialog-title">'+esc(title)+'</h3>'+content+'<div data-editor-message aria-live="polite"></div>';
    host.append(box);
    box.addEventListener('close',()=>box.remove(),{once:true});
    editor=box;
    box.showModal();
    box.querySelector('[data-close-editor]')?.addEventListener('click',()=>box.close());
    return box;
  }
  function outcomeFields(result={},extra=false){
    const names=[...new Set([...((catalog.finance_categories)||[]),'Pagamento de fatura','Aplicação financeira','Salário','Rendimentos de investimentos'])];
    return '<label>Categoria Finance V17<input required maxlength="120" list="of-finance-categories" name="category" value="'+esc(result.category||'')+'"></label>'+
      '<datalist id="of-finance-categories">'+names.map(name=>opt(name,name)).join('')+'</datalist>'+
      '<label>Natureza financeira<select name="nature">'+choices(natureNames)+'</select></label>'+
      '<details class="of-class-options"><summary>Mais detalhes da classificação</summary><div class="form-grid">'+
      '<label>Subcategoria<input name="subcategory" maxlength="80" value="'+esc(result.subcategory||'')+'"></label>'+
      '<label>Produto de investimento<input name="investment" maxlength="80" value="'+esc(result.investment||'')+'"></label>'+
      '<label>Tipo de provento<select name="provent">'+opt('','Não informado')+choices(proventNames)+'</select></label>'+
      '<label>Código de ativo<input name="asset" maxlength="6" value="'+esc(result.asset||'')+'" placeholder="Ex.: ABCD3"></label>'+
      '<label>Observação<input name="note" maxlength="256" value="'+esc(result.note||'')+'"></label>'+
      '<label class="of-history-choice"><input type="checkbox" name="principal_only" '+(result.principal_only?'checked':'')+'> Confirmo que este resgate contém somente principal</label>'+
      (extra?'<label>Revisão<select name="review">'+opt('CONFIRMED','Confirmada')+opt('SUGGESTED','Sugerida')+'</select></label>':'')+'</div></details>';
  }
  function outcome(form){
    const result={category:form.elements.category.value,nature:form.elements.nature.value};
    for(const name of ['subcategory','investment','provent','asset','note','review']){
      if(form.elements[name]?.value)result[name]=form.elements[name].value;
    }
    if(result.nature==='REDEMPTION'&&form.elements.principal_only.checked)result.principal_only=true;
    return result;
  }
  function setOutcome(form,result){
    form.elements.nature.value=result?.nature||'UNKNOWN';
    form.elements.provent.value=result?.provent||'';
    if(form.elements.review)form.elements.review.value=result?.review==='SUGGESTED'?'SUGGESTED':'CONFIRMED';
    const adapt=()=>{
      form.elements.provent.disabled=form.elements.nature.value!=='INVESTMENT_INCOME';
      if(form.elements.provent.disabled)form.elements.provent.value='';
      form.elements.principal_only.disabled=form.elements.nature.value!=='REDEMPTION';
    };
    form.elements.nature.onchange=adapt;
    adapt();
  }
  function dialogSubmit(box,form,handler){
    form.onsubmit=async event=>{
      event.preventDefault();
      if(pending)return;
      pending=true;
      const button=form.querySelector('button[type=submit]');
      if(button)button.disabled=true;
      const progress=box.querySelector('[data-editor-message]');
      progress.textContent='Processando…';
      try {await handler();}
      catch(error){
        progress.innerHTML='<p role="alert">'+esc(message(error))+'</p>';
      } finally {
        if(button)button.disabled=false;
        pending=false;
      }
    };
  }
  function edit(row){
    const actual=row.classification||{};
    const title='Classificar movimentação';
    const box=dialog(title,'<p><strong>'+esc(row.description_original||row.description||'Descrição indisponível')+'</strong></p>'+
      '<p>'+esc(institutionName(row.institution))+' · '+esc(row.account_name||'Conta')+' · '+esc(dateBR(row.date))+
      ' · '+esc(directionNames[row.direction]||'Direção não estabelecida')+' · '+financial(row.amount,row.currency,esc)+'</p>'+
      classificationDetail(row,esc)+'<form class="form-grid">'+outcomeFields({...actual,category:actual.category||categoryLabel(row.category)})+
      '<div class="actions"><button type="submit">Salvar nesta movimentação</button><button type="button" class="quiet" data-rule-from-row>Criar regra</button><button type="button" data-close-editor class="quiet">Cancelar</button></div></form>');
    const form=box.querySelector('form');
    setOutcome(form,actual);
    form.querySelector('[data-rule-from-row]').onclick=()=>{
      if(!form.reportValidity())return;
      ruleEditor(null,row,outcome(form));
    };
    dialogSubmit(box,form,async()=>{
      await post('manual',{identity:{connection_id:row.connection_id,account_id:row.account_id,transaction_id:row.external_id},
        event:actual.event??null,decision:outcome(form)});
      box.close();report('Classificação individual salva.');reload();
    });
  }
  function ruleEditor(rule,row,result=rule?.result||{}){
    const source=rule?.conditions||{};
    const defaultConnection=source.connection_id||row?.connection_id||getScope().connection_id||'';
    const connections=catalog.connections.filter(item=>item.enabled&&!item.historical||item.id===defaultConnection);
    const markup='<form class="form-grid"><label>Nome da regra<input name="name" required maxlength="120" value="'+esc(rule?.name||result.category||'')+'"></label>'+
      '<label>Descrição da regra<input name="explanation" maxlength="400" value="'+esc(rule?.description||'')+'"></label>'+
      '<label>Instituição / conexão<select name="connection_id" required>'+opt('','Selecione')+connections.map(item=>opt(item.id,institutionName(item.institution))).join('')+'</select></label>'+
      '<label>Conta<select name="account_id"></select></label>'+
      '<label>Movimentos de<select name="product">'+opt('BANK','Contas')+opt('CREDIT','Cartões')+'</select></label>'+
      '<label>Direção<select name="direction">'+opt('','Todas')+choices(directionNames)+'</select></label>'+
      '<label>Moeda<input name="currency" maxlength="3" pattern="[A-Z]{3}" value="'+esc(source.currency||row?.currency||getScope().currency||'BRL')+'"></label>'+
      '<label>Correspondência<select name="match">'+choices(matchNames)+'</select></label>'+
      '<label>Descrição a comparar<input name="description" required maxlength="600" value="'+esc(source.description||row?.description_original||row?.description||'')+'"></label>'+
      '<label>Prioridade<input name="priority" type="number" min="0" max="999" required value="'+esc(rule?.priority??100)+'"></label>'+
      '<details class="of-class-options"><summary>Condições adicionais</summary><div class="form-grid">'+
      '<label>Categoria original<select name="original_category">'+opt('','Todas')+opt('missing','Sem categoria')+
      catalog.categories.filter(item=>item.external_id).map(item=>opt('pluggy:'+item.external_id,item.display_name_pt||item.original_name||'Categoria não identificada')).join('')+'</select></label>'+
      '<label>Tipo de operação informado<input name="operation" maxlength="150" value="'+esc(source.operation||'')+'"></label></div></details>'+
      outcomeFields(result,true)+
      '<label class="of-history-choice"><input name="enabled" type="checkbox" '+(rule?.enabled!==false?'checked':'')+'> Regra ativa</label>'+
      '<label>Aplicação<select name="scope" aria-label="Aplicação">'+opt('future','Movimentações futuras')+opt('history','Somente histórico após simulação')+opt('both','Histórico após simulação e movimentações futuras')+'</select></label>'+
      '<div class="actions"><button type="submit">Salvar regra</button><button type="button" data-close-editor class="quiet">Cancelar</button></div></form>';
    const box=dialog(rule?'Editar regra':'Criar regra',markup),form=box.querySelector('form');
    form.elements.connection_id.value=defaultConnection;
    function accountOptions(){
      const id=form.elements.connection_id.value;
      form.elements.account_id.innerHTML=opt('','Todas as contas')+catalog.accounts.filter(account=>account.connection_id===id).map(account=>opt(account.external_id,account.name||'Conta')).join('');
    }
    form.elements.connection_id.onchange=accountOptions;
    accountOptions();
    form.elements.account_id.value=source.account_id||row?.account_id||'';
    form.elements.product.value=source.product||row?.product||'BANK';
    form.elements.match.value=source.match||'exact';
    form.elements.original_category.value=source.category||'';
    form.elements.direction.value=source.direction||row?.direction||'';
    form.elements.scope.value=rule?.prospective===false?'history':'future';
    setOutcome(form,result);
    dialogSubmit(box,form,async()=>{
      const entry=new FormData(form);
      const conditions={connection_id:entry.get('connection_id'),description:entry.get('description'),match:entry.get('match')};
      for(const name of ['account_id','product','direction','currency','operation']){
        if(entry.get(name))conditions[name]=entry.get(name);
      }
      if(entry.get('original_category'))conditions.category=entry.get('original_category');
      const scope=entry.get('scope'),definition={name:entry.get('name'),description:entry.get('explanation'),
        priority:Number(entry.get('priority')),enabled:form.elements.enabled.checked,prospective:scope!=='history',
        conditions,result:outcome(form)};
      const saved=await post('rule',{...(rule?{id:rule.id}:{}),revision:rule?.revision||0,rule:definition,
        history:getScope().history==='1'});
      catalogPromise=null;
      box.close();report('Regra salva.');
      if(scope!=='future'&&definition.enabled)previewEditor({...definition,...saved});
      else if(!section.hidden)showRules();
    });
  }
  function previewEditor(rule){
    const scope=getScope();
    const box=dialog('Simular aplicação no histórico','<p>'+esc(rule.name)+' · '+esc(institutionName(
      catalog.connections.find(item=>item.id===rule.conditions.connection_id)?.institution
    ))+'</p><form class="form-grid"><label>De<input type="date" name="start" required value="'+esc(scope.start)+'"></label>'+
      '<label>Até<input type="date" name="end" required value="'+esc(scope.end)+'"></label>'+
      '<label>Moeda<input name="currency" pattern="[A-Z]{3}" maxlength="3" required value="'+esc(rule.conditions.currency||scope.currency||'BRL')+'"></label>'+
      '<label class="of-history-choice"><input name="history" type="checkbox" '+(scope.history==='1'?'checked':'')+'> Incluir conexão histórica neste escopo</label>'+
      '<div class="actions"><button type="submit">Simular</button><button type="button" data-close-editor class="quiet">Fechar</button></div></form><div data-preview></div>');
    const form=box.querySelector('form'),target=box.querySelector('[data-preview]');
    let inputRevision=0;
    form.oninput=()=>{inputRevision++;target.replaceChildren();};
    dialogSubmit(box,form,async()=>{
      const before=inputRevision;
      target.replaceChildren();
      const body={id:rule.id,revision:rule.revision,scope:{
        start:form.elements.start.value,end:form.elements.end.value,currency:form.elements.currency.value,history:form.elements.history.checked,
      }};
      const response=await post('preview',body);
      if(!box.open)return;
      box.querySelector('[data-editor-message]').textContent='';
      if(before!==inputRevision)return;
      target.innerHTML='<h4>Resultado da simulação</h4><p>'+esc(institutionName(response.institution))+' · '+esc(dateBR(response.scope.start))+' a '+
        esc(dateBR(response.scope.end))+' · '+esc(response.scope.currency)+'</p><p><strong>'+esc(countBR.format(response.counts.matched||0))+
        '</strong> movimentações correspondentes. Categoria proposta: '+esc(response.target.category)+' · '+esc(natureNames[response.target.nature])+'</p>'+
        '<ul>'+Object.entries(batchNames).map(([name,label])=>'<li>'+label+' · '+esc(countBR.format(response.counts[name]||0))+'</li>').join('')+'</ul>'+
        '<details><summary>Categorias e naturezas atuais</summary><ul>'+Object.entries(response.categories).map(([name,count])=>'<li>'+esc(name)+' · '+esc(countBR.format(count))+'</li>').join('')+
        Object.entries(response.natures).map(([name,count])=>'<li>'+esc(natureNames[name])+' · '+esc(countBR.format(count))+'</li>').join('')+'</ul></details>'+
        '<details><summary>Amostra de movimentações</summary><ul>'+response.sample.map(row=>'<li>'+esc(dateBR(row.date))+' · '+esc(row.description)+' · '+esc(batchNames[row.state])+'</li>').join('')+
        '</ul></details><form><label class="of-history-choice"><input type="checkbox" required> Confirmo a classificação das movimentações alteráveis no intervalo acima</label>'+
        '<button type="submit" '+(!response.counts.apply?'disabled':'')+'>Aplicar ao histórico</button></form>';
      dialogSubmit(box,target.querySelector('form'),async()=>{
        const result=await post('apply',{...body,digest:response.digest,confirmed:true});
        box.close();report(result.replayed?'Esta operação já foi concluída.':countBR.format(result.applied)+' movimentações classificadas.');reload();
      });
    });
  }
  async function showRules(){
    const query=queries.begin();
    manager.innerHTML='<p role="status">Carregando regras…</p>';
    try{
      const rules=await getCatalog();
      if(!query.current()||section.hidden)return;
      Object.assign(catalog,{finance_categories:rules.finance_categories||[]});
      const nativeRules=rules.native.map(rule=>'<li><span>'+esc(rule.result.category)+' · '+esc(rule.bank)+'</span><button type="button" class="quiet" data-native-rule="'+esc(rule.id)+'">'+(rule.enabled?'Desativar':'Ativar')+'</button></li>').join('');
      const customRules=rules.rules.map(rule=>'<li><div><strong>'+esc(rule.name)+'</strong><br><small>'+esc(matchNames[rule.conditions.match])+' · '+esc(rule.conditions.description)+' · prioridade '+esc(rule.priority)+' · '+(rule.enabled?'Ativa':'Inativa')+'</small></div>'+
        '<div class="actions"><button type="button" class="quiet" data-edit-rule="'+esc(rule.id)+'">Editar</button>'+
        (rule.enabled?'<button type="button" class="quiet" data-simulate-rule="'+esc(rule.id)+'">Simular histórico</button>':'')+'</div></li>').join('');
      manager.innerHTML='<h4>Regras personalizadas</h4><button type="button" data-new-rule>Criar regra</button>'+
        (customRules?'<ul class="of-category-list">'+customRules+'</ul>':'<p>Nenhuma regra personalizada.</p>')+
        '<details><summary>Regras nativas</summary><ul class="of-category-list">'+nativeRules+'</ul></details>';
      manager.onclick=async event=>{
        const button=event.target.closest('button');
        if(!button)return;
        const custom=rules.rules.find(rule=>[button.dataset.editRule,button.dataset.simulateRule].includes(rule.id));
        if(button.matches('[data-new-rule]'))ruleEditor();
        if(button.dataset.editRule)ruleEditor(custom);
        if(button.dataset.simulateRule)previewEditor(custom);
        if(button.dataset.nativeRule){
          const rule=rules.native.find(item=>item.id===button.dataset.nativeRule);
          if(!window.confirm((rule.enabled?'Desativar':'Ativar')+' a regra '+rule.result.category+'?'))return;
          button.disabled=true;
          try{
            await post('rule',{id:'native:'+rule.id,revision:rule.switch_revision,rule:{enabled:!rule.enabled}});
            catalogPromise=null;report('Preferência da regra nativa atualizada.');reload();showRules();
          }catch(error){report(message(error),true);button.disabled=false;}
        }
      };
    }catch(error){if(query.current())manager.innerHTML='<p role="alert">'+esc(message(error))+'</p>';}
  }
  async function showAudit(before){
    const query=queries.begin();
    manager.innerHTML='<p role="status">Carregando auditoria…</p>';
    try{
      const data=await api(endpoint+'audit'+(before?'?before='+before:''));
      if(!query.current()||section.hidden)return;
      const batches=data.batches.map(batch=>'<li><span>'+esc(dateBR(batch.created_at))+' · '+esc(dateBR(batch.scope.start))+' a '+esc(dateBR(batch.scope.end))+
        ' · '+esc(batch.scope.currency)+'</span><button type="button" class="quiet" data-reverse-batch="'+esc(batch.id)+'">Reverter lote</button></li>').join('');
      const events=data.events.map(event=>'<li><strong>'+esc(actionNames[event.action])+'</strong> · '+esc(dateBR(event.recorded_at))+' · '+esc(institutionName(catalog.connections.find(item=>item.id===event.connection_id)?.institution))+
        ' · Proprietário<small>'+esc(event.previous?.category||'Classificação automática / original')+' → '+esc(event.decision?.category||'Classificação automática / original')+'</small></li>').join('');
      const revisions=data.rules.map(rule=>'<li>'+esc(rule.definition.name||rule.definition.native_id)+' · revisão '+esc(rule.revision)+' · '+esc(dateBR(rule.recorded_at))+'</li>').join('');
      manager.innerHTML='<h4>Auditoria e reversão</h4><details open><summary>Operações em lote</summary>'+(batches?'<ul class="of-category-list">'+batches+'</ul>':'<p>Nenhum lote registrado.</p>')+
        '</details><details><summary>Histórico das decisões</summary><ul class="of-category-list">'+events+'</ul>'+(data.before?'<button type="button" class="quiet" data-more-audit>Ver registros anteriores</button>':'')+
        '</details><details><summary>Revisões de regras</summary><ul class="of-category-list">'+revisions+'</ul></details>';
      manager.onclick=async event=>{
        const button=event.target.closest('button');
        if(button?.matches('[data-more-audit]'))showAudit(data.before);
        if(!button?.dataset.reverseBatch||!window.confirm('Reverter as classificações deste lote que não foram alteradas depois?'))return;
        button.disabled=true;
        try{
          const result=await post('undo',{id:button.dataset.reverseBatch,confirmed:true});
          report(countBR.format(result.restored||0)+' classificações restauradas · '+countBR.format(result.conflicts||0)+' conflitos preservados.');
          reload();showAudit();
        }catch(error){report(message(error),true);button.disabled=false;}
      };
    }catch(error){if(query.current())manager.innerHTML='<p role="alert">'+esc(message(error))+'</p>';}
  }
  function present(data){
    if(section.hidden||!data)return;
    lastCenter=data;
    const counts=data.counts||{},total=counts.total||0,classified=counts.classified||0;
    groupPanel.innerHTML='<p class="of-class-totals">'+esc(countBR.format(total))+' movimentações · '+esc(countBR.format(classified))+' classificadas · '+
      esc(countBR.format(counts.manual||0))+' manuais · '+esc(countBR.format((counts.native||0)+(counts.custom||0)))+' por regras · '+
      esc(countBR.format(total-classified))+' a revisar · '+esc(countBR.format(counts.conflict||0))+' em conflito</p>'+
      '<p>'+esc(countBR.format(data.group_count))+' grupos a revisar · Cobertura da classificação '+(total?esc(new Intl.NumberFormat('pt-BR',{style:'percent',maximumFractionDigits:1}).format(classified/total)):'indisponível')+'</p>'+
      (data.groups.length?'<ul class="of-category-list">'+data.groups.map((group,index)=>'<li><div><strong>'+esc(group.label)+'</strong><small>'+esc(institutionName(group.institution))+
        ' · '+esc(directionNames[group.direction]||'')+' · '+esc(dateBR(group.start))+' a '+esc(dateBR(group.end))+' · '+esc(countBR.format(group.count))+' ocorrências'+
        (group.suggestion?' · '+esc(group.suggestion):'')+'</small></div><button type="button" class="quiet" data-group-id="'+index+'">Revisar padrão</button></li>').join('')+'</ul>':'<p class="empty">Nenhum grupo a revisar neste recorte.</p>');
    groupPanel.onclick=event=>{
      const button=event.target.closest('[data-group-id]');
      if(button)edit(lastCenter.groups[Number(button.dataset.groupId)].sample);
    };
  }
  function toggle(force=false){
    section.hidden=!(force||section.hidden);
    if(!section.hidden){
      section.querySelector('[data-rules]').focus();
      reload();
      getCatalog().then(rules=>Object.assign(catalog,{finance_categories:rules.finance_categories||[]})).catch(()=>{});
    }else queries.cancel();
  }
  section.querySelector('[data-rules]').onclick=showRules;
  section.querySelector('[data-audit]').onclick=()=>showAudit();
  host.addEventListener('of-tab-selected',event=>{if(event.detail!=='flow'){queries.cancel();closeEditor();}});
  return {edit,present,toggle,open:()=>!section.hidden,loading:()=>{if(!section.hidden)groupPanel.innerHTML='<p role="status">Consultando grupos…</p>';}};
}
