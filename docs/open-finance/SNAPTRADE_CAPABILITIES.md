# SnapTrade Personal no Finance V17

O cliente instalado e inspecionado é o SDK Python oficial 13.4.4, com autenticação Personal e assinatura do próprio SDK. A allowlist do Finance V17 é fechada. Ela contém somente leituras de conexões, contas, saldos V2, posições unificadas e atividades. O transporte aceita o host oficial e métodos e caminhos previamente aprovados. A conexão precisa ter sido criada na SnapTrade pelo proprietário.

| Recurso | API e SDK 13.4.4 | Personal | Charles Schwab Read-Only | Uso na versão |
| --- | --- | --- | --- | --- |
| Autorizações e contas | `list_brokerage_authorizations`, `list_all_user_accounts` | Documentado | Conexão OAuth existente | Descoberta com validação na conta pendente |
| Saldos V2, caixa, poder de compra, margem | `get_account_balances_v2` | Leitura documentada | Caixa e valor podem ser reportados. Detalhes de margem dependem da conta | Campos opcionais. Poder de compra e margem ficam separados |
| Posições unificadas e metadados | `get_all_account_positions` | Leitura documentada | Posições, com fundos monetários incorporados ao caixa | Somente uma fonte de posições. Opções quando entregues pelo mesmo recurso |
| Atividades | `get_account_activities`, com offset, limite e datas | Leitura documentada | A documentação cita até quatro anos de retenção | Primeira e última data verificadas localmente. Cobertura depende da conta |
| Ordens recentes e históricas | API e SDK disponíveis | Sujeitas ao conector | Cobertura e permissões dependem do perfil | Consulta separada indisponível nesta versão |
| Lotes | Campo opcional em posições de títulos compatíveis | Depende do adicional habilitado na SnapTrade | Dependente de confirmação na conta. O custo médio pode vir zerado mesmo com posição | Aproveitamento somente quando já fornecidos. Nenhum adicional é habilitado |
| Série histórica de posições | A API genérica oferece histórico de saldo para alguns perfis | Dependente do perfil | Histórico de posições comparáveis não estabelecido | Snapshots prospectivos |
| Eventos corporativos, proventos, taxas, retenções | Tipos normalizados de atividades | Leitura documentada | Campo e granularidade dependem da conta | Tipos explícitos preservados. Valores bruto, líquido e retenção dependem de evidência |
| Refresh remoto, ordens de negociação, permissões e desconexão | Existem operações distintas | Dependem da configuração | Fora do fluxo de leitura | Ausentes da allowlist |

A data de atualização de uma posição vem da referência retornada pela API. A coleta local consulta o cache em intervalos independentes do provedor. Limites oficiais podem atuar simultaneamente por cliente e conta. A próxima tentativa é mantida no banco e a coleta continua nas demais contas quando o provedor identifica uma restrição por conta. A periodicidade de atualização da Charles Schwab e as lacunas na conta do proprietário ficam para homologação.

- [Guia Personal](https://docs.snaptrade.com/docs/build-with-ai.md) · [Autenticação](https://docs.snaptrade.com/docs/authentication-methods) · [Personal e Commercial](https://docs.snaptrade.com/docs/personal-vs-commercial)
- [Índice oficial](https://docs.snaptrade.com/llms.txt) · [OpenAPI](https://docs.snaptrade.com/openapi.yaml) · [SDK 13.4.4](https://pypi.org/project/snaptrade-python-sdk/13.4.4/)
- [Account Data](https://docs.snaptrade.com/docs/account-data) · [Integrações](https://docs.snaptrade.com/docs/integrations) · [Conexões](https://docs.snaptrade.com/docs/connections)
- [Atualização](https://docs.snaptrade.com/docs/syncing) · [Rate limiting](https://docs.snaptrade.com/docs/ratelimiting) · [Assinaturas](https://docs.snaptrade.com/docs/request-signatures)
- [Lotes](https://docs.snaptrade.com/docs/tax-lots) · [Schwab Read-Only](https://support.snaptrade.com/Schwab-Read-Only-4a4feaa69a1c831b9dda0190145c6dd9?pvs=21)

## Armazenamento e extensão

A migration 016 acrescenta tabelas de corretoras, contas, posições, saldo por moeda, atividades, checkpoints, observações patrimoniais, preferências, eventos sanitizados de coleta, credencial protegida e taxas históricas. Cada entidade de corretora usa uma chave local derivada de provedor e escopo. Ativos e atividades são identificados por conta e chave estável do provedor. Os registros antigos da Pluggy e os lançamentos oficiais continuam nas tabelas originais. O leitor de patrimônio normaliza as duas fontes na consulta, preservando a distinção entre uma carteira e um saldo bancário.

A coleta atualiza cada recurso por conta. Uma resposta de posições incompleta preserva a versão anterior. A lista de atividades usa upsert e progresso persistido. Registros ausentes em um recurso incompleto permanecem disponíveis para inspeção. Histórico e snapshots têm retenção local e acompanham o backup do banco. O arquivamento é local. A persistência armazena campos normalizados em vez de respostas brutas. Números completos de conta e identificadores de sessão bancária não entram no banco.

As cotações históricas usam a PTAX de fechamento de venda BRL por USD do Banco Central. A consulta envia exclusivamente o período de datas. A conversão de USD para BRL multiplica pela taxa. A conversão inversa divide pela mesma taxa. Usa-se a última taxa com data igual ou anterior à referência patrimonial, limitada a sete dias de defasagem. A interface mostra a taxa e a data. Valores em outras moedas permanecem no original. [Dados abertos do Banco Central](https://dadosabertos.bcb.gov.br/dataset/dolar-americano-usd-todos-os-boletins-diarios)

O Finance soma as posições elegíveis em cada moeda. O caixa informado fica em subtotal separado. Fundos marcados como equivalentes de caixa ficam fora das posições consolidadas. O valor total reportado pela corretora serve para conferência, assim como poder de compra e margem. A carteira sinaliza instituições coincidentes e múltiplas autorizações da mesma corretora. Use o filtro por conexão ou a política de exclusão confirmada para resolver sobreposições.

Atividades ambíguas podem receber uma regra explícita na Central de classificação. A regra corresponde à conta da corretora, ao tipo original e à descrição normalizada. O tipo original e a auditoria local são preservados. A apuração de TWR, MWR ou XIRR exigiria um histórico de posições e fluxos verificados, com reconciliação de aportes, retiradas e câmbio. Os snapshots desta versão mostram a evolução observada.
