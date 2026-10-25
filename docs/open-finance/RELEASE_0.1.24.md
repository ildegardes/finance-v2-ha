# Finance V17 0.1.24-open-finance.1 — implantação controlada

Schema 10, sem migrations adicionais. Base pública: `7bec77f6dcff63f9a66f3c408d19c887febff690` (0.1.23). O manifesto desta release é `RELEASE_0.1.24_MANIFEST.json`; BUILD_LOCK e manifestos anteriores continuam históricos, sem reinterpretação. A árvore do commit contendo o manifesto vincula os artefatos à publicação.

## Comportamento e ativação

A API inicia independentemente do provedor. Cada conexão configurada e habilitada possui seu próprio trabalhador; um banco com erro não impede o outro nem a API. O mecanismo consulta dados já disponíveis na Pluggy, não atualiza Item, não renova consentimento e não consulta saldo em tempo real. Usa autenticação temporária e leituras autorizadas, com paginação, staging e revisões existentes. Os registros financeiros oficiais nunca são promovidos pelo auto-sync.

O novo default de `open_finance_auto_sync_enabled` é `true`, mas opções explicitamente persistidas prevalecem. **Um `false` existente permanece `false`.** As opções globais e individuais do Open Finance continuam necessárias. Nenhum segredo ou Item é criado, migrado ou substituído.

Na instalação do proprietário, depois de instalar a atualização, conferir a opção no formulário de configuração do add-on. Se continuar desabilitada, a única ação adicional de ativação é marcar `open_finance_auto_sync_enabled=true`, salvar e reiniciar o add-on pelo Supervisor. Essa ação deve ser executada pelo proprietário, não por este processo de publicação. Não usar sincronização manual para compensar uma opção desabilitada. Não recadastrar Itaú ou Santander. Se alguma conexão não estiver habilitada, vinculada corretamente ou autorizada, corrigir a pendência pelo fluxo próprio, sem presumir sua validade atual.

Uma execução automática recente bem-sucedida é respeitada no reinício (janela de uma hora). Falhas recentes têm proteção contra repetição por até cinco minutos; o agendamento normal é horário. Uma execução interrompida pode ser recuperada sem esperar essa janela. O intervalo não representa promessa de atualização dos dados pela instituição.

Item expirado, aguardando usuário, com erro de login ou consentimentos explicitamente revogados/expirados interrompe a ingestão com estado auditável. Ausência de evidência de consentimento não é prova de autorização; respostas dos endpoints continuam limitantes. Resposta vazia não significa saldo zero. Os seis painéis consultam staging ao abrir/navegar; não há promessa de push para uma tela já aberta.

## Encerramento e recuperação

A correção H06-R separa o transporte puro da persistência. Cancelamento impede que uma resposta tardia alcance o banco. Uma chamada não cooperativa pode continuar em thread daemon até retornar ou o processo sair; `IO_DETACHED` não comprova cancelamento recebido pela Pluggy. O trabalhador de ingestão possui prazo de parada. Falha ao finalizar o lease é auditável e utiliza expiração finita e fencing, sem declarar sucesso nem apagar histórico.

O wrapper publicado, scheduler financeiro, OAuth/MCP, lógica financeira e migrations 001–010 são preservados. Os oito arquivos protegidos mantêm identidade byte a byte. O servidor HTTP tem concorrência limitada; falhas do provedor não bloqueiam sua inicialização.

## Antes de atualizar

1. Confirmar instalação `8327184f_finance_v17`, versão 0.1.23, schema 10, armazenamento `/data`, opções atuais e auto-update desativado. Não imprimir opções ou tokens completos.
2. Definir janela e preservar um backup nativo consistente contendo add-on, configuração e dados atuais. Verificar identidade, integridade e cópia externa recuperável. Guardar código/imagem compatíveis da versão 0.1.23. O backup histórico `090ffe1d` era schema 9 e **não representa** rollback atual de schema 10.
3. Confirmar que o catálogo do mesmo repositório oferece 0.1.24. Não criar segundo add-on nem usar slug alternativo. A atualização do catálogo e os comandos abaixo são ações futuras do proprietário.
4. Parar controladamente antes da atualização. Em estado `error`, examinar logs e saída; não repetir stop/start indefinidamente, não apagar dados e não forçar conclusão.

