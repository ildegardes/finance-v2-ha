# Finance V17 — Open Finance 0.1.24

Schema 10; migrations 001–010 preservadas. Atualizar de 0.1.23 não exige migration nova.
Python 3.12.7, oauthlib 3.3.1 e Unicode13 versionado. Notices em
`src/finance_v2/UNICODE13_NOTICES.md`. O slug continua finance_v17, porta 8766,
armazenamento /data e repositório público de distribuição permanecem os mesmos.

## Ativação sem sobrescrever preferências

O default `open_finance_auto_sync_enabled` é **true para opções novas**, mas
`open_finance_enabled` e as duas conexões continuam false em instalações novas.
Não há chamadas sem integração habilitada e credenciais/Item configurados.

**Atualização da instalação existente:** um false persistido é respeitado. O
Supervisor combina defaults com opções persistidas; mudar o default não habilita
silenciosamente esta instalação. Não há migração de opções, escrita em
/data/options.json pelo Finance ou acesso administrativo ao Supervisor.

Depois da atualização pelo proprietário, para a instalação já configurada e com
integração/conexões habilitadas, a ação adicional é abrir Configuração do add-on e
habilitar **open_finance_auto_sync_enabled**, salvar e iniciar/reiniciar quando
autorizado. Não alterar os Client IDs, Client Secrets ou Item IDs existentes.
O primeiro ciclo começa após a criação do servidor HTTP. Se a flag efetiva
permanecer false, **não haverá ingestão automática**. As opções são lidas no startup;
não existe hot reload. Não se exige recadastrar uma conexão válida.

| Opção | Default novo | Efeito |
|---|---|---|
| open_finance_enabled | false | Habilita a integração configurada |
| open_finance_auto_sync_enabled | true | Coleta periódica de cache, respeitando false persistido |
| pluggy_itau_enabled | false | Habilita o preset Itaú |
| pluggy_santander_enabled | false | Habilita o preset Santander |
| pluggy_*_client_id/client_secret/item_id | vazio | Aplicação/Item próprios de cada instituição |

Não presumir credenciais iguais. Opção incompleta afeta somente o banco correspondente,
com diagnóstico fixo OPEN_FINANCE_CONNECTION_INVALID_ITAU/SANTANDER. Nenhuma opção ou
credencial é apagada. Vínculo divergente com staging existente resulta em
CONNECTION_BINDING_CHANGED; não substituir Item ou apagar staging para contorná-lo.

## O que a sincronização faz

Um worker por conexão usa a mesma ingestão de `POST /api/v2/open-finance/coverage-sync`.
Configuração, hash do vínculo e escopo dos IDs são conferidos. O Item e os metadados
de recursos/consentimentos são lidos antes dos produtos. Autorização expirada,
revogada ou Item exigindo ação do usuário é registrada sem renovar consentimento.
Quando metadados de consentimento não estão disponíveis, não se inventa sua validade;
os endpoints e estados de cobertura do provedor continuam sendo respeitados.

São chamadas GET de cache e, quando necessário, POST /auth para chave temporária.
Não há atualização remota do Item, saldo em tempo real, SCR, pagamento, transferência
ou renovação de autorização. Dados podem estar desatualizados no provedor; ingestão
do cache não é comprovação de uma nova coleta pela instituição.

Após sucesso automático recente, o restart aguarda o intervalo restante de uma hora,
sem criar outra execução. Falha automática recente recebe backoff mínimo de cinco
minutos em restart; interrupções permitem retomada. Decisão e lease compartilham
transação SQLite. A ação manual continua disponível e auditada. Cada instituição é
independente; lease ativo impede sobreposição. Não há polling agressivo.

Chamadas automáticas usam timeout de socket de 2s e orçamento de execução de 120s.
Um I/O que não coopera é desacoplado da autoridade de persistência; sua resposta
tardia não pode gravar. Há no máximo uma chamada não resolvida por conexão.
Cancelamento finaliza como INTERRUPTED/AUTO_SYNC_CANCELLED. Se o banco recusar a
finalização, CANCELLATION_FINALIZATION_DEFERRED mantém recuperação pelo lease de
300s e fencing. Não se anuncia sucesso de uma coleta interrompida.

## Interface e verificação

As seis áreas consultam staging: Visão geral (contas/saldos), Fluxo (transações e
categorias), Cartões (contas CREDIT, limites/faturas), Ativos (posições/movimentos),
Crédito (empréstimos) e Conexões (Item, consentimentos, recursos e histórico).
Ao abrir ou trocar de área, os dados atualmente persistidos são consultados.
Não há promessa de atualização por push de uma aba já aberta.

Conexões mostra estado da última execução e cobertura. Conferir cada instituição:
SUCCEEDED não significa todos os produtos disponíveis. EMPTY, NOT_AVAILABLE,
NOT_AUTHORIZED, NOT_COLLECTED e FAILED têm significados diferentes; zero e ausência
não são equivalentes. Item OUTDATED pode fornecer cache antigo, identificado pelos
metadados originais. CONSENT_EXPIRED, CONSENT_NOT_ACTIVE, ITEM_REAUTH_REQUIRED e
ITEM_USER_ACTION_REQUIRED exigem revisão do proprietário, não sincronizações repetidas.

Não inferir saldos de transações, patrimônio consolidado, retorno histórico ou
proveniência F07 sem evidência. Revisões não são novas posições. NOT_SEEN preserva
histórico sem afirmar exclusão. Categorias originais são preservadas.
Nenhum registro staging é promovido para despesa, receita, pagamento, cartão,
fatura ou recorrência oficial. O scheduler financeiro permanece separado.

O botão de olho mantém a privacidade global: valores ocultos por padrão, preferência
localStorage e máscara R$ ••••••. Isso não é criptografia ou autorização; dados seguem
na API/memória. Não publicar screenshots com dados reais.

## Segurança e recuperação

Não imprimir options.json, environment, Client Secrets, API keys, Items ou números
completos. O stdout de ha_pluggy_options é transporte privado capturado pelo wrapper;
nunca executá-lo isoladamente em terminal ou com set -x. Campos password e backups
não substituem controle de acesso ao host. OAuth/MCP não recebe acesso owner-only
ao staging. Sessões de escrita continuam exigindo CSRF.

Antes de instalação em produção: verificar estado atual, proteção consistente
imediatamente anterior e recuperação conjunta de código, configuração e /data.
Manter cópia externa verificada e janela operacional. Nada nesta documentação
executa backup, parada, atualização ou sincronização.

Se houver falha, preservar logs sanitizados e o conjunto SQLite/WAL/SHM; não apagar
leases para fabricar sucesso. Restaurar versão e configuração compatíveis com o
mesmo banco. Ao voltar para **0.1.23**, restaurar auto-sync **false**: essa versão
rejeita true antes da API. Downgrade de código não é restauração de dados.
O backup antigo schema 9 não equivale a rollback de uma instalação schema 10.

Build e testes Docker/ARM64 emulado não são homologação Supervisor/HAOS real.
Consultar o relatório versionado em docs/open-finance/RELEASE_0.1.24.md para
evidências, limitações, gates e instruções operacionais propostas.
