import {createQueryGeneration} from './query-generation.js';
import {openFinanceError} from './open-finance-errors.js';
import {institutionName,runStateLabel} from './open-finance-labels.js';

export function mountSyncPreferences({host,panel,api,esc,navigation}){
  const section=document.createElement('section');
  section.className='panel of-sync-preferences';
  section.innerHTML='<h2>Sincronização automática</h2><div data-sync-preferences-result></div><p role="status" data-sync-feedback></p>';
  panel.firstElementChild.after(section);
  const target=section.querySelector('[data-sync-preferences-result]'),feedback=section.querySelector('[data-sync-feedback]');
  const queries=createQueryGeneration(navigation);
  const instant=value=>value?new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short',timeZone:'America/Sao_Paulo'}).format(new Date(value)):'Indisponível';
  function paint(data){
    const rows=data.connections.map(row=>'<li><h3>'+esc(institutionName(row.institution))+'</h3><dl>'+
      [['Atualização do Item na Pluggy',instant(row.last_pluggy_update)],['Próxima atualização prevista na Pluggy',instant(row.next_pluggy_update)],
       ['Última sincronização local bem-sucedida',instant(row.last_success)],['Última tentativa local',instant(row.last_attempt)],
       ['Próxima coleta local prevista',row.effective?instant(row.next_attempt):'Desativada'],
       ['Estado da última tentativa',row.state==='NOT_RUN'?'Sem tentativas':runStateLabel(row.state)],
       ['Falha mais recente',row.last_error?openFinanceError(row.last_error):'Sem falha na última tentativa']]
      .map(([label,value])=>'<div><dt>'+label+'</dt><dd>'+esc(value)+'</dd></div>').join('')+'</dl></li>').join('');
    target.innerHTML='<form class="of-presentation" aria-label="Preferências de sincronização">'+
      '<label><input type="checkbox" name="enabled" '+(data.effective_enabled?'checked':'')+' '+(data.available?'':'disabled')+'> Habilitar coleta automática</label>'+
      '<label>Intervalo<select name="hours">'+data.interval_options.map(hours=>'<option value="'+hours+'" '+(hours===data.interval_hours?'selected':'')+'>'+hours+(hours===1?' hora':' horas')+'</option>').join('')+'</select></label>'+
      '<button type="submit" '+(data.available?'':'disabled')+'>Salvar configuração</button></form>'+
      '<p>'+(data.available?'A configuração vale para as próximas coletas locais, sem reiniciar.':'A política do Supervisor ou da conexão impede a coleta automática.')+' A coleta manual continua disponível.</p>'+
      (rows?'<ul class="of-sync-institutions">'+rows+'</ul>':'<p>Nenhuma conexão ativa.</p>');
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
