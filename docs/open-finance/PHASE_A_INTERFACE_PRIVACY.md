# Fase A — Interface Open Finance e privacidade global

## Escopo e baseline

Implementação local no repositório público `ildegardes/finance-v2-ha`, branch local `master` existente, sobre `f634d2b7ff9b6616ef2f02624027efb1ac066a99` (merge da candidata 0.1.21-open-finance.1). Nenhuma branch adicional, push, release ou operação no Home Assistant. O workspace privado Finance_V2 não foi alterado.

## Funcionalidades

- Olho no cabeçalho: alternância imediata, sem navegação, reload ou novas chamadas API.
- Preferência `finance-v17:money-visible` no localStorage: somente `true` exibe; ausência, valor inválido ou erro de leitura começam ocultos. Falha de gravação mantém a alternância em memória. Eventos storage propagam a preferência às outras abas da mesma origem.
- Módulo único privacy.js: formatação, projeção monetária, preferência e observação de renderizações. Valores ocultos são `R$ ••••••`. A projeção cobre texto, opções, títulos SVG, tooltips e nomes acessíveis. MutationObserver executa a projeção antes do próximo paint. Valores originais de texto ficam em referências fracas, não em atributos HTML criados para essa finalidade.
- Campos monetários preservam value e FormData. Enquanto ocultos, usam controle password e cobertura visual; ao exibir, recuperam o tipo original. Não salvam valores no localStorage. Diálogos nativos tornam o cabeçalho inerte enquanto abertos; a preferência global continua se propagando por storage.
- Prompts monetários nativos foram substituídos pelo diálogo DOM compartilhado moneyPrompt nas edições atuais e legadas. O valor original, cancelamento e resultado textual são preservados, sem exibição numérica obrigatória em modo privado. Nenhuma fórmula ou corpo de requisição foi alterado.
- Abas Visão geral, Fluxo, Ativos e Conexões, com roles, relações ARIA, foco e setas/Home/End. Fluxo conserva filtros, contrato, página de 25 e ordem recebida da API. Troca de aba não reinicia filtros/página.
- Visão geral informa o catálogo, sem inventar saldos. Ativos declara indisponibilidade do contrato. Conexões e as últimas 25 sincronizações reutilizam o catálogo; não há refresh bancário implícito.
- Datas bancárias em DD/MM/AAAA, sem deslocamento de data civil por timezone. Decimais bancários em formato brasileiro, preservando sinal e precisão sem conversão para ponto flutuante. Outras moedas mantêm seu código. Categorias preservam o nome original, sem tradução não validada. Contas exibem nome e instituição, não IDs externos.
- Avisos de staging, direção bancária, proveniência desconhecida e ausência de conciliação/promoção oficial preservados.

## Arquivos

Criados no produto:

- finance-v17/src/finance_v2/web/privacy.js
- finance-v17/src/finance_v2/web/privacy.css

Modificados no produto:

- finance-v17/src/finance_v2/web/app.js
- finance-v17/src/finance_v2/web/completion.js (somente import e substituição dos prompts monetários)
- finance-v17/src/finance_v2/web/index.html
- finance-v17/src/finance_v2/web/open-finance.js
- finance-v17/src/finance_v2/web/open-finance.css
- finance-v17/src/finance_v2/web/revenues.js (formatter legado delegado ao módulo central)

Criados para validação: tests/phase_a_ui.cjs, tests/run_phase_a.cjs e tests/verify_phase_a.cjs. Este documento é novo. Nenhum Python, contrato HTTP, config.yaml, Dockerfile, dependência, lifecycle, scheduler ou migration foi modificado.

## Validação executada

Windows, Node 24.22.1, Playwright 1.62.1 e Edge headless disponível localmente.

