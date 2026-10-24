# Open Finance: contratos ampliados de staging

Candidata experimental 0.1.23-open-finance.1. Base publicada 0.1.22-open-finance.1,
commit a3dc38375af13d8e9d40402538bb02f1d238a334. Schema candidato: 10.

## Recursos de leitura em cache

Referência oficial recuperada pelo MCP Pluggy em 23/10/2026. Cada operação abaixo
tem contrato versionado em `src/finance_v2/pluggy_coverage_contracts.json`, verificado
por SHA-256 na importação da aplicação. O arquivo contém nomes, tipos e enumerações,
sem exemplos de credenciais ou registros bancários.

| Recurso | Operação oficial | Consulta e paginação |
| --- | --- | --- |
| Item, instituição, estado, produtos, qualidade e datas | [items-retrieve](https://docs.pluggy.ai/en/reference/Items/items-retrieve) | GET /items/{id}; somente Item explicitamente configurado |
| Recursos declarados pelo consentimento | [items-resources](https://docs.pluggy.ai/en/reference/Items/items-resources) | GET /items/{id}/resources; page/pageSize; vazio sem resourcesCollectedAt é NOT_COLLECTED |
| Consentimentos e permissões existentes | [consents-list](https://docs.pluggy.ai/en/reference/Consent/consents-list) | GET /consents?itemId; contrato não oferece page: rejeitar totalPages > 1 em vez de inventar parâmetros |
| Contas BANK/CREDIT, saldos e limites já coletados | [accounts-list](https://docs.pluggy.ai/en/reference/Account/accounts-list) | GET /accounts?itemId; conferir total/totalPages; não utiliza /balance |
| Transações e metadados de parcelas/pagamentos | [transactions-list-by-cursor](https://docs.pluggy.ai/en/reference/Transaction/transactions-list-by-cursor) | GET /v2/transactions?accountId; cursor next vinculado à conta; ciclo/escopo divergente rejeitados |
| Posições, valores, quantidades e taxas informadas | [investments-list](https://docs.pluggy.ai/en/reference/Investment/investments-list) | GET /investments?itemId; page/pageSize; moeda/tipo preservados |
| Movimentações de investimentos | [investment-transactions-list](https://docs.pluggy.ai/en/reference/Investment/investment-transactions-list) | GET /investments/{id}/transactions; page/pageSize |
| Empréstimos/financiamentos/obrigações | [loans-list](https://docs.pluggy.ai/en/reference/Loan/loans-list) | GET /loans?itemId; pagamentos, saldo devedor, juros, parcelas e encargos contratados; sem paginação inventada |
| Faturas e pagamentos já registrados | [bills-list](https://docs.pluggy.ai/en/reference/Bill/bills-list) | GET /bills?accountId; page/pageSize; somente contas CREDIT |
| Referências de extratos | [account-statements-list](https://docs.pluggy.ai/en/reference/Account/account-statements-list) | GET /accounts/{id}/statements; somente BANK; id/competência, sem baixar PDF ou persistir URL assinada |

Listagem global de Items (`GET /v2/items`) é opt-in na Pluggy e não é necessária para
consultar os Items configurados. A candidata não descobre ou agrega aplicações sem
escopo aprovado. As categorias continuam provenientes das transações; nunca são
associadas automaticamente às categorias financeiras oficiais.

### Exclusões obrigatórias

- `/accounts/{id}/balance`: saldo em tempo real, proibido neste contrato.
- `/items/{id}/scr`: a documentação descreve consulta ao Bacen por documento, com
  dependência de assinatura e possível cobrança. Não é tratado como GET passivo.
- Criação/atualização/exclusão de Items, consentimentos, webhooks, pagamentos,
  transferências, Connect tokens e renovação de autorizações: não implementadas.
- Identidade civil, documentos, números completos, participantes de pagamentos,
  códigos de autenticação, linhas digitáveis, URLs assinadas e credenciais:
  excluídos da projeção. Nenhum desses valores é registrado em diagnósticos.

## Semântica e qualidade

AVAILABLE, EMPTY, NOT_AUTHORIZED, NOT_AVAILABLE, NOT_COLLECTED, RUNNING e FAILED
são estados separados. Null, ausência de campo e zero permanecem diferentes.
Campos desconhecidos/privados omitidos incrementam omitted_field_count: não se
interpreta a projeção como cópia integral de payloads arbitrários. Expansões novas
exigem revisão do contrato e de seu hash, não aceitação automática de JSON.
Valores decimais podem ser strings decimais exatas na projeção HTTP, evitando
conversão binária e perda de precisão; o OpenAPI declara essa representação e null.

A coleta é manual e completa, com orçamento de 1.000 requisições de recursos por
execução, limite de páginas por coleção, sockets/retries já delimitados no cliente
e proteção contra cursores cíclicos. POST /auth é a única escrita remota permitida
pelo transporte e serve exclusivamente para chave temporária da aplicação.

`createdAtFrom` identifica transações criadas, não todas as alterações/exclusões.
Não se apresenta esse filtro como delta completo. A atualização é um full scan
idempotente: revisões apenas quando os dados/estado mudam. Uma ausência só é
marcada NOT_SEEN após coleção completa; não comprova exclusão no provedor e não
apaga histórico. Falhas de página não autorizam reconciliação por ausência.

Cada página salva projeções antigas e novas em uma transação SQLite conjunta.
Nenhuma requisição de rede ocorre dentro de transação de escrita. As leases e o
fencing existentes são reutilizados; página malsucedida reverte integralmente,
e execuções parcialmente concluídas permanecem diagnosticáveis e recuperáveis
por replay. Isso não é uma promessa de atomicidade da execução inteira.

## Persistência, HTTP e UI

Migration 010 apenas adiciona of_resource_records, of_resource_revisions e
of_resource_coverage, índices e FKs. As migrations 001–009 não mudam. Identidade
composta inclui conexão, recurso, pai e ID externo. Filhos têm FK para conta ou
posição do mesmo escopo; revisões e cobertura referenciam a execução correspondente.
Não há promoção para despesas/receitas/cartões oficiais. F07 legado e a flag global
de evidência permanecem inalterados.

Novas rotas owner-only:

- GET /api/v2/open-finance/resources: resource, connection_id, parent_id, state,
  type, currency, history=0/1, page e page_size=25/50/100; ordenação determinística.
- GET /api/v2/open-finance/coverage: progresso persistido e estados por coleção.
- POST /api/v2/open-finance/coverage-sync: apenas connection_id; confirmação manual;
  owner bearer ou sessão UI existente com CSRF. OAuth/MCP externo não ganha acesso.

Abrir/navegar na interface só consulta o staging. O botão manual confirma a ação
antes de emitir POST. Visão geral, Fluxo, Cartões, Ativos, Crédito e Conexões mantêm
o aviso de staging. Filtros F01–F07 e paginação do Fluxo continuam no contrato anterior.
As outras áreas têm seleção de recurso/instituição, paginação e histórico observado.

Não existe total patrimonial automático: moedas e sobreposições entre saldo bancário,
aplicação automática e posições não foram demonstradas. Taxas/rentabilidades exibidas
são informadas pelo provedor; não são calculadas a partir da variação do saldo.
O histórico de observações não é uma série histórica retroativa nem rentabilidade.
Sem moeda conhecida, não se inventa BRL. Valores e taxas sensíveis usam a privacidade
global, inclusive após respostas assíncronas. Não há gráfico que exponha dados ocultos.

## Limites de homologação

Nenhum Item real foi consultado nesta implementação. Cobertura Itaú/Santander,
cardinalidades, períodos e permissões atuais permanecem NOT_VERIFIED. Sandbox/mocks
não comprovam cobertura de uma instituição real. Acesso real e eventual expansão
de campos dependem de gate próprio; não foram incorporados dados bancários a fixtures.
