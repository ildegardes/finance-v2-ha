# Evidências sintéticas da 0.1.35

As capturas foram geradas por Playwright com o Finance V17, WSGI, SQLite e um provedor simulado. A captura de subtotal usa uma resposta sintética com um cartão sem saldo. As regras de consolidação foram verificadas separadamente no servidor com obrigações fictícias de duas instituições.

| Cenário | Capturas |
| --- | --- |
| Visão geral | [desktop](visao-geral.png), [desktop amplo](visao-geral-ampla.png), [tablet](visao-geral-tablet.png), [celular](visao-geral-mobile.png) |
| Perspectivas e reconciliação | [econômica e detalhamento](fluxo-ajustado.png), [bancária](fluxo-bruto.png), [Aplic Aut Mais](aplic-aut-mais-visao-geral.png), [qualidade dos dados](qualidade-dos-dados.png) |
| Cartões e posições | [quatro cartões](cartoes.png), [subtotal conhecido](cartoes-subtotal.png), [posições por instituição](posicoes-por-instituicao.png) |
| Histórico patrimonial | [posição e seletor](investimentos-com-historico.png), [histórico em formação](historico-em-formacao.png) |
| Movimentações | [filtros](movimentacoes-filtros.png), [ordem por data](movimentacoes-ordenacao-data.png), [ordem por valor](movimentacoes-ordenacao-valor.png) |
| Paginação | [25](paginacao-25.png), [50](paginacao-50.png), [100](paginacao-100.png), [250](paginacao-250.png), [500](paginacao-500.png) |
| Preferências | [sincronização](configuracao-sincronizacao.png), [privacidade](menu-de-privacidade.png), [valores ocultos](ocultar-valores.png), [privacidade total](privacidade-total.png) |
| Exceções | [sem registros](estado-vazio.png), [erro recuperável](estado-erro.png) |

## Desempenho

Consulta local do módulo de analytics em Windows x86-64, Python 3.10 e SQLite. O teste combina filtro de período, descrição e elegibilidade econômica com ordenação decrescente por magnitude e limite de 500 itens. O pico de memória é o conjunto residente do processo durante a campanha e inclui a preparação dos bancos sintéticos.

| Registros no banco | Elegíveis pelo filtro | Retornados | Tempo | Comandos SQLite | Pico do processo |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 119 | 60 | 60 | 0,042 s | 17 | 42,0 MiB |
| 500 | 250 | 250 | 0,040 s | 17 | 42,0 MiB |
| 5.000 | 2.500 | 500 | 0,308 s | 17 | 59,8 MiB |
| 20.000 | 10.000 | 500 | 1,256 s | 17 | 122,0 MiB |

A regressão do navegador reproduz separadamente as 119 movimentações sem o filtro de metade do conjunto. A página de 100 registros navega para 101–119, e a de 250 apresenta os 119 registros de uma vez.
