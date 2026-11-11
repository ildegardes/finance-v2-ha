# Finance V17 — candidata 0.1.29-open-finance.1

Schema 12, com migração aditiva do registro de conexões. A instalação operacional depende de homologação e autorização.
O slug finance_v17, porta 8766 e persistência /data são preservados.

As seis áreas consultam projeções tipadas do staging, sem criar lançamentos oficiais.
Contas e cartões navegam para movimentos, faturas e referências de extratos;
posições navegam para suas movimentações. Dados ausentes/null/zero e cache
desatualizado são distintos. O histórico é de observações, não rentabilidade calculada.
Downloads de extratos e consolidação patrimonial não comprovada permanecem desabilitados.

GET domain e relations não autenticam na Pluggy nem coletam dados.
Coleta completa, reconciliação incremental e retomada exigem ação explícita do proprietário.
Incremental significa upsert/revisão das alterações numa varredura completa limitada;
retomada repete coleções idempotentemente, sem confiar em cursor antigo.
Consentimentos estrangeiros continuam rejeitados. O diagnóstico não autoriza ignorar a guarda.

O default de open_finance_auto_sync_enabled nesta candidata é **false**.
Isso não modifica opções existentes: uma configuração persistida true precisa de
decisão operacional explícita antes de qualquer futura inicialização.
Não iniciar esta candidata com configuração copiada da produção durante ensaios.

Detalhes: ../docs/open-finance/GATE_B_CONTRACTS.md. A recuperação de schema11
para schema10 exige restaurar juntos código 0.1.26, configuração e banco correspondentes;
trocar somente o código não reverte a migration. Backup/restore real pelo Supervisor
não foi executado no Gate B.

## Documentação histórica de 0.1.25 (defaults anteriores)

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

## Diagnóstico 0.1.25

Esta versão acrescenta somente eventos OPEN_FINANCE_DIAGNOSTIC para localizar
ACCOUNT_SCOPE_MISMATCH e AUTH_FAILED. Campos fechados identificam etapa, recurso,
categoria, status HTTP e correlação de execução local; não expõem Item/conta,
credencial, payload ou dados financeiros. Os códigos públicos e as guardas não mudam.
Opções, auto-sync, consentimentos e schema 10 continuam como na 0.1.24.
Não iniciar novas sincronizações para validar este diagnóstico sem autorização.
Procedimento e rollback: docs/open-finance/RELEASE_0.1.25.md no repositório.


## D08 — candidata 0.1.26-open-finance.1

A interface distingue recusa de autenticação sem causa confirmada, divergência de escopo, consentimento expirado/inativo, comunicação e falha interna. Não altere credenciais ou Item apenas por AUTH_FAILED. A guarda de escopo continua estrita; divergências reais Itaú/Santander dependem de diagnóstico autorizado. Nenhuma coleta inicia por abrir a tela.

Uma falha pode ocorrer após páginas confirmadas no staging; consulte histórico e cobertura antes de repetir. Nenhum resultado bancário é promovido a lançamento oficial. Não há migration nova. O cache de API Key continua em memória por cliente, com expiração e uma renovação por GET 401; respostas antigas não invalidam chave diferente recém-renovada.

Publicação e atualização requerem autorizações separadas. Preservar a instalação existente finance_v17, /data e configuração. Rollback de código para 0.1.25 é compatível com schema 10, mas incidente de dados exige recuperação coordenada com configuração e backup schema 10 contemporâneo; não usar backup schema 9. Os procedimentos detalhados acompanham D08_GITHUB_UPDATE_INSTRUCTIONS.md.
# Chave das conexões Pluggy gerenciadas

O add-on guarda as credenciais gerenciadas cifradas no SQLite e usa
`/data/pluggy-keyring.json` como arquivo de chave separado. O arquivo tem
permissão `0600` e pertence ao usuário efetivo do serviço. O provisionamento
cria a primeira chave somente quando a origem administrativa privada está
configurada e ainda não existem credenciais gerenciadas. Reiniciar o add-on
preserva a chave existente. A opção `pluggy_admin_origin` fica vazia por padrão.

Para administrar conexões no Supervisor, use uma conexão direta pela rede
privada. Em `/ssl`, instale um certificado dedicado
`finance-v17-admin.pem` e a chave correspondente
`finance-v17-admin-key.pem`. O certificado deve conter o endereço IP privado
no Subject Alternative Name e ser confiável no navegador. O Supervisor monta
`/ssl` somente para leitura. Na configuração do add-on, informe a origem exata,
por exemplo `https://192.168.1.10:8767`, e habilite o mapeamento da porta
`8767/tcp`, que vem desativado. Acesse `/app/` nessa origem e autentique-se
com o token do proprietário. Mantenha a porta TLS fora do Cloudflare Tunnel
e de encaminhamentos públicos. A porta HTTP 8766 continua atendendo as
rotas existentes, com a administração do registro bloqueada.

Em **Instituições Financeiras**, salve um rascunho e use **Verificar Item e
recursos** para conferir o Item e os recursos declarados pela Pluggy. A
verificação consulta apenas a primeira página de recursos e indica quando há
mais páginas. A ativação exige confirmação separada. A coleta financeira pode
ser iniciada manualmente após a ativação.

As regras de mapeamento de diretórios e portas são descritas na
[referência de configuração do Supervisor](https://contributors.home-assistant.io/apps/reference/configuration/).

Em caso de `CREDENTIAL_KEY_RESTORE_REQUIRED`, recupere o arquivo da mesma
geração do banco. Uma chave perdida não pode ser derivada dos dados cifrados.
O add-on mantém as consultas locais e as conexões legadas disponíveis enquanto
o acesso às credenciais gerenciadas falha com diagnóstico sanitizado.

Um backup que contém o banco e o arquivo de chave permite decifrar as credenciais.
Proteja o backup com criptografia e acesso restrito. Mantenha o material de
recuperação da chave protegido e fora de logs, repositórios e chamados de
suporte. Valide uma restauração em instância descartável com o banco e a chave
da mesma geração, confirmando integridade SQLite e leitura das credenciais
sintéticas. Para retornar a uma versão que só aceita o schema 11, restaure um
backup anterior à migração, após preservar os dados novos para conciliação.
Recibos pendentes da recuperação Santander da versão 0.1.28 precisam ser
reconciliados nessa versão antes da migração, pois seus fingerprints incluem
o schema 11.
