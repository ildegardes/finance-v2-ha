// Explicit owner action only. No request is made on page mount or navigation.
const labels=Object.freeze({IMPORTED_RECORDS:'Existem registros importados Santander.',HISTORY_NOT_EXPECTED_26_FAILURES:'O histórico difere das 26 falhas esperadas.',ACTIVE_RUN:'Há uma sincronização em andamento.',LEASE_PRESENT:'Existe lease pendente, mesmo que vencido.',INDIRECT_OR_CROSS_REFERENCE:'Existem referências indiretas ou cruzadas.',INTEGRITY:'A integridade não foi confirmada.',UNRECOGNIZED_BINDING:'O vínculo não corresponde aos candidatos atual ou invertido.',CHECKPOINT_DEPENDENCY:'Há checkpoint que exige análise.',COVERAGE_DEPENDENCY:'Há cobertura que exige análise.',RESUME_DEPENDENCY:'Há referência de retomada.'});
export function mountSantanderRecovery({host,api,navigation=null}){
 const panel=host.querySelector('#of-panel-connections');if(!panel)return;
 const section=document.createElement('section');section.className='panel';
 section.innerHTML='<h2>Administração: vínculo Santander</h2><p>Exclusivo do proprietário. Verifica o vínculo e as dependências locais; não consulta a Pluggy. A correção altera somente o binding Santander e preserva o histórico. Não inicia coleta.</p><button type="button" data-recovery-inspect>Verificar elegibilidade</button><label><input type="checkbox" data-recovery-backup> Confirmei um backup consistente e atual de configuração e dados, com procedimento de recuperação.</label><button type="button" data-recovery-apply disabled>Corrigir vínculo Santander</button><button type="button" data-recovery-revert disabled>Reverter última correção Santander</button><p role="status" aria-live="polite" data-recovery-status>Nenhuma verificação ou correção iniciada.</p>';
 panel.append(section);
 const inspect=section.querySelector('[data-recovery-inspect]'),apply=section.querySelector('[data-recovery-apply]'),revert=section.querySelector('[data-recovery-revert]'),backup=section.querySelector('[data-recovery-backup]'),status=section.querySelector('[data-recovery-status]');
 let report=null,busy=false;
 const current=()=>section.isConnected&&(!navigation||navigation.current());
 function controls(){inspect.disabled=busy;apply.disabled=busy||!backup.checked||!report||!['ELIGIBLE','ALREADY_CORRECT'].includes(report.status);revert.disabled=busy||!backup.checked||!report?.revert_operation;}
 function show(r){report=r;status.textContent=`Atual: ${r.CURRENT_BINDING_MATCH}. Invertido: ${r.SWAPPED_BINDING_MATCH}. ${r.status==='ELIGIBLE'?'Elegível para confirmação explícita.':r.status==='ALREADY_CORRECT'?'Vínculo já corresponde à configuração atual.':'Correção bloqueada.'} ${(r.blockers||[]).map(x=>labels[x]||'Há uma condição que exige análise.').join(' ')}`;controls();}
 function error(e){status.textContent='Operação não confirmada. Código: '+(/^[A-Z0-9_]{1,100}$/.test(e.code||'')?e.code:'LOCAL_ERROR')+'. Verifique o estado antes de repetir.';report=null;controls();}
 inspect.onclick=async()=>{busy=true;controls();try{const r=await api('/open-finance/santander-binding-recovery');if(current())show(r)}catch(e){if(current())error(e)}finally{busy=false;if(current())controls()}};
 backup.onchange=controls;
 async function execute(action){
  if(busy||!report||!backup.checked)return;
  const operation=report.revert_operation;
  busy=true;controls();
  try{
   const prepared=await api('/open-finance/santander-binding-recovery/prepare',{method:'POST',body:{action,backup_confirmed:true,...(action==='REVERT'?{operation}:{})}});
   if(!current())return;
   if(!window.confirm(action==='APPLY'?'Confirmar manutenção de um único campo do vínculo Santander? Os 26 históricos serão preservados. Não haverá coleta.':'Confirmar reversão seletiva? Ela será recusada se o conjunto Santander mudou. Dados manuais e Itaú posteriores serão preservados.'))return;
   const r=await api('/open-finance/santander-binding-recovery/confirm',{method:'POST',body:{confirmation:prepared.confirmation,explicit_confirmation:action==='APPLY'?'CORRIGIR_BINDING_SANTANDER':'REVERTER_BINDING_SANTANDER',backup_confirmed:true}});
   if(current()){status.textContent=r.status==='COMMITTED_AUDIT_PENDING'?'A transação foi confirmada; a auditoria precisa ser reconciliada. Não repetir a correção.':r.status==='APPLIED'?'Vínculo Santander corrigido. Nenhuma coleta foi iniciada.':r.status==='REVERTED'?'Correção revertida seletivamente.':r.status==='ALREADY_REVERTED'?'A correção já estava revertida.':'O vínculo já estava correto; nenhuma linha foi alterada.';report=null;backup.checked=false;}
  }catch(e){if(current())error(e)}finally{busy=false;if(current())controls()}
 }
 apply.onclick=()=>execute('APPLY');revert.onclick=()=>execute('REVERT');
}
