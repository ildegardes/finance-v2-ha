# Finance V17 0.1.25-open-finance.1 — instrumentação Open Finance

Baseline 0.1.24: commit de publicação `0ed53d32e7a7c57f3f37a7fd239d4582854e4032`, árvore `2fc366bc9e4fae957d1763c5d242fca7c075895c`. Schema 10, migrations 001–010 inalteradas. Esta candidata incorpora somente o código diagnóstico D02 aprovado e os metadados/testes/documentação indispensáveis à release. Preparação local não autoriza publicação ou instalação.

## O que muda

Uma falha ACCOUNT_SCOPE_MISMATCH ou AUTH_FAILED passa a produzir um evento WARNING `OPEN_FINANCE_DIAGNOSTIC` com campos fechados: instituição lógica, correlação de execução local, recurso, operação, etapa, motivo e status HTTP quando disponível. Os códigos públicos e as respostas HTTP não mudam. Nenhum valor de Item, conta, credencial, payload, URL parametrizada ou dado financeiro é registrado.

Motivos de escopo distinguem campo ausente/null/divergente, conta fora do cache de autorização e divergência de conexão na persistência. Auth distingue recusa na obtenção da chave temporária, repetição de 401 e 403 de recurso obrigatório. Isso localiza uma falha; não renova consentimento, corrige credencial, troca Item ou remove guarda de segurança.

Não há mudança de configuração, auto-sync, seleção de banco, requisições Pluggy, paginação, staging, idempotência, leases, lifecycle, scheduler, OAuth/MCP ou interface. O MCP anuncia somente o novo metadado de versão, preservando protocolo 2025-03-26. A versão 0.1.25 não introduz migration nem ativação de opções.

## Identidade e evidências

`RELEASE_0.1.25_MANIFEST.json` identifica os 84 arquivos de produto e oito protegidos. O commit que contém esse manifesto vincula a árvore; seu SHA é registrado externamente, evitando autorreferência. BUILD_LOCK e manifestos anteriores permanecem históricos e íntegros.

`RELEASE_0.1.25_VALIDATION.json` apresenta resultados e hashes dos logs. Build ARM64 deve ser feito pelo Dockerfile original de distribuição, a partir da base Python 3.12.7 fixada por digest, com requisitos e hashes fixos. A imagem derivada de ensaio D02 não constitui artefato de release.

Os testes usam apenas bancos novos sintéticos e provedor simulado. Build/execução Docker ARM64 emulada não equivalem a instalação, watchdog ou restauração pelo Supervisor real. Não houve acesso a dados bancários, consentimentos, credenciais reais ou Home Assistant nesta preparação. A causa real Itaú/Santander continua NOT_VERIFIED.

## Pré-condições para futura instalação

1. Obter autorizações independentes de publicação e de operação no HA. Confirmar os commits e revalidar a master para evitar sobrescrever alterações concorrentes.
2. Confirmar a instalação existente `8327184f_finance_v17`, versão 0.1.24, schema 10, configuração e armazenamento /data. Esse estado é informação operacional anterior, não reconsulta desta candidata.
3. Ter backup consistente recente, identificado e externamente recuperável de código/imagem 0.1.24, configuração atual e /data schema 10. Preservar disponibilidade verificável da versão anterior. Um backup antigo schema 9 não atende a esse rollback.
4. Definir janela e critérios de parada. Não recriar add-on, não usar outro slug/catálogo para presumir compartilhamento de dados e não alterar credenciais/Items/consentimentos para instalar diagnósticos.

O slug finance_v17, repositório e caminho finance-v17 permanecem iguais; a atualização futura usa o catálogo normal. A candidata não implementa bloqueio global de auto-update para terceiros. O proprietário declarou ser o único consumidor conhecido, premissa operacional que não prova ausência de instalações externas.

## Sequência futura pelo Supervisor — não executada

