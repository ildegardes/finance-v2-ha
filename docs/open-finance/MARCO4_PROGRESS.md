# Marco 4 — Progresso de Conexões

## Implementado e verificado

- Cartões de instituições usam o catálogo local: estado habilitada/desabilitada/histórica, contagem de contas/cartões identificados e última sincronização registrada. Contagens referem-se ao catálogo, não à cobertura financeira completa.
- Para conexão operacional, o botão abre o diagnóstico com a identidade exata e dispara somente consulta local. Conexões arquivadas permanecem visíveis sem seleção operacional silenciosa.
- Histórico, explorador técnico, coleta manual, reconciliação e manutenção permanecem montados em seções expansíveis; abrir Conexões não inicia operações de escrita.
- Os cartões consultam a cobertura por recurso da API existente, separada pelo identificador exato da conexão. Cada ponto de coleta mostra seu estado e data, sem converter contagem de registros em percentual. Falhas da consulta apresentam nova tentativa; respostas anteriores não substituem a seleção atual.
- A integração WSGI usa SQLite temporário, três instituições sintéticas, e verifica consulta ao diagnóstico por identidade, preservação da arquivada e ausência de requisições de escrita Open Finance ao navegar. Capturas locais: `artifacts/synthetic-preview/conexoes-desktop.png` e `conexoes-mobile.png`.

## Limitações e próximos testes

- Estado de conexão é o estado de configuração, não comprovação de consentimento vigente nem frescor financeiro. A data de coleta exibida não é a data financeira nem comprova atualização do provedor; estas continuam indisponíveis no resumo quando não há evidência no contrato.
- Faltam casos integrados de falhas e recuperação por instituição, alternância rápida específica de Conexões, navegação histórica e operação administrativa sintética completa.
- Faltam acessibilidade integral, testes com leitor de tela, revisão financeira e homologação ARM64/Supervisor. O Marco 4 e o release permanecem NO_GO.
- Preparar runbook final apenas após validar em laboratório backup restaurável, atualização, integridade e rollback; preservar dados gerados após atualização. Nunca executar em produção sem autorização separada.

## Referências de execução

- `node tests/open_finance_connections_ui.cjs`
- `python -m unittest discover -s tests -p test_open_finance_integrated_ui.py` com `PYTHONPATH=finance-v17/src;tests`
- `node --test --test-reporter=dot tests/test_gate_c6r_ui.cjs` com `GATE_B_UI_FIXTURE` apontando para fixture sintética aprovada.

## Verificação ARM64 preliminar

- Build local `linux/arm64` da árvore de trabalho, imagem `sha256:aa9fe94e8b932f837854daef84db8759f41269d85a38d27205a027aad5b08037`: importação e runtime `aarch64` confirmados.
- Em contêiner sem rede, banco SQLite temporário recebeu as migrações 1–12 e o endpoint WSGI de saúde respondeu 200 com schema 12 atualizado. Nenhum banco ou serviço de produção foi usado.
- Isto não qualifica inicialização, atualização, backup, rollback ou catálogo pelo Supervisor. O laboratório anterior estava parado na inspeção desta execução; não foi homologada esta candidata no Supervisor. Não publicar release enquanto os gates permanecem pendentes.

## Regressão desta alteração

- Analytics: 32; Gate B: 18; C6R Python: 8; autenticação: 8; privacidade de saída: 6; integração WSGI/SQLite e navegador: 1; C6R interface: 7; instituições: 10; conexões: 1 arquivo. Todos passaram na execução com suas dependências sintéticas configuradas.
- Uma primeira execução de C6R interface sem `GATE_B_UI_FIXTURE` falhou antes dos testes por ausência da fixture. A execução posterior com a variável correta passou; o erro não foi omitido nem contado como teste aprovado.
- A integração inclui três instituições sintéticas, histórico, cobertura indisponível e falha por recurso, verificação de identidade e ausência de escrita durante navegação. O teste isolado cobre erro de consulta, nova tentativa e resposta atrasada. Esses testes não substituem a matriz integrada completa solicitada.
