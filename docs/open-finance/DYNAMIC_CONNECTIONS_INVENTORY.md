# Gerenciamento dinâmico Pluggy

Base auditada: v0.1.28-open-finance.1 / 7fa6ce95e3553155e8c8b99116c4edfabefb0127, schema 11.

| Área | Pontos de integração |
| --- | --- |
| Bootstrap e opções | run.sh lê /data/options.json. ha_pluggy_options.py converte os dois perfis legados em FINANCE_V2_PLUGGY_CONNECTIONS_JSON. config.py e pluggy_config.py materializam Settings e PluggyConnection. |
| Cliente e escopo | pluggy_client.py autentica, renova a chave e limita tentativas. pluggy_coverage.py pagina e open_finance_coverage.py coordena a coleta e as políticas de recursos. pluggy_access_policy.py diferencia strict, pessoal e sandbox. |
| Identidade e concorrência | open_finance.py usa hash de Client ID e Item, adquire lease e cria run na mesma transação. open_finance_write.py serializa writers. open_finance_auto.py lê o snapshot inicial de Settings. |
| Persistência | Migrations 009–011 são a fonte das tabelas de staging, runs, revisões, cobertura, vínculos e checkpoints. O vínculo técnico parte de of_connections.id. IDs novos precisam respeitar PluggyConnection e manter IDs existentes. |
| Leituras e API | open_finance_http.py, open_finance_query.py, open_finance_domain.py, open_finance_presentation.py e open_finance_output_privacy.py leem Settings. As leituras históricas precisam incluir IDs arquivados sem incluí-los na lista de coleta. |
| Interface e segurança | api.py fornece sessão do proprietário, CSRF, Origin e roteamento. A administração Pluggy precisa de uma superfície privada, separada da consulta financeira existente. web/open-finance-coverage.js monta a recuperação específica do Santander. |
| Caso Santander | open_finance_recovery.py e open_finance_recovery_checks.py implementam uma correção estrita para o binding invertido. A nova substituição deve arquivar o ID antigo e criar outro. Recibos anteriores pendentes precisam bloquear a operação. |
| Backup e rollback | O schema é verificado por migrations.py no startup. A 0.1.28 rejeita uma migration desconhecida. O retorno exige ensaio do backup anterior, incluindo banco/WAL, opções, recibos e material criptográfico quando aplicável. |

A migration 012 introduz metadados administrativos e eventos em tabelas novas. As tabelas do schema 11 permanecem a fonte do histórico e nenhuma FK existente é reescrita. A configuração legada precisa ser incorporada de forma idempotente, com tombstones respeitados após reinício.

Para a validação, usar autenticação no servidor e consulta de Item conhecido, sem exigir listagem global de Items ou iniciar coleta. A Pluggy documenta que a listagem é opt-in e indisponível em certos planos pessoais. Referência: https://v2.docs.pluggy.ai/en/docs/connections/item
