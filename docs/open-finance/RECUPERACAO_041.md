# Finance V17 0.1.41 · Cartões, faturas e movimentações

A auditoria partiu da tag `v0.1.40-open-finance.1`, commit `32fe66a`, schema 16. As capturas e os testes usam contas, transações, valores e credenciais sintéticos. O ambiente do proprietário fica reservado para a homologação.

## Cartões

A `.38` consolidou a Visão geral. Na `.39`, o commit [`2f57040`](https://github.com/ildegardes/finance-v2-ha/commit/2f57040) vinculou a publicação do valor de cada cartão à mesma auditoria usada para incluí-lo no total atual. A `.40`, em [`2620674`](https://github.com/ildegardes/finance-v2-ha/commit/2620674), distinguiu `CONSENT_ITEM_MISMATCH` no diagnóstico, mantendo o bloqueio de apresentação. A aba Cartões seguia consultando a tabela de registros locais pelo caminho de produtos e mostrava os campos nativos e as faturas.

O perfil Meu Pluggy Personal verifica a identidade do conector, consulta consentimentos pelo Item configurado e descarta associações estrangeiras. A auditoria registra a divergência. A coleta separada de contas só grava resultados com Item e conta validados. O mesmo cenário em dois bancos sintéticos reproduziu o bloqueio dos quatro cartões na `.40`. O [guia Meu Pluggy Personal](https://docs.pluggy.ai/pt/docs/guides/meu-pluggy-personal-use) documenta o Item acessível pelo aplicativo e o consentimento do banco separadamente. A aplicação preserva essa separação e as guardas de associação. A origem das divergências no provedor, para os dois bancos do proprietário, permanece sem confirmação.

A `.41` usa os registros de contas de crédito e seus checkpoints para projetar o valor individual e consolidado. Para exibir uma posição preservada, exige vínculo local verificado, Item e conta compatíveis e conta observada na última coleta completa do escopo. O consentimento não confirmado mantém o saldo fora da posição atual. Quando os valores preservados têm cobertura completa e a mesma data financeira, a utilização compara o saldo e o limite daquela data.

Em contas reguladas, `balance` representa crédito utilizado para o titular, conforme a [documentação de contas](https://docs.pluggy.ai/pt/docs/products/accounts). Uma linha total identificada pode informar `usedAmount` e `limitAmount`. O saldo em aberto informado por um conector não regulado aparece como saldo em aberto quando o uso não está disponível. Faturas e pagamentos não alimentam a métrica. A consolidação conta uma linha compartilhada comprovada uma única vez. O diagnóstico recolhido oferece códigos e contagens, sem expor identificação de Item, conta, credencial ou valor.

## Movimentações

O commit [`1a94f14`](https://github.com/ildegardes/finance-v2-ha/commit/1a94f14) montou a paginação de Movimentações como um elemento `nav`. O CSS do menu lateral, introduzido em [`1f7e69d`](https://github.com/ildegardes/finance-v2-ha/commit/1f7e69d), aplicava regras genéricas a `nav`. Na `.40` com a resposta real do WSGI, o SQLite, a API e o DOM continham nove transações. No desktop, o paginador superior herdava posição fixa à rolagem e altura de quase toda a janela, empurrando as linhas para fora da primeira dobra. No mobile, o paginador herdava a transformação que recolhe o menu lateral.

A `.41` limita aquelas regras ao menu lateral. A paginação permanece no fluxo da página. Cada linha tem sua data e o teste de navegador confirma a presença física de uma linha na região visível da página. Uma falha de renderização mantém um diagnóstico sanitizado com retentativa. Uma resposta sem os itens correspondentes à contagem produz `MOVEMENTS_RESPONSE_INVALID`. Essa segunda condição foi simulada separadamente para testar o diagnóstico.

## Faturas

A lista apresenta **Fatura de cartão** e converte vencimento e fechamento em datas civis no resumo. Nos detalhes do produto, o horário e o fuso permanecem como recebidos. O formato da [API de faturas](https://v2.docs.pluggy.ai/en/reference/bill/bills-retrieve) permite informar a ausência da data de fechamento.

## Evidências e homologação

As [capturas sintéticas](../../artifacts/recuperacao-041) incluem a lista de cartões, faturas, a mesma resposta válida com nove transações antes e depois, a primeira dobra no desktop e a página no mobile. A pesquisa do navegador verifica descrições e valores, filtros, ordenação global, navegação, paginação, privacidade e ausência de exceções JavaScript não tratadas.

1. No Home Assistant, faça o backup do add-on e confira no catálogo a versão `0.1.41-open-finance.1`. A homologação pode ser feita sobre uma cópia do backup com coleta automática desativada.
2. Em **Open Finance › Visão geral**, confira separadamente Itaú e Santander. Compare saldo utilizado, limite, data e final mascarado com **Cartões** e com a observação equivalente no Meu Pluggy. Confirme que zero aparece como valor e que a posição preservada traz a referência. Compare posições de mesma data.
3. Abra uma fatura em **Cartões**. Confira vencimento, fechamento, pagamentos e movimentações vinculadas. Confira o fuso nos detalhes.
4. Em **Movimentações**, aplique o filtro que retornava nove registros. Confira visualmente as nove descrições, datas e valores. Repita em tela estreita e em privacidade total.
5. Se a divergência persistir, copie somente os códigos e contagens de **Diagnóstico de cartões** por instituição. Para Movimentações, compartilhe versão, tamanho de tela, contagens da consulta e das linhas visíveis, e o código sanitizado exibido. Referências, valores reais, tokens e identificadores do provedor ficam no ambiente do proprietário.
