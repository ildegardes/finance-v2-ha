# D08 — Finance V17 0.1.26-open-finance.1

## Decisão

**RELEASE_CANDIDATE_WITH_EXTERNAL_BLOCKER.** Correções locais demonstradas, pacote e build ARM64 preparados; Santander e Itaú reais continuam **NOT_VERIFIED**. O bloqueio externo é de autorização/evidência operacional, não prova de defeito ou recusa imputável à Pluggy. Nenhuma chamada bancária real foi executada. Não declarar a integração integralmente funcional nem afirmar que esta release resolverá o 401 Santander ou o Item divergente Itaú.

## Procedência e isolamento

- Repositório público: `ildegardes/finance-v2-ha`.
- Baseline exata: `bd8477e429fa8408c11b4b2d2b551666a2359a97`; árvore `4c70c5b29f9c315a32a19132b2e25de2c3a738c0`. Confirmadas por leitura GitHub e pelo clone novo; origin/master correspondia à baseline durante a preparação.
- Workspace novo: `G:/Codex/FinanceOpenFinanceD08-20261026-01/candidate`.
- Branch exclusivamente local: `codex/finance-v17-d08-0.1.26`.
- A confiança Git foi limitada a `git -c safe.directory=<este caminho>` por comando para o clone público explicitamente identificado. Nenhuma exceção global, ACL ou arquivo de configuração foi alterado para resolver ownership. Checkouts históricos e `G:/Codex/Finance_V2` preservados.
- O coletor D07-B2 não foi executado, modificado ou integrado ao produto. Aceite R1–R5, fonte privada, console e autorização de janela real não estavam comprovados.

## Correções demonstradas

1. **Concorrência de autenticação:** `PluggyClient.coverage_get` invalidava incondicionalmente o cache ao receber 401. Uma requisição antiga podia apagar a chave renovada por outra e provocar um terceiro POST /auth desnecessário. Teste com barreiras reproduziu 3 autenticações onde bastavam 2. A correção associa o 401 à chave efetivamente enviada, sob o lock existente. O padrão já utilizado em `_get` foi preservado; não há cache global nem exportação de chave.
2. **Código perdido na interface:** o endpoint de coleta retorna `run.error_code` em HTTP 502; o cliente web procurava apenas `error.code`. A correção recupera exclusivamente códigos conhecidos de runs FAILED/INTERRUPTED e apenas na rota de coleta completa. Não carrega payload, diagnóstico livre ou chave para a exceção. Contratos HTTP do backend permanecem idênticos.
3. **Progresso atrasado:** uma consulta de progresso já em voo podia sobrescrever o erro final com “coleções em andamento”. A tela deixa de aceitar progresso quando a operação termina. Teste reproduziu a sobrescrita e confirmou sua correção.
4. **Mensagens estáticas compartilhadas:** histórico e coleta usam vocabulário fechado para autenticação recusada sem causa confirmada, escopo incompatível, consentimento expirado/inativo, ação exigida pelo Item, comunicação e erro interno. AUTH_FAILED nunca é traduzido como “credenciais inválidas”. Não se oferece diagnóstico de invalidade sem evidência estruturada disponível; a resposta bruta do provedor continua descartada.
5. **Harness Windows:** o evento SQLite fornece caminhos bytes neste Python. Corrigido `str(path)` para `os.fsdecode(path)` somente no harness, mantendo a guarda de diretório sintético e acrescentando controles negativos. A primeira rodada 24 PASS/66 FAIL foi preservada no relatório de testes.

## O que permanece intacto

Guardas de Item, conta e consentimento; seleção por instituição; corpo e endpoint de auth; TTL local 6900 s; limite existente de renovação; retries do produto; contratos HTTP; paginação; binding; leases/fencing; staging; idempotência; OAuth/MCP; domínio financeiro; scheduler; run.sh; opções auto-sync e migrações 001–010. Não houve normalização de identificadores ou tentativa de aceitar Item divergente. Schema permanece 10.

A validação de escopo compara todos os arquivos de produto com a baseline, admite somente os dez arquivos previstos e verifica os oito protegidos. Controles negativos rejeitam alterações no wrapper, migration e domínio financeiro. Os oito hashes estão no manifesto interno do pacote e no relatório de testes. BUILD_LOCK e manifestos de releases anteriores não foram modificados.

## Testes e artefatos

Ver `D08_TEST_RESULTS.md` para comandos, casos individuais, falhas iniciais preservadas e rodadas finais. Testes reais de aplicação utilizam exclusivamente bancos novos e provedor falso. Network guard permite somente loopback nos testes HTTP. Contêineres ARM64 usam network none, raiz somente leitura, cap-drop ALL, no-new-privileges, limites de CPU/RAM/PIDs e tmpfs /data; nenhum volume do host ou porta publicada.

