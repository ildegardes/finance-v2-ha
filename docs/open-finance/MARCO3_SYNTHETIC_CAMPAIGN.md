# Marco 3 — campanha sintética

Base da campanha: WSGI real, SQLite criado em diretório temporário e provedor simulado em memória. Nenhuma credencial, conta ou chamada bancária real é utilizada. As imagens são geradas pela execução com `OF_SCREENSHOTS`.

| Requisito | Implementado | Testado | Evidência | Pendência |
|---|---|---|---|---|
| Múltiplas instituições | Parcial | Sim | `test_open_finance_integrated_ui.py`: três conexões, duas ativas e uma arquivada; seleção por instituição | Cobertura de todos os filtros e estados por instituição |
| Múltiplos cartões e faturas | Sim | Parcial | Integração: dois cartões e três faturas por conexão, incluindo fatura sem vencimento | Múltiplos períodos e vínculos em todas as combinações de UI |
| Faturas históricas | Consulta histórica | Parcial | `open_finance_domain.query_domain` consulta revisões; UI omite atalho histórico | `of_resource_link_revisions` não garante projeção da relação em cada revisão; ausência precisa de contraprovas e explicação visual |
| Vínculos MATCHED | Sim | Sim | Integração e `test_bill_filter_requires_scoped_proven_link`: vínculo válido, sem vínculo e conta incorreta | Cobertura de histórico |
| Filtros combinados | Parcial | Parcial | Integração: instituição e moeda USD em investimentos; teste analítico com data, conta e busca | Matriz completa nas três abas |
| Concorrência | Parcial | Parcial | `open_finance_product_concurrency_ui.cjs`: respostas fora de ordem por instituição; `test_gate_c6r.py` | Moeda, alternância de abas, falhas e estados intermediários |
| Cobertura parcial | Parcial | Parcial | Testes de valores ausentes e cobertura FAILED; fixture tem posição sem valor | UI e recursos indisponíveis por produto |
| Frescor | Parcial | Parcial | Integração verifica data financeira de 2025 e atualização de 2026 separadas | Cenários de stale e histórico incompleto nas três abas |
| Privacidade | Parcial | Parcial | Resumos ocultos nas três abas, expansão e alternância no navegador | Atributos acessíveis, estados intermediários e alternância durante carregamento |
| Acessibilidade | Parcial | Parcial | Navegação por setas, foco visível e contraste de aba selecionada automatizados | Ordem integral, contraste geral e árvore acessível; nenhum leitor de tela foi testado |
| Responsividade | Parcial | Parcial | Integração verifica largura do documento em 390, 768 e 1440 px | Inspeção sistemática de sobreposição e truncamento |
| Integração WSGI | Sim | Parcial | `test_open_finance_integrated_ui.py` e `open_finance_integrated_ui.cjs` | Erros e consultas históricas ampliadas |

Não há homologação completa, nem GO para o Marco 3. Valores econômicos permanecem não estabelecidos quando não há evidência confiável.
