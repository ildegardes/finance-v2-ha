# Candidata de recuperaÃ§Ã£o seletiva Santander

Base: tag v0.1.27-open-finance.1, commit 3672d20d5f6ec7262a506a3779805f7271bfc5c0; schema 11. A prÃ³xima versÃ£o proposta Ã© 0.1.28-open-finance.1. Esta branch Ã© uma candidata em revisÃ£o, nÃ£o uma release distribuÃ­da.

## Limite de autorizaÃ§Ã£o

O proprietÃ¡rio confirmou a inversÃ£o inicial dos campos. Isso justifica investigar o par invertido; nÃ£o comprova o valor atualmente persistido. A candidata farÃ¡ essa prova na prÃ³pria instalaÃ§Ã£o antes de permitir qualquer alteraÃ§Ã£o. A recuperaÃ§Ã£o em produÃ§Ã£o NÃƒO foi executada nem estÃ¡ autorizada por este PR. NÃ£o hÃ¡ chamadas Pluggy, leitura de cofre, importaÃ§Ã£o ou coleta automÃ¡tica nesta operaÃ§Ã£o.

## ImplementaÃ§Ã£o e identidade

`Application.__init__` entrega o mesmo objeto Settings da aplicaÃ§Ã£o a `SantanderBindingRecovery`. NÃ£o recebe credenciais, identificadores bancÃ¡rios ou digests pelo pedido administrativo. Os campos existentes do add-on continuam sendo carregados pelo lanÃ§ador protegido, a partir de /data/options.json. NÃ£o hÃ¡ dependÃªncia de Windows, cofre ou staging externo.

`config`, `bindings` e `inspect_db`, em src/finance_v2/open_finance_recovery.py, selecionam exclusivamente a conexÃ£o configurada com id santander. Exigem configuraÃ§Ã£o habilitada, perfil meupluggy_personal e sincronizaÃ§Ã£o automÃ¡tica desativada em todas as conexÃµes habilitadas. Calculam os dois candidatos com a funÃ§Ã£o publicada `OpenFinanceService._binding`: SHA-256 do JSON compacto de [client_id,item_id]. O candidato invertido troca apenas esses dois campos em uma cÃ³pia da configuraÃ§Ã£o. Client Secret nÃ£o participa da comparaÃ§Ã£o nem Ã© lido pelo mecanismo de recuperaÃ§Ã£o.

- Atual igual ao persistido: ALREADY_CORRECT; nenhuma atualizaÃ§Ã£o nem novo recibo de correÃ§Ã£o.
- Invertido igual ao persistido e todas as guardas aprovadas: ELIGIBLE.
- Valor desconhecido, configuraÃ§Ã£o insuficiente ou qualquer bloqueio: BLOCKED/erro sanitizado; nenhuma atualizaÃ§Ã£o.

ALREADY_CORRECT descreve somente o binding. Outros bloqueios, se houver, continuam presentes no relatÃ³rio; esse resultado nÃ£o autoriza uma sincronizaÃ§Ã£o.

## DependÃªncias e histÃ³rico

As treze tabelas verificadas sÃ£o:

| Tabela | CondiÃ§Ã£o para aplicar a correÃ§Ã£o |
| --- | --- |
| of_connections | Uma conexÃ£o Santander; binding invertido; nenhum lease em qualquer conexÃ£o |
| of_sync_runs | Exatamente 26 Santander, todas FAILED/AUTH_FAILED; nenhum RUNNING em qualquer conexÃ£o |
| of_accounts | Zero registros Santander |
| of_categories | Zero registros Santander |
| of_transactions | Zero registros Santander |
| of_transaction_revisions | Zero registros Santander |
| of_resource_records | Zero registros Santander, inclusive Item/consentimento persistido |
| of_resource_revisions | Zero registros Santander |
| of_resource_links | Zero registros Santander |
| of_resource_link_revisions | Zero registros Santander |
| of_resource_coverage | Somente metadados de falha do Item com zero pÃ¡ginas/registros |
| of_collection_checkpoints | Somente falha inicial do Item; sem coleta completa, pÃ¡ginas ou registros |
| of_domain_sync_audit | HistÃ³rico preservado; sem RESUME ou referÃªncia de retomada |