| Grupo | PASS | FAIL | SKIP | Limite |
| --- | ---: | ---: | ---: | --- |
| Integração frontend sintética | 33 | 0 | 0 | HTTP estático loopback e respostas API artificiais interceptadas; não é teste do backend financeiro |
| Regressões históricas de apresentação | 3 | 0 | 0 | Asserts JavaScript originais executados contra o checkout público; sem importar fixtures DB |

Os 33 cenários incluem nove telas financeiras com valores, cartões/calendário, máscara em formulário e FormData, diálogos, aria/title, renderização tardia e resposta API pendente, storage indisponível/inválido, propagação entre abas, navegação por teclado, paginação 25+25+13 sem duplicação, filtros combinados e limpeza, categoria original, sinal/direção, estados vazio/carregando/erro, larguras 360/390/768/1440 e alvos de 44px. Todos bloqueiam requests de página externos, acusam erros JavaScript e rejeitam mutações API. Os três controles finais cobrem o helper monetário, seu uso no fluxo real de recorrência e uma contraprova com o completion.js literal do baseline.

Regressões históricas: ações e estados financeiros proibidos, payloads de pagamento/edição e refresh filtrado; projeção de auditoria/correções; indicador de recorrência e layout em navegador. Asserts não foram relaxados; somente o cwd aponta para o produto público.

A suíte backend completa não foi executada: suas fixtures aplicam migrations, proibidas nesta fase. Não são skips transformados em PASS. Nenhum SQLite, migration, scheduler real, banco, Pluggy, credencial real ou HA foi utilizado. Não houve build ARM64 ou execução real pelo Supervisor nesta fase.

### Tentativas e rastreabilidade

- Primeira rodada: 25 PASS/1 FAIL, por ID de formulário incorreto no teste (`expense-form` versus `new-expense`). Corrigido apenas o seletor.
- Segunda: 28 PASS/1 FAIL. O teste tentava clicar no cabeçalho atrás de um dialog nativo modal, corretamente inerte. O controle passou a usar a alteração real de preferência por outra aba da mesma origem, preservando a exigência de atualizar o dialog aberto.
- Terceira e quarta rodadas completas: 30/30 PASS. A quarta ocorreu após conferir/restaurar bytes canônicos no checkout. Resultados anteriores permanecem preservados, não reclassificados.
- Revisão de cobertura identificou os prompts monetários fora da árvore DOM. Após substituí-los, a quinta rodada teve 31 PASS/1 FAIL: seletor de Cancelar ambíguo entre o novo diálogo e outro diálogo legado. A sexta usa o heading para selecionar inequivocamente o diálogo monetário e acrescenta contraprova de que o segundo diálogo já ocorria no baseline; 33/33 PASS. Nenhum assert de privacidade, payload ou proibição de mutação foi removido.
- Evidências finais: `G:\Codex\FinancePhaseAValidation-20261023-06`, incluindo TAP, JSON, hashes e screenshots exclusivamente sintéticos. Rodadas 02 a 05 e seus resultados permanecem preservados.
- Regressões históricas e conferência protegida: `G:\Codex\FinancePhaseARegression-20261023-01`.

### Integridade e EOL

O checkout possuía core.autocrlf=true herdado da instalação Git. Sete dos oito arquivos protegidos haviam sido convertidos por checkout para CRLF, apesar dos blobs Git continuarem corretos. Somente os bytes originais do baseline foram rematerializados nesses arquivos, após comprovar diferença exclusivamente EOL e SHA-256 canônico correto. Nenhum hash esperado foi alterado, nem foi criado diff de produto nesses arquivos. Evidência antes/depois em PROTECTED_IDENTITY.json, fora do repositório.

O verificador tests/verify_phase_a.cjs exige oito identidades exatas, no baseline, no índice Git e nos arquivos protegidos de trabalho; rejeita qualquer alteração de produto fora dos oito assets autorizados. Também executa diff --check e confirma auto-sync false. BUILD_LOCK.json continua sendo a evidência histórica da release-base, não um manifesto desta nova árvore UI.

