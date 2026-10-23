# Configuração local do Open Finance / Pluggy

Candidata experimental 0.1.23-open-finance.1, schema 10, baseada na distribuição 0.1.22-open-finance.1. Python 3.12.7,
oauthlib 3.3.1 e dados Unicode13 fixados; consulte os notices distribuídos
em `src/finance_v2/UNICODE13_NOTICES.md` e seu manifesto de integridade.
O startup aplica migrations antes de iniciar API e scheduler financeiro.
Publicação restrita à branch de revisão; instalação no Home Assistant não foi executada nem autorizada.

A integração é opcional e vem desabilitada. Este pacote em desenvolvimento
não autoriza conexão bancária real, implantação ou migration em Production.
API/UI, OAuth e scheduler financeiro continuam funcionando sem Pluggy.

## Fase A — interface e privacidade global

O olho no cabeçalho oculta/exibe valores em toda a interface, sem recarregar
a página. Sem preferência anterior, os valores começam ocultos como
`R$ ••••••`. A preferência `finance-v17:money-visible` fica no localStorage
do navegador; somente `true` exibe valores. Não altera opções do add-on,
respostas da API ou registros financeiros. Não é criptografia nem controle
de acesso: os dados continuam na memória, nos formulários e na API.

Open Finance possui Visão geral, Fluxo, Cartões, Ativos, Crédito e Conexões. Fluxo preserva
filtros e paginação; Conexões reutiliza o catálogo e histórico existentes.
Saldos, limites, faturas, posições, movimentações de investimentos e empréstimos
podem ser consultados no staging após coleta manual do cache autorizado. Categorias
bancárias são preservadas. Não há total patrimonial consolidado ou retorno calculado:
moedas, possíveis sobreposições e completude histórica não são presumidas.
Abrir as abas não inicia sincronização bancária ou conciliação oficial.

A release mantém as migrations 001–009 sem mudanças e adiciona a 010 exclusivamente
para staging. O startup existente executará 9→10, ou 8→9→10, conforme o estado
efetivo. Não atualizar antes de backup consistente e recuperação coordenada aprovados.
Downgrade de código não reverte schema. Estado atual e backup devem ser reconfirmados;
nenhuma migration foi executada em banco operacional nesta preparação.

## Cobertura ampliada e coleta manual

Abrir as telas consulta apenas o staging. A ação “Consultar cache” exige confirmação
e usa a configuração privada existente por instituição; não atualiza a instituição.
Pode emitir chave temporária POST /auth. Saldo em tempo real, SCR/Bacen e endpoints
de movimentação financeira são bloqueados. Sincronização automática permanece falsa.

Cada recurso distingue não consultado, não autorizado, não disponível, vazio e zero.
Payloads são projetados por contrato, sem documentos/números completos ou URLs assinadas.
Omissões privadas ou de campos ainda não contratados são contabilizadas. Histórico e
NOT_SEEN preservam registros sem inferir exclusão ou proveniência F07 legada.
Consulte `docs/open-finance/FULL_COVERAGE_CONTRACTS.md` no repositório de distribuição.

Limitação preexistente: editar receita recorrente pode também abrir o diálogo
de materialização pelo handler legado. Isso foi reproduzido no baseline e
não foi corrigido nesta release; requer avaliação antes de uso operacional
desse fluxo. A qualificação da interface não certifica sua escrita financeira.

Esta preparação não exige backup adicional automaticamente. Antes de uma
instalação autorizada, avaliar se a proteção já aceita ainda corresponde ao
estado atual. Recuperação deve coordenar código, configuração e banco
compatíveis; não restaurar automaticamente um ponto antigo schema 8 sobre
uma instalação schema 9 com dados posteriores.

## Opções

| Opção | Padrão | Uso |
| --- | --- | --- |
| `open_finance_enabled` | false | Habilita as conexões Pluggy selecionadas para sincronização manual owner-only |
| `open_finance_auto_sync_enabled` | false | Reservada: true bloqueia startup com OPEN_FINANCE_AUTO_SYNC_UNAVAILABLE; não existe scheduler Open Finance |
| `pluggy_itau_enabled` | false | Seleciona Itaú, somente com integração geral habilitada |
| `pluggy_itau_client_id` | vazio | Client ID da aplicação Pluggy destinada a essa conexão |
| `pluggy_itau_client_secret` | vazio | Client Secret dessa aplicação; campo password |
| `pluggy_itau_item_id` | vazio | Item ID da conexão Itaú |
| `pluggy_santander_enabled` | false | Seleciona Santander, somente com integração geral habilitada |
| `pluggy_santander_client_id` | vazio | Client ID da aplicação Pluggy destinada a essa conexão |
| `pluggy_santander_client_secret` | vazio | Client Secret dessa aplicação; campo password |
| `pluggy_santander_item_id` | vazio | Item ID da conexão Santander |