Comandos futuros, usando a família `ha apps` já observada pelo proprietário (reconfirmar `--help` na CLI instalada antes de operar):

```sh
ha apps info 8327184f_finance_v17
ha apps stop 8327184f_finance_v17
ha apps update 8327184f_finance_v17
ha apps info 8327184f_finance_v17
ha apps start 8327184f_finance_v17
ha apps logs 8327184f_finance_v17
```

Não executar `start` se o Supervisor já tiver iniciado o add-on. A confirmação no catálogo instalado não foi feita por esta campanha; a publicação verifica somente os arquivos do repositório. Nenhum comando HA foi executado.

## Validação após atualização

Confirmar versão 0.1.24, API HTTP 200, schema esperado/atual 10 e migrations 10/10 sem aplicação nova. Dar tempo à emulação/lentidão sem ampliar timeouts do produto. Conferir opção efetiva e status por conexão, última execução e pendências de consentimento. `SUCCEEDED` de um banco não prova êxito do outro. Os vínculos bancários reais não foram consultados nesta campanha.

Conferir Visão geral (contas/saldos fornecidos), Fluxo (transações/paginação), Cartões (limites/faturas autorizados), Ativos (posições/movimentações), Crédito (contratos disponibilizados), Conexões (cobertura/consentimentos/histórico). Preservar privacidade global e ausência de contagem dupla. Zero registros, recurso indisponível e erro são estados distintos. Confirmar dados oficiais por invariantes e registros completos na ferramenta local autorizada, sem divulgá-los.

## STOP e rollback

Interromper se houver falha de build, identidade divergente, schema inesperado, migração adicional, API indisponível, inconsistência oficial, duplicidade ou isolamento quebrado. Preservar logs sanitizados e backup do incidente antes de qualquer recuperação. Não apagar leases RUNNING nem alterar SQLite diretamente.

Para recuperar, impedir novas tentativas de auto-sync, parar o add-on e restaurar **conjuntamente** versão/imagem 0.1.23, configuração correspondente (auto-sync false) e `/data` schema 10 de um backup identificado. A sintaxe historicamente observada é `ha backups restore <SLUG_VALIDADO> --app 8327184f_finance_v17`; conferir ajuda e conteúdo antes de executar. Não usar literal de exemplo como slug. Verificar versão/configuração/schema antes de liberar a API. Uma troca de código isolada não substitui recuperação coordenada. A restauração pelo Supervisor real não foi ensaiada e não se promete disponibilidade futura da imagem anterior.

## Evidência e limitações

Resultados individuais e hashes estão em `RELEASE_0.1.24_VALIDATION.json`. Os cenários operacionais usam a imagem ARM64 real sob Docker/emulação, com rede `none`, root filesystem read-only, limites de recursos e fixtures sintéticas. O provedor é simulado; não são homologação do Supervisor, consentimento bancário ou cobertura real dos Items.

Como verificação adicional do Gate D, a rotina exata de combinação de opções do Supervisor 2026.10.3 foi executada em fixtures com sua dependência deepmerge fixada. Defaults são combinados primeiro e valores persistidos os substituem; nenhuma configuração é escrita. Também foram verificados slug, porta, init, privilégios e preservação do caminho de atualização. Isso delimita o contrato de configuração, sem substituir instalação, watchdog ou restauração pelo Supervisor real.

Fontes oficiais: [opções](https://contributors.home-assistant.io/apps/guides/options/), [configuração](https://contributors.home-assistant.io/apps/reference/configuration/), [Supervisor 2026.10.3](https://github.com/home-assistant/supervisor/blob/2026.10.3/supervisor/apps/app.py), [ciclo de Item Pluggy](https://docs.pluggy.ai/en/docs/connections/item-lifecycle), [consentimento e expiração](https://docs.pluggy.ai/en/docs/guides/meu-pluggy-personal-use).

A declaração histórica do proprietário de ser o único consumidor conhecido é premissa operacional, não prova de inexistência de terceiros. O repositório público disponibiliza a atualização a qualquer consumidor; o auto-update local não protege terceiros. Preferências explícitas false são preservadas. Não há tag, release de binários ou imagem publicada automaticamente por esta alteração.