TambÃ©m sÃ£o verificadas referÃªncias indiretas aos runs, referÃªncias cruzadas de transaÃ§Ãµes, todas as foreign keys, integridade SQLite, DDL, Ã­ndices, ausÃªncia de triggers Open Finance e ausÃªncia de novas referÃªncias externas Ã s treze tabelas. Schema inesperado bloqueia. A Ãºnica normalizaÃ§Ã£o de metadados trata a grafia de tipo de coluna virtual reportada diferentemente por SQLite 3.35 e 3.40; expressÃ£o gerada e DDL continuam exatos.

A polÃ­tica Ã© deliberadamente conservadora: mesmo dados parciais, metadados nÃ£o reconhecidos ou um lease vencido mas ainda persistido bloqueiam a correÃ§Ã£o. AusÃªncia de sucesso no histÃ³rico nunca substitui a inspeÃ§Ã£o das tabelas. A contagem de 26 Ã© especÃ­fica deste incidente; outra contagem exige revisÃ£o, nÃ£o flexibilizaÃ§Ã£o automÃ¡tica.

## TransaÃ§Ã£o, WAL e concorrÃªncia

O serviÃ§o abre SQLite diretamente com mode=ro na inspeÃ§Ã£o e mode=rw na confirmaÃ§Ã£o. NÃ£o cria banco, nÃ£o usa immutable=1, nÃ£o copia somente o arquivo principal e nÃ£o executa PRAGMA journal_mode. A leitura transacional inclui o estado confirmado no WAL; SQLite pode acessar seus arquivos auxiliares normais. Usa a fila de escrita existente e BEGIN IMMEDIATE para exclusÃ£o entre processos, com espera de atÃ© dois segundos e inspeÃ§Ã£o limitada a 30 segundos.

Na confirmaÃ§Ã£o, configuraÃ§Ã£o e conjunto Santander devem corresponder Ã  preparaÃ§Ã£o. Todas as guardas sÃ£o repetidas dentro da transaÃ§Ã£o. O UPDATE tem predicado de comparaÃ§Ã£o do binding anterior e ausÃªncia de lease, deve afetar exatamente uma linha e somente binding_hash. Um authorizer SQLite nega INSERT/DELETE/DDL e qualquer outra coluna de UPDATE. Antes do commit, sÃ£o comparados integralmente schema e todas as demais cÃ©lulas do banco com MAC privado, alÃ©m de integrity_check e foreign_key_check. Os 26 runs, ItaÃº, dados manuais, timestamps e estados nÃ£o sÃ£o reescritos.

NÃ£o hÃ¡ encerramento de jobs, limpeza de leases, alteraÃ§Ã£o de credenciais, reset de trava histÃ³rica ou migraÃ§Ã£o. Se uma coleta disputar a transaÃ§Ã£o, a manutenÃ§Ã£o Ã© bloqueada/abortada ou a coleta verifica o binding jÃ¡ confirmado posteriormente; nenhuma coleta Ã© iniciada pela manutenÃ§Ã£o.

## AdministraÃ§Ã£o e CSRF

GET /api/v2/open-finance/santander-binding-recovery inspeciona agregados somente apÃ³s aÃ§Ã£o explÃ­cita. POST .../prepare exige action APPLY, REVERT ou RECONCILE e backup_confirmed=true. POST .../confirm exige o desafio de uso Ãºnico, a confirmaÃ§Ã£o literal correspondente e nova confirmaÃ§Ã£o de backup. Nenhum endpoint aceita SQL, conexÃ£o arbitrÃ¡ria, binding ou credenciais.

