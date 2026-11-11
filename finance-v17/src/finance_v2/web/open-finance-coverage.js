import {createQueryGeneration} from './query-generation.js';
import {openFinanceError} from './open-finance-errors.js';
import {mountDomains} from './open-finance-domain.js';
import {activeConnections,runSummary} from './open-finance-status.js';
import {mountSantanderRecovery} from './santander-binding-recovery.js';

export function mountCoverage(context){
  const {host,api,esc,catalog,navigation=null}=context;
  mountDomains(context);
  const panel=host.querySelector('#of-panel-connections'),manual=document.createElement('section');manual.className='panel';
  manual.innerHTML=`<h2>Leitura manual de todos os produtos em cache</h2><p>Não atualiza Item, saldo em tempo real, consentimento ou instituição. Não promove dados a lançamentos oficiais. A primeira consulta pode emitir uma chave temporária com a configuração privada existente.</p>${activeConnections(catalog).map(c=>`<button type="button" data-coverage-sync="${esc(c.id)}">Consultar cache: ${esc(c.institution)}</button>`).join('')}<p role="status" data-coverage-progress>Nenhuma coleta iniciada.</p>`;
  panel.append(manual);
  mountSantanderRecovery(context);
  manual.querySelectorAll('[data-coverage-sync]').forEach(button=>button.onclick=async()=>{
    if(!window.confirm('Consultar os produtos já disponíveis no cache Pluggy? Nenhuma atualização bancária será disparada.'))return;
    const buttons=[...manual.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
    const progress=manual.querySelector('[data-coverage-progress]');progress.textContent='Leitura manual em andamento…';
    let collecting=true;const polls=createQueryGeneration(navigation);
    const poll=setInterval(async()=>{if(!collecting||!manual.isConnected)return;try{const query=polls.begin();const r=await api('/open-finance/coverage',{queryScope:query});if(collecting&&manual.isConnected&&query.current())progress.textContent=`${r.coverage.filter(c=>c.state==='RUNNING').length} coleções em andamento; consulte os estados por recurso.`}catch(_){}},1500);
    try{const r=await api('/open-finance/coverage-sync',{method:'POST',body:{connection_id:button.dataset.coverageSync}});if(navigation&&!navigation.current())return;progress.textContent=runSummary(r.run,r.run.state==='SUCCEEDED'?'Coleta concluída. Confira cobertura e permissões de cada produto.':openFinanceError(r.run.error_code));}
    catch(error){if(!navigation||navigation.current())progress.textContent=openFinanceError(error.code)}
    finally{collecting=false;clearInterval(poll);polls.cancel();if(!navigation||navigation.current())buttons.forEach(b=>b.disabled=false)}
  });
}
