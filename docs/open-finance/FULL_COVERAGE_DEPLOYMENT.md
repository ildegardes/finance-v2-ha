# Implantação futura e recuperação — candidata schema 10

## Estado e barreira de distribuição

Baseline GitHub verificada em 23/10/2026: master a3dc38375af13d8e9d40402538bb02f1d238a334,
versão 0.1.22-open-finance.1/schema 9. O estado instalado atual do Home Assistant
**não foi consultado**. Versão, schema, serviços, WAL/SHM, atualização automática,
watchdog e configuração efetivos precisam de inventário autorizado posterior.

A candidata 0.1.23-open-finance.1/schema 10 usa a mesma identidade finance_v17,
porta 8766, opções e armazenamento /data. Não é uma segunda instalação. A branch
de revisão não altera o catálogo master e não torna o update disponível normalmente.
stage=experimental descreve maturidade; **não é uma barreira contra auto-update**.
Não se usa breaking_versions como autorização ou bloqueio artificial.

Fundamento: [configuração oficial do app](https://contributors.home-assistant.io/apps/reference/configuration/)
e [identidade, atualização e persistência pelo Supervisor](https://contributors.home-assistant.io/apps/how-apps-work/).

Não fazer merge enquanto faltar barreira aprovada para consumidores públicos. Um
merge em master pode tornar a versão elegível para todas as instalações do catálogo,
inclusive auto-update de terceiros. Publicar outro slug/repositório não é atualização
in-place e não compartilha automaticamente os dados do add-on existente.

## GO/NO-GO anterior à primeira operação

Exigir: código e manifesto aprovados; build das duas arquiteturas; regressões sem
falhas; artefatos protegidos exatos; riscos Supervisor e cobertura real explicitamente
avaliados; canal aprovado; inventário atual; backup compatível e janela operacional.
Nenhuma dessas condições autoriza por si só comandos de escrita em produção.

As capturas históricas aceitas pelo proprietário continuam preservadas. Backup
nativo e SQLite extraído da mesma captura não são duas capturas independentes.
Sua existência não comprova restauração operacional, completude ou atualização.
Não se exige segunda captura direta do banco como substituto automático do mecanismo
aceito; exige-se uma referência consistente compatível com o estado que será alterado.

## Sequência proposta — NÃO EXECUTADA

1. Mediante autorização, inventariar com CLI Supervisor oficial a versão, estado,
   storage, configuração e disponibilidade de backup. Conferir comandos com `ha
   apps --help`/`ha backups --help` da instalação atual, sem adivinhar flags.
2. Aprovar janela, critérios de indisponibilidade, canal de distribuição e risco de
   atualização de terceiros. Não reativar serviços por implicação deste documento.
3. Obter backup consistente do add-on, código e configuração por procedimento nativo
   aprovado. Se envolver parada, watchdog ou outras alterações, autorizar cada ação.
   Preservar WAL/SHM; não copiar o arquivo principal de um banco ativo isoladamente.
4. Transferir/proteger a captura autorizada, registrar SHA-256, identidade e schema.
   Em cópia isolada, integrity_check, foreign_key_check e histórico/checksums devem
   passar. Registrar fingerprints integrais das tabelas oficiais e staging existente,
   sem divulgar registros. Confirmar acesso ao código da versão correspondente ao
   backup, independente de master.
5. Somente após autorização específica: promover a revisão aprovada, atualizar o
   catálogo pelo mecanismo oficial e solicitar update do add-on existente, mantendo
   slug e /data. Um canal paralelo não é substituto para esta operação.
6. Separar build de execução: não interpretar build aprovado em Docker como build/
   instalação homologados no Supervisor. Conferir comportamento da versão atual do
   Supervisor antes de depender de preservação da imagem anterior diante de falha.
7. Startup aplicará migration 010 (e 009 se ainda pendente). Conferir schema 10,
   histórico 001–010, integridade, FKs e igualdade integral dos dados preexistentes.
   Não considerar downgrade simples recuperação suficiente.
8. Validar autenticação UI, OAuth/MCP e scheduler sem habilitar Pluggy ou coleta
   automática por conveniência. Verificar privacidade, Fluxo e dados legados. Só
   coletar cache financeiro real mediante autorização/escopo separados e confirmação.

## STOP imediato

Hash diferente; versão/schema desconhecidos; backup sem identidade/integridade;
configuração ou storage divergentes; build falho; migrations inesperadas; histórico
inconsistente; diferença financeira; FK inválida; exposição de segredo; perda de
autenticação; sync automático; falha de startup/shutdown ou necessidade de KILL não
prevista. Preservar logs sanitizados e não repetir comandos indiscriminadamente.

## Atualização manual futura do mesmo add-on

Somente depois de promoção estável autorizada e backup/recuperação compatíveis:
Configurações → Apps → Finance V17 existente, slug completo
`8327184f_finance_v17`. Conferir versão disponível 0.1.23-open-finance.1 e sua
identidade; então solicitar Atualizar. Não instalar um app paralelo ou adicionar
outro repositório/slug supondo compartilhamento de /data. Conferir estado após o
build; iniciar apenas com autorização para executar a migration 010.

Equivalentes CLI propostos, **não executados**. Antes, confirmar comandos/flags
na ajuda da CLI instalada. Se divergirem, STOP; não imprimir respostas brutas que
possam conter opções/segredos:

```sh
# Leitura sanitizada, se --raw-json e jq estiverem disponíveis nesta CLI:
ha apps info 8327184f_finance_v17 --raw-json | jq '(.data // .) | {version,version_latest,update_available,state,auto_update,watchdog}'

# Escritas independentes, cada uma condicionada à aprovação operacional:
ha apps stop 8327184f_finance_v17
ha apps update 8327184f_finance_v17
ha apps start 8327184f_finance_v17
```

Entre stop e update: validar a captura consistente aprovada. Entre update e start:
conferir build, versão e mecanismo de recuperação. Estes comandos não incluem
criar/restaurar backup, alterar watchdog ou tocar no SQLite; tais operações exigem
procedimento e autorização específicos. Não assumir que o estado pós-update será
stopped ou running sem observação. A leitura de schema, integridade e fingerprints
de produção precisa de mecanismo apropriado e autorizado, não uma conexão improvisada.

## Recuperação coordenada

- Identificar a captura exatamente anterior à atualização e sua versão/schema.
- Sob nova autorização, impedir escritores e usar o mecanismo nativo de restauração
  do mesmo add-on, incluindo **código/imagem, opções e banco/sidecars consistentes**.
- Se a captura for schema 9, restaurar a versão compatível com schema 9; se for
  schema 8, restaurar seu conjunto compatível. Não impor um schema histórico
  diferente do backup efetivamente selecionado.
- Não abrir banco schema 10 com código antigo e presumir reversão. Não executar
  SQL de downgrade nem excluir manualmente as novas tabelas.
- Validar hashes, schema/histórico, integridade, FKs, fingerprints oficiais, UI,
  OAuth/MCP e serviços antes de retomar uso. Revogação de famílias OAuth, mudanças
  após o backup e operações perdidas exigem avaliação específica, sem replay cego.
- Só restaurar watchdog/boot e encerrar a janela depois de critérios aprovados.

Ensaio sintético local não equivale a restauração pelo Supervisor. Instalação/rebuild,
watchdog, backup/restore reais e execução ARM64 nativa continuam gates distintos.
Não houve acesso ao HA ou alteração dos backups existentes nesta implementação.