Reconfirmar a CLI efetiva e a versão oferecida. A família abaixo foi observada historicamente; não foi executada nem revalidada contra produção nesta D03:

```sh
ha apps info 8327184f_finance_v17
ha apps stop 8327184f_finance_v17
ha apps update 8327184f_finance_v17
ha apps info 8327184f_finance_v17
ha apps start 8327184f_finance_v17
ha apps logs 8327184f_finance_v17
```

Não executar start se o Supervisor já o tiver iniciado. Não operar antes da autorização. Publicação/refresh de catálogo não foram feitos; esta sequência depende de futura versão efetivamente disponibilizada.

Confirmar versão 0.1.25, API disponível, schema atual/esperado 10, migrations 10/10 sem execução adicional e opções preservadas. Não alterar a flag auto-sync nesta atualização. Com a preferência já habilitada por decisão do proprietário, observar somente o ciclo normal, sem coleta manual ou atualização remota adicional para obter logs.

Nos logs, buscar OPEN_FINANCE_DIAGNOSTIC. Institution é ITAU/SANTANDER ou OTHER para aliases não padronizados. Correlation_id é `ofdiag-` + primeiros 24 hex de SHA-256 do texto ASCII de of_sync_runs.id (UUID local de 32 hex), não um identificador bancário. Isso permite vincular ao histórico local sem expor Item/conta.

Para Itaú, observar resource/operation/category: consentimento sem itemId é diferente de Item de resposta divergente ou de conta fora do conjunto autorizado. Para Santander, TOKEN_ACQUISITION/AUTH_REQUEST_REJECTED é diferente de RESOURCE_QUERY/REPEATED_401 ou REQUIRED_RESOURCE_403. A categoria não prova a justificativa privada do provedor nem autoriza ação corretiva automática.

Ausência de evento não prova sucesso: pode não haver nova execução elegível, haver outro erro ou supressão do sink. O evento só é emitido para os dois códigos alvo, uma vez na fronteira do serviço. Não ativar debug HTTP, imprimir opções ou repetir sincronizações como substituto de evidência.

## STOP e recuperação coordenada schema 10

STOP em identidade divergente, build falho, versão errada, migration inesperada, indisponibilidade persistente da API, vazamento, seleção cruzada de bancos ou mudança de invariantes financeiras. Preservar logs sanitizados, estados e identificação do incidente. Não apagar banco, binding_hash, leases ou histórico.

O código 0.1.24 permanece estruturalmente compatível com schema 10, já que não há DDL novo. Para retirar apenas a instrumentação, coordenar parada e retorno à imagem/código 0.1.24 preservados, mantendo a configuração correspondente e o banco schema 10 consistente. Não restaurar banco antigo automaticamente se o problema for somente de código, pois isso perderia alterações legítimas posteriores.

Se houver incidente de dados que exija restauração, recuperar conjuntamente código/imagem, configuração e /data do mesmo backup schema 10 identificado, sob autorização explícita, aceitando perda das alterações posteriores à captura. Reconferir auto-sync e estado de inicialização antes de liberar o serviço. Não restaurar schema 9 sob código que migrará automaticamente no startup.

Sintaxe histórica de recuperação nativa: `ha backups restore <SLUG_VALIDADO_SCHEMA10> --app 8327184f_finance_v17`. Conferir a ajuda e o conteúdo do backup antes de qualquer operação; não executar placeholder. A restauração real pelo Supervisor não foi ensaiada nesta etapa. Downgrade isolado de código não substitui recuperação coordenada em caso de incidente de dados.

## Gate de publicação

Exigir build ARM64 independente, regressões e segurança PASS, oito hashes preservados, árvore de escopo fechado, versão consistente, ausência de dados sensíveis e plano de rollback. O commit local não implica autorização de push, PR, merge, tag, release, catálogo ou instalação. Não reutilizar a identificação 0.1.25 para bytes diferentes depois de uma eventual publicação sem nova análise.
