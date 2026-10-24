# Validação da candidata Open Finance ampliada

23/10/2026. Versão anterior publicada: **0.1.22-open-finance.1 / schema 9**.
Nova candidata: **0.1.23-open-finance.1 / schema 10**.
Branch de revisão: `codex/open-finance-full-coverage`, base
`a3dc38375af13d8e9d40402538bb02f1d238a334`.

**Validação técnica local: PASS. RELEASE_READY=BLOCKED para promoção estável.**
O código, testes, manifesto e procedimento estão preparados para revisão; a branch
de revisão não torna a atualização disponível no catálogo master do Home Assistant.
Commit e URL do Draft PR serão confirmados no encerramento da publicação autorizada.

## Implementação e fronteiras

Ampliação seletiva do cliente e do serviço existentes, não implementação paralela.
Há contratos para dez famílias de recursos de leitura em cache: Item/instituição,
recursos declarados, consentimentos, contas/cartões, transações, posições de
investimentos, movimentos de investimentos, empréstimos, faturas e referências de
extratos. Campos, paginação, exclusões e limitações estão em
[FULL_COVERAGE_CONTRACTS.md](FULL_COVERAGE_CONTRACTS.md).

Migration 010 adiciona três tabelas de staging e índices/FKs; 001–009 permanecem
byte a byte inalteradas. Identidades são compostas por conexão/recurso/pai/ID.
Páginas atualizam atomicamente projeções OF-L2 e ampliadas, com rollback integral
da página inválida. Leases/fencing existentes, retries delimitados, replay idempotente
e estados de qualidade preservam execuções incompletas sem excluírem histórico.
Não há atomicidade prometida para a execução inteira, promoção financeira ou backfill F07.

Seis áreas de UI: Visão geral, Fluxo, Cartões, Ativos, Crédito e Conexões. Consultas
ao staging, filtros/paginação e histórico observado são separados da ação manual
confirmada de coleta do cache. Valores numéricos sensíveis usam privacidade global.
Não se inventam patrimônio consolidado, moeda desconhecida ou retorno histórico.

## Resultados finais efetivamente observados

| Grupo | Ambiente | PASS | FAIL / ERROR / SKIP |
| --- | --- | --- | --- |
| Novos contratos, persistência, projeções, HTTP e migration 8→9→10 | Windows, Python 3.12.14, oauthlib 3.3.1 | 20 | 0 / 0 / 0 |
| MCP: versão exata 0.1.23 e protocolo 2025-03-26, autenticação e transporte | Windows, mesmo runtime | 6 | 0 / 0 / 0 |
| Interface real em navegador, API artificial; desktop/móvel, privacidade, abas e filtros | Windows / Edge headless | 38 | 0 / 0 / 0 |
| Regressões financeiras, HTTP, OAuth/refresh, scheduler e OF anteriores requalificadas | Windows, mesmo runtime | 258 | 0 / 0 / 0 |
| **Total desses grupos Windows** | Sem somar novamente subcasos | **322** | **0 / 0 / 0** |
| Lifecycle separado do wrapper publicado | Windows / Git-MSYS | 12 | 0 / 0 / 0 |
| Novos contratos + MCP + regressão histórica | Linux ARM64 emulado, Python 3.12.7, oauthlib 3.3.1 | 284 | 0 / 0 / 0 |

Os 284 ARM64 são 20+6+258; não incluem os testes de navegador nem uma execução
ARM64 dos 12 cenários de shell. A execução ARM64 durou 307,953 s, com rede none,
rootfs somente leitura, limites de CPU/memória/PIDs e apenas mounts de fontes/testes
sem dados reais e evidências. Terminou exit 0/PID 0 e o contêiner próprio foi removido.

**Rastreabilidade da última correção visual:** a regressão ARM64 usou a árvore de
produto `8e4b4842b426da245cf67b69e79ad1bdded2ece0`. Depois, uma linha em
`web/open-finance-coverage.js` deixou de herdar BRL em saldo estrangeiro sem moeda
própria. A árvore final é `43b705787d934d696b88fd14f68cef61f2753cce`.
Comparação integral comprovou **80/81 arquivos idênticos**, incluindo todo o backend,
migrations, dependências, configuração e os oito protegidos. O controle visual novo
e a suíte de navegador final passaram (38 casos); imagens finais foram reconstruídas
e novamente conferidas/executadas. Não se afirma que os 284 casos foram repetidos
sobre uma árvore com hash diferente: a aplicação da evidência de backend usa essa
identidade de componentes, explicitada no JSON de evidências.

### Build e runtime finais