- Windows Open Finance/SQLite/workers/diagnóstico: 93 PASS (90 existentes e 3 controles da fronteira de fixtures).
- Windows domínio financeiro/receitas/scheduler: 48 PASS (45 existentes e 3 controles da fronteira).
- MCP versão/protocolo/autenticação: 6 PASS.
- Autenticação D08: 8 PASS no Windows; 8 PASS em ARM64 emulado.
- Interface D08: 7 PASS, incluindo perda de código e resposta tardia.
- Build ARM64 final pelo Dockerfile do add-on: `sha256:b23ed43e4e897e1574b70fb037d6f882d3b3d65a23c0185f931c1a1d2bcea8db`. Base/digest e quatro dependências com hashes preservados. Uma tentativa offline falhou por ausência da camada pip; o build posterior com dependências públicas passou. Nenhum acesso Pluggy foi permitido nos testes.
- Pacote: `../artifacts/finance-v17-0.1.26-open-finance.1-source-rc.zip`.
- SHA-256 do ZIP: `E0CE9C07D312ED9958AB747E9B002AF720BB3DAFC9F0C7035645B7F48B6EAD8B`.
- 87 membros, 255832 bytes; dois builds ZIP em memória byte-idênticos, CRC e correspondência de todos os membros aprovados. `MANIFEST.sha256.json` interno identifica 85 arquivos do add-on, repository.yaml, oito protegidos, versão e baseline; não contém autorreferência.

O SHA do commit local que contém estes documentos será entregue separadamente, evitando autorreferência. O ZIP contém apenas fontes do add-on, repository.yaml e manifesto próprio; não inclui .git, testes, SQLite, opções operacionais, backups ou evidências financeiras. Os testes financeiros históricos externos não foram copiados para este repositório público.

## Compatibilidade e limites

Slug local `finance_v17`, origem de catálogo, caminho finance-v17, porta 8766, armazenamento /data, arquitetura aarch64/amd64 e opções permanecem iguais. A identidade instalada `8327184f_finance_v17` depende da mesma origem de repositório; não instalar cópia por outro slug. Nenhuma migration nova/destrutiva. O validador exige que config, Dockerfile e __version__ mudem apenas no valor da versão.

Compatibilidade de atualização é **PASS estrutural e sintético**, não instalação real pelo Supervisor. Build/TERM/INT Docker ARM64 não homologam watchdog, UI móvel real, restauração Supervisor ou disponibilidade dos bancos. Nenhum build amd64 novo foi executado; não houve dependência nativa nova. O código roda na imagem ARM64 emulada, com verificações de bytes e schema documentadas.

## Riscos e próximo passo

- A autenticação Santander e a divergência de Item Itaú continuam sem causa externa comprovada. Não mudar credenciais, Item ou consentimento por suposição.
- A candidata corrige defeitos locais independentes; não converte sincronização interrompida em sucesso, nem promove registros oficiais.
- A publicação pública pode oferecer atualização a consumidores adicionais. A declaração do proprietário de único consumidor conhecido não prova inexistência de terceiros. Não há proteção global de atualização automática introduzida aqui.
- O diagnóstico real necessita autorização separada, orçamento limitado, fonte privada e aceite dos efeitos desconhecidos de nova emissão de chave. Não iniciar esse diagnóstico como parte de push/instalação.
- Antes de publicação: revisão humana do diff/commit e autorização explícita de push/PR. Antes de HA: autorização operacional independente, estado atual confirmado e recuperação coordenada schema 10 disponível.

```ini
GOAL=D08
IMPLEMENTATION_STATUS=PARTIAL
SANTANDER_STATUS=NOT_VERIFIED
ITAU_STATUS=NOT_VERIFIED
AUTH_LIFECYCLE_STATUS=PASS
SCOPE_GUARD_STATUS=PASS
REGRESSION_STATUS=PASS
ADDON_PACKAGE_STATUS=READY
UPGRADE_COMPATIBILITY=PASS
RELEASE_VERSION=0.1.26-open-finance.1
GITHUB_PUSH=NOT_PERFORMED
GITHUB_PR=NOT_CREATED
PRODUCTION_DATABASE_CHANGED=false
HOME_ASSISTANT_UPDATED=false
REAL_REQUESTS=0
FINAL_STATUS=RELEASE_CANDIDATE_WITH_EXTERNAL_BLOCKER
```
