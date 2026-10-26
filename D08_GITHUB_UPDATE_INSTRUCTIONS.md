# D08 — Publicação e atualização futuras, não executadas

## 1. Revisão local

Checkout: `G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate`.
Branch: `codex/finance-v17-d08-0.1.26`. Base auditada: `bd8477e429fa8408c11b4b2d2b551666a2359a97`.

```powershell
Set-Location -LiteralPath 'G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate'
git -c safe.directory=G:/Codex/FinanceOpenFinanceD08-20261026-01/candidate status --short
git -c safe.directory=G:/Codex/FinanceOpenFinanceD08-20261026-01/candidate log -1 --format=%H
git -c safe.directory=G:/Codex/FinanceOpenFinanceD08-20261026-01/candidate diff bd8477e429fa8408c11b4b2d2b551666a2359a97 HEAD --stat
python -B tests/verify_d08_release.py
```

Exigir working tree limpa, SHA entregue e oito hashes corretos. A opção safe.directory é específica deste clone por comando, sem desabilitação global da proteção. Não alterar checkouts históricos.

## 2. Push e Draft PR — exigem autorização específica

Antes do push, reconfirmar a master remota. Divergência da baseline implica STOP para revisão; não fazer rebase/merge automático nem force push.

```powershell
git -c safe.directory=G:/Codex/FinanceOpenFinanceD08-20261026-01/candidate fetch origin
git -c safe.directory=G:/Codex/FinanceOpenFinanceD08-20261026-01/candidate rev-parse origin/master
git -c safe.directory=G:/Codex/FinanceOpenFinanceD08-20261026-01/candidate push origin HEAD:codex/finance-v17-d08-0.1.26
gh pr create --repo ildegardes/finance-v2-ha --base master --head codex/finance-v17-d08-0.1.26 --draft --title "Finance V17 0.1.26: correções locais de autenticação e diagnóstico na interface" --body-file D08_RELEASE_REPORT.md
```

Esses comandos não foram executados. Conferir SHA remoto, diff e checks disponíveis. Ausência de CI não equivale a PASS. Não marcar ready, mergear, criar tag/release ou habilitar auto-merge sem outra autorização. Merge na master oferece a versão pelo catálogo público; não há proteção automática de terceiros. A descrição deve manter explícito que Santander/Itaú reais não foram validados.

## 3. Pré-condições operacionais HA — outra autorização

Manter `8327184f_finance_v17`, origem `ildegardes/finance-v2-ha`, diretório `finance-v17/` e /data. Não usar um catálogo/slug novo para presumir preservação de dados. Não instalar o ZIP como segunda instalação.

Confirmar por leitura autorizada a versão instalada, disponível, estado, schema 10, opções/auto-sync e watchdog, sem imprimir segredos. Dispor de backup consistente e recuperação verificável da versão 0.1.25, configuração correspondente e /data schema 10. Reutilizar proteção existente somente se adequada ao estado atual; esta D08 não cria nem verifica backups reais. Não considerar antigos backups schema 9 equivalentes.

Rever efeito das tarefas automáticas já configuradas antes de autorizar o início; não mudar flags/credenciais como parte desta release. Definir janela, prazo de prontidão e responsável pela decisão. Em emulação os tempos estão no relatório; não transpor automaticamente esse prazo para HAOS.

## 4. Sequência futura na instalação existente

Sintaxe da família `ha apps` foi observada historicamente, **não reconfirmada na CLI atual nesta D08**. Primeiro consultar ajuda/versões por leitura, sob autorização de acesso. Comandos abaixo são proposta condicionada, não procedimentos já ensaiados pelo Supervisor:

```sh
ha apps info 8327184f_finance_v17
ha apps stop 8327184f_finance_v17
ha apps update 8327184f_finance_v17
ha apps info 8327184f_finance_v17
```

Somente avançar do stop se o encerramento efetivo estiver comprovado. STOP se build/update falhar ou a versão oferecida não for exatamente a aprovada. Não repetir update por tentativa e erro. Consultar estado após update: o Supervisor pode iniciar o app. Executar `ha apps start 8327184f_finance_v17` apenas se ainda parado e o início estiver expressamente autorizado. Não acionar sync manual para testar esta correção.

Validação: versão 0.1.26, API pronta, schema atual/esperado 10, migrations 10/10 sem nova migration; mesmas entidades financeiras e configuração; interface carrega o novo módulo, mantém privacidade/filtros e apresenta histórico sem dados sensíveis. Observar logs sanitizados sem imprimir opções. Testar uma coleta real exige autorização bancária distinta, não implícita na atualização.

## 5. STOP e recuperação

STOP diante de imagem/versão errada, perda de disponibilidade, migration inesperada, mudança de vínculo/escopo, evidência de exposição ou alteração indevida de dados. Preservar evidências sanitizadas; não apagar staging, leases ou binding_hash e não substituir credenciais/Item automaticamente.

Se for somente regressão de código, retirar a versão nova e retornar à imagem/código 0.1.25 previamente preservados sob autorização operacional. Como o schema permanece 10, não restaurar banco antigo automaticamente e perder alterações legítimas. Confirmar configuração e compatibilidade antes de iniciar.

Se houver incidente de dados, restaurar conjuntamente imagem/código 0.1.25, configuração e /data da mesma captura schema 10. Confirmar conteúdo/versão do backup, sintaxe atual e efeitos de início automático antes de executar:

```sh
ha backups restore <SLUG_DE_BACKUP_SCHEMA10_VALIDADO> --app 8327184f_finance_v17
```

Placeholder não é comando executável. Restauração real pelo Supervisor não foi comprovada aqui. Evitar reinício automático com código incompatível e aceitar explicitamente eventual perda das alterações após a captura. Não tentar desfazer migration por downgrade isolado; nenhuma migration nova é incluída nesta release.

**Push/PR, merge/publicação, operação HA e diagnóstico bancário são autorizações independentes. Nenhuma está concedida por este documento.**
