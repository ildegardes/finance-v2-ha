# Analytics: regras e limites atuais

A leitura OF-ANALYTICS/1 usa recursos PRESENT e não modifica staging nem lançamentos oficiais. Fluxos são movimentos brutos declarados, por produto e moeda; não representam receitas ou despesas econômicas. PENDING e POSTED são filtros separados.

A ligação TRANSACTION_BILL só é exibida quando registrada no staging com a identidade composta da transação. MATCHED comprova o vínculo com a fatura, não a natureza da transação nem o pagamento. Nenhuma ligação é inferida por valor, data ou descrição. Compras, pagamentos, estornos, transferências próprias, aportes, resgates e rendimentos mantêm classificação econômica NOT_ESTABLISHED e reconciliação UNRECONCILED até existir evidência específica suficiente. Totais econômicos permanecem indisponíveis.

Cada posição distingue data financeira, atualização do provedor, coleta e frescor conforme metadados da origem. Ausência de data financeira não é substituída pela data da coleta. Resumos com campos ausentes, moedas desconhecidas ou cobertura incompleta são qualificados como parciais. Zero e valor ausente são distintos.

O ranking representa saídas brutas elegíveis por moeda e produto; agrupa cinco categorias, outras e sem categoria antes da paginação. Não se trata de classificação econômica. Campos desconhecidos e dados indisponíveis exigem tratamento explícito pelo consumidor.

Este contrato permanece experimental: a matriz completa de classificação, cobertura de movimentações, filtros, testes de segurança e compatibilidade ainda não está concluída. Não utilizar como critério de liberação ou publicar como versão homologada.