Não substituir timezone, ui_token, external_clients ou oauth_clients existentes.
Para uso futuro autorizado, preencher cada banco com sua aplicação/item próprios.
Credenciais estruturais válidas não provam autorização ou conectividade bancária.
Nenhum token/API key vem embutido no pacote.

`/data/options.json` é lido no startup. O adaptador converte os presets de HA
em registry genérico `FINANCE_V2_PLUGGY_CONNECTIONS_JSON`, validado pelo mesmo
parser do backend. Itaú/Santander são opções de apresentação: o modelo interno
continua suportando outras conexões, sem novos campos específicos em Settings.

Flags devem ser booleanas. Com integração geral habilitada, cada conexão
selecionada exige Client ID, Client Secret e Item ID não vazios, sem espaços
periféricos ou caracteres de controle; limites são os do cliente canônico.
Incompletude bloqueia antes de migrations/API/scheduler, com diagnóstico
estático que identifica somente a conexão, nunca o valor informado.

Conexões desabilitadas são omitidas do registry: campos parciais/armazenados
não são utilizados nem exportados. Habilitação geral false produz registry
vazio, inclusive sobrescrevendo variável antiga herdada. Nenhuma conexão
habilitada também é estado válido. As opções e o histórico já importado não
são apagados. Alterações das opções são recarregadas em novo startup; não há
hot reload ou sincronização implícita após salvar/reiniciar.

## Segurança e limitações

O schema HA usa `password` para os dois Client Secrets, conforme o contrato
de configuração do Supervisor:
[Home Assistant — App configuration](https://developers.home-assistant.io/docs/apps/configuration/).
Não confundir esse tipo de campo com criptografia em repouso ou um cofre.
Configuração, editor YAML, backups e acesso administrativo ao host/Supervisor
podem disponibilizar os valores; proteger esses acessos e backups.
Client ID e Item ID são identificadores, mas também não aparecem em diagnóstico
ou consultas de conexões.

O helper `finance_v2.ha_pluggy_options` é transporte interno de credenciais:
seu stdout é capturado por command substitution no run.sh, sem impressão.
Não executá-lo standalone em terminal/log, ativar `set -x`, imprimir registry,
options.json ou environment, nem compartilhar dumps de processos.
Segredos permanecem em memória/environment dos processos que herdam a
configuração, como já acontece com credenciais do runtime; administradores
podem inspecioná-los. Não há proteção contra um host comprometido.
API keys Pluggy não são armazenadas nas tabelas de staging ou nas opções.

Consultas de conexões e imports são owner-only; não conceder acesso bancário
ao MCP, Hermes ou scheduler. POST por sessão exige CSRF; bearer UI utiliza a
autorização existente. Respostas e erros não retornam Client Secret/API key.

Não existe sincronização automática. A opção automática deve permanecer false.
O scheduler financeiro existente não foi transformado em scheduler Pluggy.
Não há conciliação, categorização inteligente ou criação automática de despesas,
receitas, cartões, faturas ou recorrências a partir dos imports.

## Implantação futura e rollback (não executados)

1. Obter autorização específica de release/deployment e, separadamente, da
   aplicação da migration 009 em banco real. O startup do pacote com registry 9
   executa migrations oficiais; configurar opções não substitui essa autorização.
2. Revisar versão/gates, sincronização pública byte a byte e build/ensaio ARM64
   em ambiente descartável. Este lote não é prova de build/runtime HA real.
3. Parar o runtime somente quando autorizado, criar backup consistente de todo
   `/data` (SQLite e configuração, protegendo segredos), e validar restauração
   em cópia antes de atualizar. Preservar configurações OAuth/UI anteriores.
4. Após implantação autorizada, começar com integração/auto sync false;
   conferir health, schema/histórico/checksums e funcionamento da aplicação.
5. Só com autorização bancária posterior habilitar conexão e solicitar uma
   sincronização manual owner-only; não usar GET como comando.

Rollback de configuração: desabilitar integração/auto sync e reiniciar somente
quando autorizado; isso impede chamadas futuras sem apagar staging/financeiro.
Rollback de pacote/schema exige parar processos e restaurar backup compatível
previamente validado: não fazer downgrade de user_version, apagar tabelas ou
rodar pacote schema 8 contra banco schema 9. Restaurar as opções correspondentes
e verificar health/OAuth antes de disponibilizar novamente. Nunca imprimir os
segredos durante backup, restauração ou diagnóstico.