## Reexecução local

Com Node e Playwright disponíveis (sem instalar dependências implicitamente):

```powershell
node tests/run_phase_a.cjs 'G:\Codex\FinancePhaseAValidation-NOVA-EXECUCAO'
```

O diretório de evidências deve ser novo. FINANCE_NODE_MODULES e FINANCE_BROWSER_EXECUTABLE podem indicar runtimes já instalados. O teste encerra seus próprios contextos/browser e servidor loopback. O verificador de integridade é executado sobre a árvore staged:

```powershell
node tests/verify_phase_a.cjs
git diff --cached --check
```

## Limites e atualização futura — NÃO EXECUTAR NESTA FASE

Privacidade é apresentação, não autorização, criptografia ou remoção dos dados recebidos. API, memória do navegador e valores dos formulários continuam disponíveis ao usuário autenticado e às ferramentas locais. Gráficos mantêm suas proporções. Não equivale a certificação WCAG nem a validação de todos os navegadores/leitores de tela; a qualificação executada foi Edge/Chromium desktop com viewports móveis, não dispositivo físico.

Limitação preexistente comprovada: a edição de receita recorrente pode também abrir um diálogo de materialização por propagação do evento ao handler legado. A contraprova carrega o completion.js original do baseline e reproduz o comportamento, sem escritas. Não foi corrigido nesta fase, para não alterar outro fluxo financeiro. O diálogo monetário novo é testado e cancelado explicitamente por heading, sem confundir esse diálogo adicional. Uma revisão específica desse fluxo é recomendada antes de homologação operacional; esta fase não certifica a execução financeira completa desse caminho.

Foi preservada a identificação 0.1.21-open-finance.1 nesta fase de interface. **Antes de distribuir, uma etapa de release autorizada deve atribuir versão nova e consistente ao add-on/servidor, atualizar manifestos e validar o pacote.** Não reutilizar um ZIP histórico ou publicar código diferente sob a mesma versão. Não há atualização nova disponível apenas por existir commit local.

Procedimento futuro, condicionado a aprovação de publicação e instalação, e à verificação do estado real:

1. Revisar o commit desta fase e a nova identidade de release; preservar o mesmo slug e armazenamento. Não exigir outra instalação ou novo backup nesta fase. A proteção anteriormente aceita só pode ser avaliada conforme o estado e as escritas ocorridas desde sua captura.
2. Publicar somente com GO específico. Publicar na master pode oferecer atualização aos demais consumidores; este commit não constitui autorização de push/merge.
3. No terminal HA, após GO operacional, atualizar catálogo, conferir versão disponível e atualizar manualmente a instalação existente:

```sh
ha store reload
ha apps info 8327184f_finance_v17
ha apps update 8327184f_finance_v17 --backup=false
```

Consultar apps info privadamente: pode conter opções sensíveis. Confirmar versão alvo e estado STOPPED antes/depois, conforme o plano operacional aprovado. `--backup=false` não cria uma captura adicional implicitamente e pressupõe a proteção previamente aceita ainda adequada.

4. START exige GO separado. Se o banco efetivo ainda estiver em schema 8, o startup da base Open Finance executará migration009 e o scheduler financeiro original; esta Fase A não os alterou, desabilitou ou executou. Não iniciar apenas para testar a interface sem esse gate.
5. Após início autorizado, validar autenticação, privacidade, filtros, dados e configuração. Manter Pluggy/auto-sync desabilitados até autorização específica. Se a atualização falhar, usar recuperação coordenada de código, configuração e banco prevista no plano operacional; simples downgrade não reverte schema9.

IMPLEMENTATION_STATUS=READY_FOR_REVIEW
GITHUB_PUBLICATION_EXECUTED=False
HOME_ASSISTANT_ACCESSED=False
MIGRATIONS_EXECUTED=False
PRODUCTION_DEPLOYMENT_AUTHORIZED=False
