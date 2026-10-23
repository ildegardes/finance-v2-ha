// Imported bank staging only. No provider calls or official financial writes.
export function createOpenFinance({api,view,heading,esc}) {
  const directionLabels={CREDIT:'Entrada',DEBIT:'Saída',UNKNOWN:'Desconhecida',CONFLICT:'Conflito'};
  const runLabels={SUCCEEDED:'Concluída',FAILED:'Falhou',INTERRUPTED:'Interrompida',RUNNING:'Em andamento'};
  const reasonLabels={DECLARED_PROVIDER_TYPE:'Tipo declarado pelo provedor',ZERO_UNCLASSIFIED:'Valor zero: direção não atribuída',TYPE_PRESENCE_UNRECOVERABLE:'Tipo ausente/nulo não distinguível',TYPE_UNKNOWN_VALUE:'Tipo não reconhecido',ACCOUNT_PRODUCT_CONFLICT:'Produto da conta incompatível',PRODUCT_NOT_COVERED:'Produto não abrangido',PRODUCT_CONTEXT_MISSING:'Produto da conta indisponível',ACCOUNT_IDENTITY_UNESTABLISHED:'Identidade da conta não comprovada',VALUE_UNSUPPORTED:'Representação de valor não abrangida',MONETARY_CONTEXT_MISSING:'Contexto monetário indisponível'};
  const option=(value,label)=>`<option value="${esc(value)}">${esc(label)}</option>`;
  let saved={},page=1;
  return async function openFinance() {
    heading('Open Finance','Dados bancários importados — não são despesas ou receitas oficiais.');
    const host=document.createElement('section');host.className='of-screen';view.append(host);
    host.innerHTML='<p role="status">Carregando conexões bancárias…</p>';
    let catalog;
    try {catalog=await api('/open-finance/catalogs')} catch (_) {
      if(view.contains(host))host.innerHTML='<p role="alert" class="attention">Não foi possível carregar o Open Finance. Verifique o armazenamento e tente novamente.</p><button type="button" data-retry>Recarregar</button>';
      host.querySelector('[data-retry]')?.addEventListener('click',openFinance);return;
    }
    if(!view.contains(host))return;
    host.innerHTML=`<p class="of-notice">Consulta de staging bancário. Os filtros usam a data informada pelo provedor, não a competência das despesas. A direção declarada da conta não comprova liquidação nem representa receita/despesa oficial.</p>
      <form class="form-card of-filters" aria-label="Filtros bancários"><div class="form-grid">
      <label>Data inicial<input type="date" name="start"></label><label>Data final<input type="date" name="end"></label>
      <label>Instituição / conexão<select name="connection_id">${option('','Todas as instituições')}${catalog.connections.map(c=>option(c.id,`${c.institution} · ${c.id}${c.historical?' (histórica)':''}`)).join('')}</select></label>
      <label>Conta bancária<select name="external_account_id"></select></label>
      <label>Movimentação<select name="direction">${option('all','Todas, incluindo desconhecidas/conflitos')}${option('incoming','Entradas (CREDIT)')}${option('outgoing','Saídas (DEBIT)')}</select></label>
      <label>Categoria bancária<select name="category_key"></select></label>
      <label>Descrição ou estabelecimento<input name="search" type="search" maxlength="256" placeholder="Ex.: café"></label>
      <label>Sincronização de origem<select name="origin_run_id"></select></label>
      </div><div class="actions"><button type="submit">Aplicar filtros</button><button type="button" class="secondary" data-clear>Limpar filtros</button></div></form>
      <div class="of-results" aria-live="polite"></div><section class="panel of-history"><h2>Histórico das sincronizações manuais</h2><p>Nenhuma sincronização é iniciada ao abrir esta tela.</p><div data-history></div></section>`;
    const form=host.querySelector('form'),results=host.querySelector('.of-results');
    const names=['start','end','connection_id','external_account_id','direction','category_key','search','origin_run_id'];
    const choice=(name)=>form.elements.namedItem(name);
    function scopedOptions() {
      const cid=choice('connection_id').value;
      for(const [name,items,key,label] of [
        ['external_account_id',catalog.accounts,'external_id',a=>`${a.name||'Conta sem nome'} · ${a.external_id}`],
        ['category_key',catalog.categories,'category_key',c=>c.original_name||c.external_id||'Categoria sem nome'],
        ['origin_run_id',catalog.runs,'id',r=>`${r.started_at} · ${runLabels[r.state]||r.state} · ${r.id.slice(0,8)}`]]) {
        const select=choice(name);select.innerHTML=option('',cid?'Todas':'Selecione uma conexão')+items.filter(r=>r.connection_id===cid).map(r=>option(r[key],label(r))).join('');select.disabled=!cid;
      }
    }
    for(const name of ['start','end','connection_id','direction','search'])choice(name).value=saved[name]|| (name==='direction'?'all':'');
    scopedOptions();for(const name of ['external_account_id','category_key','origin_run_id'])choice(name).value=saved[name]||'';
    choice('connection_id').onchange=scopedOptions;
    let generation=0;
    async function load() {
      const current=++generation;
      results.innerHTML='<p role="status">Carregando transações bancárias…</p>';
      const q=new URLSearchParams({contract:'of-l2-v2',metrics:'exact',page:String(page),page_size:'25',...saved});
      try {
        const response=await api('/open-finance/transactions?'+q);
        if(current!==generation||!view.contains(host))return;
        const meta=response.query_meta,counts=meta.counts;
        const qualifiers=[];
        if(meta.query_completeness!=='COMPLETE')qualifiers.push('Há registros cujo enquadramento nos filtros não pôde ser determinado. A lista não representa todas as possíveis correspondências.');
        if(meta.coverage.direction.state==='PARTIAL')qualifiers.push('Existem movimentos sem direção comprovada ou com conflito. “Todas” mantém esses registros visíveis.');
        if(meta.warnings.includes('PROVENANCE_UNKNOWN_PRESENT'))qualifiers.push('Há origens não comprovadas; não são inferidas pelas datas.');
        const count=counts.after_f04.state==='EXACT'?`${counts.after_f04.value} ${counts.after_f04.value===1?'transação encontrada':'transações encontradas'}`:'Contagem não disponível';
        results.innerHTML=`<p class="of-count">${esc(count)} · Página ${page}</p>${qualifiers.map(t=>`<p class="of-notice">${esc(t)}</p>`).join('')}${response.items.length?`<table class="of-table"><caption>Transações bancárias importadas</caption><thead><tr>${['Data','Instituição','Conta','Descrição / estabelecimento','Categoria bancária','Valor original','Direção'].map(t=>`<th scope="col">${t}</th>`).join('')}</tr></thead><tbody>${response.items.map(tx=>{
          const date=tx.transaction_date,category=tx.category;
          const values=[date,tx.institution,`${tx.account_name||'Nome indisponível'} · ${tx.external_account_id}`,
            `${tx.description_original??'Descrição indisponível'}${tx.merchant_name?' · '+tx.merchant_name:''}`,
            tx.category_key===null?'Sem categoria':category?.original_name||category?.external_id||'Categoria não resolvida',
            `${tx.amount_decimal} ${tx.currency}`,directionLabels[tx.direction.result]||'Desconhecida'];
          return `<tr>${values.map((v,i)=>`<td data-label="${['Data','Instituição','Conta','Descrição','Categoria','Valor','Direção'][i]}"><bdi>${esc(v)}</bdi>${i===6?`<small>${esc(reasonLabels[tx.direction.reason_code]||'Direção não comprovada')}${tx.direction.warnings.includes('CARD_SIGN_DOCUMENTATION_UNRESOLVED')?' · Perspectiva da conta do cartão':''}</small>`:''}</td>`).join('')}</tr>`;
        }).join('')}</tbody></table>`:'<p class="empty">Nenhuma transação encontrada para os filtros selecionados.</p>'}
          <div class="actions of-pagination"><button type="button" data-prev ${page===1?'disabled':''}>Anterior</button><button type="button" data-next ${!response.has_more?'disabled':''}>Próxima</button><button type="button" class="secondary" data-refresh>Atualizar consulta</button></div>`;
        results.querySelector('[data-prev]').onclick=()=>{page--;load()};results.querySelector('[data-next]').onclick=()=>{page++;load()};results.querySelector('[data-refresh]').onclick=load;
      } catch(error) {
        if(current!==generation||!view.contains(host))return;
        const message=error.code==='QUERY_PROFILE_UNAVAILABLE'?'Busca textual indisponível: o runtime não possui o perfil Unicode aprovado. Nenhum filtro foi ignorado.':'Não foi possível consultar as transações bancárias. Nenhum resultado parcial foi publicado.';
        results.innerHTML=`<p role="alert" class="attention">${esc(message)}</p><button type="button" data-retry>Repetir consulta</button>`;results.querySelector('button').onclick=load;
      }
    }
    form.onsubmit=e=>{e.preventDefault();if(choice('start').value&&choice('end').value&&choice('start').value>choice('end').value){choice('end').setCustomValidity('A data final deve ser igual ou posterior à inicial.');choice('end').reportValidity();return}saved=Object.fromEntries(names.map(n=>[n,choice(n).value]).filter(([,v])=>v!==''));page=1;load()};
    choice('end').oninput=()=>choice('end').setCustomValidity('');choice('start').oninput=()=>choice('end').setCustomValidity('');
    host.querySelector('[data-clear]').onclick=()=>{saved={};page=1;for(const n of names)choice(n).value=n==='direction'?'all':'';choice('end').setCustomValidity('');scopedOptions();load()};
    const history=host.querySelector('[data-history]');
    host.querySelector('.of-history > p').textContent='Últimas 25 sincronizações registradas. Nenhuma sincronização é iniciada ao abrir esta tela.';
    history.innerHTML=catalog.runs.length?`<ul class="of-run-list">${catalog.runs.slice(0,25).map(r=>`<li><strong>${esc(catalog.connections.find(c=>c.id===r.connection_id)?.institution||r.connection_id)}</strong> · ${esc(runLabels[r.state]||r.state)}<small>${esc(r.started_at)} · ${r.inserted_count} inseridas · ${r.updated_count} atualizadas · ${r.page_count} páginas${r.error_code?' · '+esc(r.error_code):''}</small></li>`).join('')}</ul>`:'<p class="empty">Nenhuma sincronização manual registrada.</p>';
    await load();
  };
}