A credencial existente do proprietÃ¡rio da interface (UI:local) Ã© o administrador desta aplicaÃ§Ã£o. Clientes externos, MCP, OAuth externo e scheduler nÃ£o recebem a capacidade. SessÃµes por cookie exigem o CSRF existente; writes com Origin exigem a origem WSGI exata ou uma origem CORS explicitamente configurada. NÃ£o hÃ¡ confianÃ§a cega em X-Forwarded-*; um proxy incompatÃ­vel falha fechado. O desafio expira em cinco minutos, Ã© vinculado Ã  sessÃ£o e consumido mesmo em falha. O servidor padrÃ£o usa um processo com threads; reinicializaÃ§Ã£o perde desafios pendentes e exige nova preparaÃ§Ã£o.

A interface nÃ£o executa GET nem POST de manutenÃ§Ã£o ao montar a pÃ¡gina. Exige clique de inspeÃ§Ã£o, confirmaÃ§Ã£o de backup e diÃ¡logo explÃ­cito antes do POST final. NÃ£o aplica retry automÃ¡tico e descarta efeitos visuais de navegaÃ§Ã£o obsoleta. O backend nÃ£o agenda a operaÃ§Ã£o.

## Auditoria e limites

Recibos privados ficam ao lado do banco, em <nome-do-banco>.santander-recovery, com diretÃ³rio 0700 e arquivos 0600 em Linux. ContÃªm somente identificador aleatÃ³rio da operaÃ§Ã£o, fases, horÃ¡rios, chave HMAC aleatÃ³ria e MACs de integridade privados. NÃ£o contÃªm credenciais, UUIDs bancÃ¡rios, binding_hash ou payloads. A chave e os MACs nunca sÃ£o retornados na API. SÃ£o verificaÃ§Ãµes locais, nÃ£o uma assinatura contra um administrador/root que possa reescrever o banco e os recibos.

PREPARED Ã© gravado e fsync executado antes do commit SQLite. Falha anterior ao commit provoca rollback. Falha ao finalizar o recibo depois de um commit bem-sucedido produz COMMITTED_AUDIT_PENDING, nunca uma falsa promessa de rollback. ReconciliaÃ§Ã£o ocorre somente por nova aÃ§Ã£o administrativa explÃ­cita e exige identidade exata do conjunto Santander; GET e boot nÃ£o reconciliam/escrevem. Recibos ambÃ­guos ou configuraÃ§Ã£o alterada bloqueiam. NÃ£o remova recibos para contornar o bloqueio.

A confirmaÃ§Ã£o de backup Ã© uma declaraÃ§Ã£o explÃ­cita do proprietÃ¡rio; a aplicaÃ§Ã£o nÃ£o consegue provar recuperabilidade de um backup externo. A implantaÃ§Ã£o/execuÃ§Ã£o permanece condicionada Ã  confirmaÃ§Ã£o independente de backup consistente atual. A homologaÃ§Ã£o usa apenas dados sintÃ©ticos e nÃ£o comprova o binding nem a ausÃªncia de dados na produÃ§Ã£o.

## Pontos de código revisados

| Arquivo | Função/linha |
| --- | --- |
| finance-v17/src/finance_v2/open_finance_recovery.py | def config — 61 |
| finance-v17/src/finance_v2/open_finance_recovery.py | def bindings — 96 |
| finance-v17/src/finance_v2/open_finance_recovery.py | def inspect_db — 106 |
| finance-v17/src/finance_v2/open_finance_recovery.py | def prepare — 233 |
| finance-v17/src/finance_v2/open_finance_recovery.py | def execute — 250 |
| finance-v17/src/finance_v2/open_finance_recovery.py | def reconcile — 210 |
| finance-v17/src/finance_v2/open_finance_recovery_checks.py | def schema_check — 21 |
| finance-v17/src/finance_v2/open_finance_recovery_checks.py | def dependencies — 54 |
| finance-v17/src/finance_v2/open_finance_http.py | def dispatch — 58 |
| finance-v17/src/finance_v2/web/santander-binding-recovery.js | export function mount — 3 |
