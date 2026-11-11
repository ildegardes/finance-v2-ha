# Marco 4 — Progresso de Conexões

## Implementado e verificado

- Cartões de instituições usam o catálogo local: estado habilitada/desabilitada/histórica, contagem de contas/cartões identificados e última sincronização registrada. Contagens referem-se ao catálogo, não à cobertura financeira completa.
- Para conexão operacional, o botão abre o diagnóstico com a identidade exata e dispara somente consulta local. Conexões arquivadas permanecem visíveis sem seleção operacional silenciosa.
- Histórico, explorador técnico, coleta manual, reconciliação e manutenção permanecem montados em seções expansíveis; abrir Conexões não inicia operações de escrita.
- A integração WSGI usa SQLite temporário, três instituições sintéticas, e verifica consulta ao diagnóstico por identidade, preservação da arquivada e ausência de requisições de escrita Open Finance ao navegar. Capturas locais: `artifacts/synthetic-preview/conexoes-desktop.png` e `conexoes-mobile.png`.

## Limitações e próximos testes

- Estado de conexão é o estado de configuração, não comprovação de consentimento vigente nem frescor financeiro. Cobertura, recursos e datas financeiras continuam no diagnóstico; a visão resumida ainda não os consolida.
- Faltam casos integrados de falhas e recuperação por instituição, alternância rápida específica de Conexões, navegação histórica e operação administrativa sintética completa.
- Faltam acessibilidade integral, testes com leitor de tela, revisão financeira e homologação ARM64/Supervisor. O Marco 4 e o release permanecem NO_GO.
- Preparar runbook final apenas após validar em laboratório backup restaurável, atualização, integridade e rollback; preservar dados gerados após atualização. Nunca executar em produção sem autorização separada.

## Referências de execução

- `node tests/open_finance_connections_ui.cjs`
- `python -m unittest discover -s tests -p test_open_finance_integrated_ui.py` com `PYTHONPATH=finance-v17/src;tests`
- `node --test --test-reporter=dot tests/test_gate_c6r_ui.cjs` com `GATE_B_UI_FIXTURE` apontando para fixture sintética aprovada.
