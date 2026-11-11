# Reversão seletiva do binding

A reversão é uma segunda ação administrativa, não automática. Usa a mesma configuração efetivamente carregada e o recibo privado da operação aplicada. Não restaura o banco inteiro e não apaga ou recria conexão, dados ou runs.

1. Manter auto-sync desligado e não iniciar nenhuma coleta Santander. Obter autorização e comprovar backup atual. Preservar os recibos em /data junto com o banco.
2. Na interface do proprietário, clicar em Verificar elegibilidade. Reverter última correção Santander só fica habilitado quando há exatamente um recibo aplicado e o conjunto Santander permanece igual ao pós-commit auditado. A operação aleatória exibida internamente não é um identificador bancário.
3. Marcar confirmação de backup, escolher Reverter e confirmar o diálogo. O desafio é separado, vinculado à sessão, expira e é de uso único.
4. Sob BEGIN IMMEDIATE, validar configuração, schema, integridade, ausência de runs/leases e o MAC do conjunto Santander. Derivar o binding invertido em memória com a função original e atualizar somente binding_hash com comparação do valor atual esperado.
5. Antes do commit, comprovar que Santander voltou exatamente ao estado anterior e todas as demais células permanecem iguais ao início desta reversão. Alterações legítimas de Itaú ou do financeiro manual feitas depois da correção são preservadas. Retornar REVERTED e verificar SWAPPED_BINDING_MATCH=MATCH. Isso restaura o bloqueio anterior; não inicia coleta.

Novo run Santander, qualquer novo dado/importação/alteração Santander, mudança da configuração ou recibo ausente/ambíguo bloqueia a reversão seletiva. Não sobrescrever alterações posteriores nem editar os MACs/hashes para permitir a ação. Nesse caso, parar e projetar recuperação específica, sem restauração integral automática. Uma reversão já confirmada pode retornar ALREADY_REVERTED sem novo UPDATE.

PREPARED e REVERT_PREPARED preservam a ambiguidade de queda de energia entre SQLite e fechamento do recibo. O estado é reconciliado somente por ação administrativa explícita e igualdade exata com os estados auditados. Em COMMITTED_AUDIT_PENDING, não presumir rollback. Recibos e banco devem permanecer juntos em backups privados.
