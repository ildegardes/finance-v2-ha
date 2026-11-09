# Gate B — contratos da candidata local 0.1.27

Base pública 3c4e131e6592a1155cb06910c5188bf2fd5793b2 (mesma árvore D08). Schema10->11 somente em ensaios sintéticos. BUILD_LOCK e manifestos históricos não representam esta nova candidata e não foram regravados. Manifesto próprio no diretório de evidências do Gate B.

| Contrato aditivo | Operação |
| --- | --- |
| GET /api/v2/open-finance/domain?resource=... | OF-DOMAIN/1, projeção tipada paginada de staging, sem coleta externa |
| GET /api/v2/open-finance/relations | OF-RELATIONS/1, relações exatas e auditáveis entre transação e fatura |
| POST /api/v2/open-finance/domain-sync | Owner UI, CSRF em sessão cookie; body fechado connection_id/mode FULL, INCREMENTAL ou RESUME |

As rotas legadas continuam disponíveis. Novas rotas não são ferramentas MCP, não ganham autorização OAuth e não são acessíveis aos clientes externos. Erros sanitizados e dados do proprietário permanecem no limite de autenticação existente.

Recursos: item, resources, consents, accounts, transactions, investments, investment_transactions, loans, bills, statements. Cada DTO conserva identidade composta connection/resource/parent/external_id, observação, estado de registro, campos tipados, completude e frescor do cache. Identificadores técnicos são usados internamente para navegação; não aparecem no texto principal da UI. Identificador de resources não é convertido em ID de produto.

Campo VALUE/NULL/ABSENT/UNSUPPORTED distingue ausência de zero. MONEY/RATE/QUANTITY preservam representação decimal, sem conversão cambial ou rendimento calculado. Moeda estrangeira sem moeda própria não herda BRL. Datas civis não sofrem deslocamento; instantes preservam horário/fuso de origem. Arrays de juros, encargos, parcelas, garantias e pagamentos são componentes da revisão do pai, sem IDs inventados.

CollectionQuality separa COMPLETE/EMPTY/NOT_AVAILABLE/NOT_AUTHORIZED/NOT_COLLECTED/FAILED/INTERRUPTED e ausência de checkpoint (NOT_QUERIED). A última coleta completa é mantida diante de falha posterior. Completo não significa atualizado; statusDetail do provedor pode sinalizar STALE e execução parcial. A UI nunca soma cache, histórico e lançamentos oficiais como patrimônio.

011 cria quatro tabelas auxiliares sobre records/revisions/coverage de 010: of_resource_links, of_resource_link_revisions, of_collection_checkpoints, of_domain_sync_audit. Nenhuma tabela oficial ou migration histórica é alterada. Vínculos de fatura: MATCHED somente com referência e alvo na mesma conexão/conta; MISSING_REFERENCE quando billId está ausente; UNRESOLVED sem criar alvo fictício. Referência comprovada de outra conta é rejeitada.

FULL, INCREMENTAL e RESUME compartilham o coletor existente, leases, fencing e transação por página. INCREMENTAL não é promessa de delta remoto: detecta alterações por hash/upsert após varredura limitada. RESUME reaplica coleções, registra run anterior e não reutiliza cursor de cache mutável. NOT_SEEN só após coleção esgotada; não afirma exclusão no banco e não apaga histórico.

Consentimentos estrangeiros/ambíguos continuam falhando fechados. Projeção de histórico e diagnóstico é independente da aprovação de nova importação. Nenhuma mudança da política de confiança foi implementada. Persistem as condições opcionais já existentes do contrato D08, sem transformar 403 opcional em consentimento válido.

Extratos: somente metadados; URLs assinadas são omitidas antes da persistência. Não há rota de download. Nenhuma sincronização remota de Item, OAuth bancário, novo consentimento ou promoção a registros oficiais foi adicionada. Default auto-sync false para novas opções; valores operacionais existentes não são alterados.
