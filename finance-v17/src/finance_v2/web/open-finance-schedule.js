import {createQueryGeneration} from './query-generation.js';
import {openFinanceError} from './open-finance-errors.js';
import {runStateLabel} from './open-finance-labels.js';

const policyMessages={
  ARCHIVED:'Conexão arquivada. Consulte seu histórico nas Instituições Financeiras.',
  NOT_ACTIVATED:'Valide e ative a conexão nas Instituições Financeiras.',
  CONNECTION_DISABLED:'Conexão suspensa. Para retomar, valide e reative nas Instituições Financeiras.',
  SUPERVISOR_DISABLED:'Habilite a coleta automática nas opções do add-on.',
  GLOBAL_PREFERENCE_DISABLED:'Habilite a preferência global de coleta nesta tela.',
  CONNECTION_AUTO_DISABLED:'Habilite a coleta automática neste card pelo acesso administrativo privado.',
  CONNECTION_BINDING_CHANGED:'Confira o vínculo do Item e as credenciais antes de coletar.',
};

export function mountSyncPreferences({host,panel,api,esc,navigation}){
  const section=document.createElement('section');
  section.className='panel of-sync-preferences';
  section.innerHTML='<h2>Sincronização automática</h2><div data-sync-preferences-result></div><p role="status" data-sync-feedback></p>';
  panel.firstElementChild.after(section);
  const target=section.querySelector('[data-sync-preferences-result]'),feedback=section.querySelector('[data-sync-feedback]');
  const queries=createQueryGeneration(navigation);
  const instant=value=>value?new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short',timeZone:'America/Sao_Paulo'}).format(new Date(value)):'Indisponível';
  const cards=new Map([...panel.querySelectorAll('[data-connection-policy]')].map(target=>
    [target.closest('[data-connection-id]').dataset.connectionId,target]));
  function paint(data){
    for(const row of data.connections){
      const card=cards.get(row.connection_id);
      if(!card)continue;
      card.innerHTML='<p><strong>Coleta automática local</strong> · '+(row.requested_enabled?'Ativada':'Pausada')+'</p>'+
        '<p>Próxima coleta local prevista <strong>'+(row.effective?esc(instant(row.next_attempt)):'Desativada')+'</strong></p>'+
        (row.reason?'<p>'+esc(policyMessages[row.reason]||'Confira a política da conexão.')+'</p>':'')+
        '<details><summary>Horários e histórico da coleta</summary><dl>'+
      [['Atualização do Item na Pluggy',instant(row.last_pluggy_update)],['Próxima atualização prevista na Pluggy',instant(row.next_pluggy_update)],
       ['Última sincronização local bem-sucedida',instant(row.last_success)],['Última tentativa local',instant(row.last_attempt)],

       ...(row.action_required?[['Ação na conexão','Confira o consentimento e valide o Item antes de repetir a coleta.']]:[]),
       ['Estado da última tentativa',row.state==='NOT_RUN'?'Sem tentativas':runStateLabel(row.state)],
       ['Falha mais recente',row.last_error?openFinanceError(row.last_error):'Sem falha na última tentativa']]
      .map(([label,value])=>'<div><dt>'+label+'</dt><dd>'+esc(value)+'</dd></div>').join('')+'</dl></details>'+
        (data.registry_admin_available&&row.policy_editable?'<button type="button" class="quiet" data-connection-auto>'+
          (row.requested_enabled?'Pausar coleta automática':'Habilitar coleta automática')+'</button>':'')+
        '<p role="status" data-connection-policy-feedback></p>';
      const button=card.querySelector('[data-connection-auto]');
      if(button)button.onclick=()=>changeConnection(row,button);
    }
    target.innerHTML='<form class="of-presentation" aria-label="Preferências de sincronização">'+
      '<label><input type="checkbox" name="enabled" '+(data.requested_enabled?'checked':'')+' '+(data.available?'':'disabled')+'> Habilitar coleta automática</label>'+
      '<label>Intervalo<select name="hours">'+data.interval_options.map(hours=>'<option value="'+hours+'" '+(hours===data.interval_hours?'selected':'')+'>'+hours+(hours===1?' hora':' horas')+'</option>').join('')+'</select></label>'+
      '<button type="submit" '+(data.available?'':'disabled')+'>Salvar configuração</button></form>'+
      '<p>'+(data.available?'A preferência global permite ou pausa as próximas coletas locais.':'A política do add-on ou das conexões bloqueia a coleta automática.')+
      ' A coleta manual continua disponível. Os controles por conexão usam o acesso administrativo privado.</p>';
    const form=target.querySelector('form');
    form.onsubmit=async event=>{
      event.preventDefault();
      const scope=queries.begin();
      form.querySelector('button').disabled=true;
      feedback.textContent='Salvando configuração…';
      try{
        const saved=await api('/open-finance/sync-preferences',{method:'POST',body:{enabled:data.available?form.elements.enabled.checked:data.requested_enabled,
          interval_hours:Number(form.elements.hours.value),revision:data.revision}});
        if(scope.current()&&host.isConnected){paint(saved);feedback.textContent='Configuração salva.';target.querySelector('button').focus()}
      }catch(_){
        if(scope.current()&&host.isConnected){feedback.textContent='Não foi possível salvar. Recarregue a configuração antes de tentar novamente.';form.querySelector('button').disabled=false;}
      }
    };
  }
  async function changeConnection(row,button){
    const scope=queries.begin();
    const card=cards.get(row.connection_id),enabled=!row.requested_enabled;
    button.disabled=true;
    card.querySelector('[data-connection-policy-feedback]').textContent='Salvando política da conexão…';
    try{
      await api('/open-finance/registry/auto-sync',{method:'POST',body:{
        connection_id:row.connection_id,revision:row.revision,enabled,confirmed:true}});
      const saved=await api('/open-finance/sync-preferences',{queryScope:scope});
      if(scope.current()&&host.isConnected){
        paint(saved);
        card.querySelector('[data-connection-policy-feedback]').textContent=enabled?'Preferência ativada.':'Preferência pausada.';
        card.querySelector('[data-connection-auto]')?.focus();
      }
    }catch(error){
      if(scope.current()&&host.isConnected){
        const busy=error.code==='SYNC_BUSY';
        card.querySelector('[data-connection-policy-feedback]').textContent=busy
          ?'A coleta está em andamento. Tente novamente quando terminar.'
          :'Não foi possível confirmar a política. Volte à aba para recarregar a configuração.';
        if(busy)button.disabled=false;
      }
    }
  }
  async function load(){
    const scope=queries.begin();
    target.innerHTML='<p role="status">Carregando configuração…</p>';
    feedback.textContent='';
    try{
      const data=await api('/open-finance/sync-preferences',{queryScope:scope});
      if(scope.current()&&host.isConnected)paint(data);
    }catch(_){
      if(scope.current()&&host.isConnected){
        target.innerHTML='<p role="alert">Configuração de sincronização indisponível.</p><button type="button">Tentar novamente</button>';
        target.querySelector('button').onclick=load;
      }
    }
  }
  host.addEventListener('of-tab-selected',event=>{if(event.detail==='connections')load();else queries.cancel()});
}