- Dockerfile exato construído para linux/amd64 e linux/arm64, sem publicar imagem.
- Python 3.12.7 e oauthlib 3.3.1 conferidos em ambas as imagens; pip check PASS.
- **76/76 arquivos runtime** iguais ao manifesto em ambas; também foi rejeitada a
  presença de arquivos inesperados. O produto distribuído contém 81 arquivos.
- Oito hashes históricos preservados no working tree, blobs Git e pacote/runtime.
- Base por digest e as quatro dependências por hashes permanecem como na baseline.

Imagens finais:

| Arquitetura | Identidade local |
| --- | --- |
| amd64 | sha256:2ab3012f26b597c669ef159647b175a6adb5f06d3661fdab42eeb725f23bdaf1 |
| arm64 | sha256:922a375d44884f265dd296be33b7ee303832724419862f50969e019b2764d11e |

### API e scheduler reais, com banco novo artificial

Em cada imagem final: run.sh original, API e scheduler reais; nenhum volume,
configuração ou credencial de produção; rede desabilitada, sem porta publicada,
rootfs read-only e recursos limitados. Cada arquitetura passou por dois ciclos.

| Arquitetura | Prontidão inicial / reinício | Paradas | Preservação |
| --- | --- | --- | --- |
| amd64 | 2,313 s / 2,297 s | exit 0 / exit 0 | Schema 10, migrations 001–010, integridade ok, FKs zero, 35 fingerprints iguais |
| ARM64 emulado | 31,328 s / 26,796 s | exit 0 / exit 0 | Mesmas verificações, sem diferença financeira |

Não houve KILL requerido nesses ciclos. Os contêineres e volumes novos foram removidos,
com verificação de propriedade. Nenhum recurso preexistente foi parado/removido.
No teste sintético de filho resistente, KILL/137 e wrapper 124 são **o resultado
esperado de falha limitada**, não shutdown gracioso. Os outros erros espontâneos
continuam distintos de parada solicitada. Sete controles negativos do harness passaram.

### Migration e recuperação

Testes novos cobrem banco financeiro artificial populado, 8→9→10, reaplicação vazia,
falha intermediária em 010 com rollback para 9, SQLite/FKs e ausência de escrita em
tabelas financeiras. Coleta e replay preservam revisões e identidades; uma página
malformada reverte simultaneamente contas/projeções antigas e novas. Comparações
integrais verificam conteúdo e estrutura financeira, não igualdade física após DDL.

Ensaio adicional executou o **código exato da baseline a3dc383** para criar e recuperar
schema 9 sintético. Captura consistente por sqlite backup, configuração artificial
preservada, upgrade a 10 e rejeição do downgrade isolado; a recuperação do conjunto
compatível manteve fingerprints das 35 tabelas, integridade e FKs. A referência
permaneceu inalterada. **Não é restauração pelo Supervisor nem prova de backup real.**

## Requalificação e falhas preservadas

Os testes históricos privados não foram alterados nem publicados. Cópias descartáveis
registram 11 adaptações específicas: expectativas exatas de schema/migrations 9→10,
lista fechada de rotas com os três novos contratos e verificação do layout público de
um único add-on no lugar dos mirrors/wheel do monorepo privado. Mantidos/reforçados
hashes/comprimentos Unicode, Docker COPY, asserts financeiros, erros e isolamento.
Não houve skip/xfail, comparação genérica relaxada ou substituição do produto por mocks.

O harness delimita SQLite a fixtures novas, permite somente filhos Python dos testes
revisados e registra término/cleanup; a execução Linux acrescenta isolamento de rede
e mounts do Docker. Filhos em testes negativos podem terminar em erro esperado, sem
serem convertidos em sucesso artificial. Nomes hexadecimais de fixtures evitam que
uma sequência aleatória “v1” se passe por um caminho de configuração legado.

Ocorrências anteriores desta preparação não foram reclassificadas:

- Erro de sintaxe inicial na nova descrição HTTP, corrigido antes da validação final.
- Runtime auxiliar sem oauthlib; criado ambiente de teste próprio com dependências
  fixadas, sem modificar o Python global. A execução inicial em Python 3.10.0 com
  oauthlib 3.1.1 não é apresentada como validação do ambiente-alvo.
- Checkout com autocrlf converteu entradas históricas e bloqueou checksums. Blobs da
  baseline conferidos e rematerializados exatamente, sem atualizar hashes esperados.
  .gitattributes preserva os protegidos como bytes e fixa EOL dos demais. Git archive
  também mostrou conversão no primeiro ensaio de recuperação; o ensaio final usa
  diretamente blobs Git, não normalização de arquivos protegidos.
