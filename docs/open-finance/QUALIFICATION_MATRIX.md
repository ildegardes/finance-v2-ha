# PR 11 — matriz de qualificação

Os testes usam dados sintéticos. PASS em uma verificação não implica aprovação integral do marco. O teste real com leitor de tela e o Supervisor continuam pendentes; não publicar release.

| Área e requisito | Implementação e evidência | Lacuna / estado |
| --- | --- | --- |
| Marco 1: decimal, moedas, posições, fluxos, filtros e categorias | `open_finance_analytics.py`; `test_open_finance_analytics.py`, Gate B e CI | Cobertura dos cenários existentes aprovada; revisão financeira completa e contratos ainda pendentes. NO_GO. |
| Marco 1: classificação e reconciliação | Classificação conservadora e estado indeterminado nos testes de analytics | Nenhuma equivalência por descrição/valor; faltam evidências para toda a matriz financeira. NO_GO. |
| Marco 2: indicadores, contexto, paginação e filtros | `open-finance-flow.js`, `open-finance.js`; testes de visão geral, fluxo e WSGI sintético | Estados e combinações não exaustivos. NO_GO. |
| Marco 2: privacidade e concorrência | `privacy.js`, `query-generation.js`; testes de atributos, respostas atrasadas e alternância | Auditoria integral das seis abas pendente. NO_GO. |
| Marco 3: cartões, faturas, investimentos e crédito | `open-finance-domain.js`; componentes sintéticos e WSGI; navegação histórica de fatura não é inferida | Matriz funcional completa e acessibilidade manual ainda pendentes. Desenvolvimento/final NO_GO. |
| Marco 3: máscara neutra | Testes de privacidade e WSGI; capturas atualizadas | Cobertura das áreas e estados ainda não é integral. NO_GO. |
| Marco 4: instituições, autorização, histórico e arquivamento | 17 testes administrativos, testes de instituições e integração WSGI | Operações administrativas completas pelo navegador e todas as contraprovas integradas ainda pendentes. NO_GO. |
| Marco 4: cobertura, falha e recuperação | Integração WSGI simula HTTP 503, nova tentativa, escopo e ausência de escrita na navegação | Concorrência e histórico em todas as combinações ainda pendentes. NO_GO. |
| C6R: quatro instituições e reimportação | Campanhas sintéticas independentes Windows e Linux, 100 iterações por sistema, integridade e idempotência em cada uma | Falha anterior do CI não reproduzida; causa não estabelecida. Instrumentação sanitizada captura tipo, código SQLite e estágio em futuras falhas. NO_GO até investigação suficiente. |
| Interface responsiva | 36 capturas das seis abas em 390, 768 e 1440 px, valores visíveis/ocultos; verificação automatizada de ausência de overflow horizontal | São estados observados, não matriz completa de erro, vazio e detalhes expandidos. Inspeção manual integral ainda pendente. NO_GO. |
| Acessibilidade | Testes existentes de teclado, foco, contraste, rótulos e atributos privados | Leitor de tela real não executado; não declarar WCAG integral. NO_GO. |
| Supervisor / backup / rollback | `OCI_SUPERVISOR_EVIDENCE.md` documenta hashes e laboratório | Operação bloqueada por política; laboratório integralmente sintético e instalação da candidata ainda não comprovados. BLOCKED_BY_POLICY. |

## Reproduzir a campanha

Com `PYTHONPATH=finance-v17/src;tests` no Windows ou `finance-v17/src:tests` no Linux, execute `python tests/c6r_stress_campaign.py --iterations 100`. Cada linha JSON registra duração, resultado, erros reconhecidos, verificação de integridade/idempotência e, somente em falha, tipo/código/estágio sanitizados. Não registra mensagens de exceção, credenciais ou payloads. Os arquivos da campanha desta execução estão em `artifacts/c6r-stress/`. A campanha não substitui as contraprovas de FIFO, cancelamento e contenção em `test_gate_c6r.py`.

## Roteiro manual de leitor de tela

Em instalação sintética autorizada, registrar sistema, leitor e navegador. Com valores inicialmente ocultos, percorrer as seis abas por Tab/Shift+Tab e setas; confirmar anúncio de nome, aba selecionada, foco, expansão, carregamento, erro e alternativas dos gráficos. Abrir detalhes e filtros, alternar privacidade e confirmar que valores ocultos não são anunciados. Repetir em 390 px e registrar problemas, passos e resultados. Não usar dados reais. A inspeção da árvore acessível não substitui essa verificação.
