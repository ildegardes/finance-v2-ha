# Finance V17 0.1.42 · Saldo em aberto, política por conexão e identidade visual

A versão parte da `0.1.41-open-finance.1` e mantém o schema 16. Os testes e as capturas usam um banco SQLite sintético.

## Saldo dos cartões

A `.41` já verificava o vínculo do Item e da conta e retornava `reported_balance` a partir de `balance` em cartões de conectores não regulados. A interface o colocava em uma segunda linha, enquanto o resumo e o KPI usavam a projeção de crédito utilizado. A `.42` promove o saldo em aberto à posição principal e usa a mesma projeção no KPI, na Visão geral e nos produtos. A auditoria de consentimento conserva as mesmas condições e não confirma autorização para novas coletas.

A soma usa o saldo nativo observado na última coleta completa e exclui valores de escopo incompatível. Zeros explícitos são incluídos. Os dias de referência e a cobertura parcial aparecem no resumo. Cada valor em moeda diferente da selecionada é convertido pela PTAX elegível para a data de origem. Contas duplicadas com a mesma identidade do Item são contadas uma única vez quando as observações concordam.

Faturas e pagamentos conservam sua apresentação. Para conectores regulados, a Pluggy define `balance` como crédito utilizado. Um escopo exclusivamente regulado mantém essa métrica com seu rótulo específico. Em escopo que inclui saldo em aberto, a análise de crédito utilizado fica nos detalhes. Limite consolidado e percentual exigem valores comparáveis e linha compartilhada sem duplicação. A [documentação de contas](https://docs.pluggy.ai/pt/docs/products/accounts) descreve as duas semânticas.

## Política por conexão

Na `.41`, o endpoint administrativo de coleta automática atendia somente conexões gerenciadas. As legadas seguiam apenas a configuração do add-on. A `.42` reutiliza esse mesmo endpoint, com sessão privada do proprietário, origem configurada, proteção CSRF e revisão concorrente. O card mostra a preferência individual, a política efetiva e a próxima coleta local. O registro das alterações legadas utiliza o histórico administrativo existente, vinculado à associação local da conexão. A ausência de uma alteração preserva o padrão anterior.

A política do add-on tem precedência. Em seguida, o estado ativo, a validação do vínculo e a preferência global determinam se a escolha individual pode produzir coletas. A preferência global pode ficar ativa mesmo com todas as conexões pausadas. Habilitar uma conexão nesse estado não inicia a coleta se a preferência global estiver pausada. Depois de habilitada, o agendador reconhece a alteração sem reinicialização e usa o último sucesso, o intervalo e as janelas de retentativa para calcular a próxima coleta. Os horários da Pluggy aparecem separadamente. A coleta manual continua disponível nas ações da conexão ativa. Conexões arquivadas ficam recolhidas, sem controles operacionais de coleta.

## Identidade visual

A composição preserva a geometria e as cores do SVG aprovado. O add-on fornece `icon.png` de 128 × 128 e `logo.png` horizontal de 256 × 100, conforme as [orientações do Home Assistant](https://developers.home-assistant.io/docs/apps/presentation/). A interface usa SVG local no cabeçalho e fornece favicon PNG de 16, 32 e 48 px, favicon SVG e Apple Touch Icon de 180 px. A autenticação e a interface autenticada referenciam os mesmos arquivos com a versão `v=042`.

## Homologação do proprietário

1. Faça o backup do add-on e confira a versão `0.1.42-open-finance.1` no catálogo. A homologação pode ser feita sobre uma cópia da base.
2. Em **Open Finance › Visão geral**, compare o KPI e os quatro saldos da lista com **Cartões** e o Meu Pluggy na mesma referência. Confira os dois zeros, o intervalo de datas e o estado preservado.
3. Em **Conexões**, abra a sessão administrativa privada já configurada. Confira se a política de coleta automática do add-on e a preferência global permitem coletas. Use **Habilitar coleta automática** no card do Santander ativo e confira a próxima coleta local. Reabra a aba e verifique a persistência. O histórico do Santander arquivado continua na seção recolhível.
4. Confira o ícone no catálogo, no cabeçalho e na aba de autenticação. Reaplique um filtro conhecido de Movimentações e confira as linhas e a paginação.

Veja as [capturas sintéticas antes e depois](../../artifacts/identidade-042).