- Primeira execução de navegador: 27 PASS / 6 FAIL. Cinco falhas de Fluxo vieram do
  seletor de formulário após a inclusão de novos formulários, corrigido no produto;
  outra foi a confiança Git do novo worktree no harness. Não houve mudança global
  de safe.directory; a confiança foi limitada por comando ao worktree criado.
- Regressões históricas iniciais registraram 33 FAIL/4 ERROR, depois 29/8 e 4/3,
  antes de completar requalificação de schema/layout e suporte a processos filhos.
  A asserção de OpenAPI não tipado encontrou defeito real: os contratos foram corrigidos,
  não a asserção. Houve um WinError 10053 de conexão local em execução intermediária,
  sem causa isolada; não voltou nas duas execuções completas aprovadas. Não se declara
  esse evento como defeito do produto resolvido.
- Um erro de preparação do harness Popen/asyncio interrompeu descoberta antes dos
  testes; corrigido por observação via subclass, mantendo semântica e captura de exit.

Logs, resultados individuais, scripts e ledgers dessas tentativas permanecem nos
diretórios locais exclusivos da campanha. Evidências finais agregadas, identidades e
limites estão em [FULL_COVERAGE_EVIDENCE.json](FULL_COVERAGE_EVIDENCE.json). As fontes
históricas completas dependem do acervo privado do proprietário; não foram copiadas
para o repositório público. Testes novos, UI e MCP são distribuídos nesta revisão.

## Manifesto e publicação

[RELEASE_0.1.23_MANIFEST.json](RELEASE_0.1.23_MANIFEST.json) é próprio da nova versão;
o BUILD_LOCK histórico e os manifestos anteriores não foram reinterpretados ou
substituídos. O validador novo exige escopo fechado, paridade dos componentes
financeiros/OAuth/scheduler, configurações preservadas, checksums e whitespace estrito.
Manifesto vincula a árvore do produto; o commit que o contém vincula código e evidências
sem dependência circular. O pacote local é selado com o SHA do commit após o commit.

Apenas branch de trabalho/Draft PR estão autorizados. Não se criaram tags, release
estável, imagem em registry, segunda instalação ou operação no Home Assistant.

## Matriz de decisão e pendências

| Gate | Estado | Condição seguinte |
| --- | --- | --- |
| Código e testes sintéticos locais | PASS | Revisão humana do diff e contratos |
| Build Docker amd64/ARM64 + arquivos runtime | PASS | Não substitui instalação/rebuild pelo Supervisor |
| Preservação financeira/rollback sintético | PASS | Não comprova restauração do backup de produção |
| Cobertura Itaú/Santander e permissões atuais | NOT_VERIFIED | Acesso real com escopo/autorização próprios; sem exigir credenciais no chat |
| Supervisor, watchdog, recuperação e ARM64 nativo | NOT_TESTED | Avaliação/aceitação operacional explícita; nenhum laboratório criado nesta etapa |
| Encerramento muito precoce histórico | Limitação residual | Ensaios atuais reais pararam após prontidão; não resolvem retrospectivamente o evento 137 antigo |
| Patrimônio/retorno retroativo | NOT_ESTABLISHED | Contratos de moedas, sobreposição e dados temporais suficientes |
| Publicação estável sem atualização involuntária | BLOCKED | Barreira/canal aprovados para consumidores públicos |
| Estado/backup atual da produção e implantação | NO-GO nesta etapa | Inventário atual, captura compatível, recuperação, janela e autorização |

Não inferir indisponibilidade de produto de um banco a partir de mock, ausência de
acesso ou limite do cliente. SCR/live balance são exclusões de segurança; extratos
têm somente referências sem URL assinada/PDF. Incremental createdAt não é prometido
como feed de alterações/exclusões. Privacidade é apresentação, não criptografia ou
controle de acesso; payloads e valores originais permanecem na API/memória autorizadas.

Próximo passo: revisão do Draft PR e decisão explícita sobre distribuição/risco
operacional; só então preparar atualização do mesmo add-on com o procedimento de
[implantação e recuperação](FULL_COVERAGE_DEPLOYMENT.md). Nenhuma atualização foi executada.

```ini
LOCAL_TECHNICAL_VALIDATION=PASS
RELEASE_READY=BLOCKED
STABLE_PROMOTION=BLOCKED
MASTER_MODIFIED=False
REAL_FINANCIAL_DATA_USED=False
PRODUCTION_DATABASE_CHANGED=False
HOME_ASSISTANT_OPERATED=False
PRODUCTION_DEPLOYMENT_AUTHORIZED=False
```
