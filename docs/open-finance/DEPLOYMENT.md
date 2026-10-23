# Open Finance 0.1.21 — opt-in, instalação e recuperação

Esta é documentação de revisão, **não autorização de instalação**. Não mesclar este
conteúdo no canal estável apenas por existirem testes locais aprovados.

## Canal e identidade

Estratégia de opt-in: manter a branch estável com a versão schema 8 e oferecer a candidata
apenas por adesão explícita ao canal de revisão. O Home Assistant aceita URL de repositório
com `#branch`, mas usa a URL completa para identificar o repositório/app. Logo, esse canal
tem outro slug completo, hostname e armazenamento; não é upgrade transparente do app
instalado na URL sem branch. [Documentação oficial](https://contributors.home-assistant.io/apps/guides/repository/).

Não reutilizar diretamente o `/data` do app estável, não compartilhar SQLite entre apps,
não supor que restore de um slug migre dados para outro, nem usar a mesma porta 8766 em
dois apps simultâneos. A adesão ao canal e eventual migração entre identidades exigem
aprovação e ensaio próprios. Não depender de `breaking_versions`, stage experimental,
nome prerelease ou changelog como barreira comprovada para instalações anteriores.

## Atualizar uma instalação existente no mesmo slug

É um caminho distinto do canal opt-in: o catálogo associado ao slug instalado deve oferecer
o commit aprovado. Enquanto a branch estável estiver antiga, `update`/`rebuild` do app
original não seleciona esta branch de revisão. Não editar metadados internos do Supervisor
para simular troca de repositório.

Publicar no catálogo estável poderá ofertar a versão também a outros consumidores. Não há
garantia de que desconhecidos estejam com auto-update desligado. Antes de qualquer oferta
geral, resolver explicitamente essa proteção/decisão. A configuração da instalação local
não constitui barreira global. Esta revisão não altera master nem publica versão nesse canal.

## Gates operacionais futuros

1. Reconfirmar privadamente versão, slug, estado stopped, armazenamento, schema, espaço e
   auto-update; não imprimir opções/credenciais. A CLI disponível deve ter sua ajuda conferida.
2. Aprovar o canal e a identidade, conferir commit/ZIP/hashes protegidos e reservar janela.
3. Validar a adequação temporal do backup consistente aceito, disponível fora do dispositivo,
   e o procedimento de recuperar **código anterior + configuração + banco schema 8**.
   SQLite extraído do mesmo backup é outra representação da captura, não captura independente.
4. Separar autorizações de publicação, instalação/update e primeiro start. Manter parado até
   o GO de start/migration. No código Supervisor consultado, update preserva stopped, mas isso
   não foi testado no Supervisor instalado; confirmar antes e depois, com contenção aprovada.
5. `run.sh` aplica automaticamente a migration 009 no startup, mesmo com Pluggy desligado.
   Primeiro start exige autorização explícita para schema 9. Não fazer restart repetido em erro.
6. Após start autorizado, verificar saúde/autenticação, história 001–009, integridade/FKs,
   preservação integral dos dados oficiais e seis tabelas OF inicialmente vazias. Contagens
   não substituem comparação de conteúdo. Conexão bancária real exige outra autorização.

## Rollback

Não fazer downgrade de código mantendo schema 9. Restaurar o conjunto correspondente ao
app anterior, preservando o estado pós-falha para análise e interrompendo todos os escritores
somente com autorização. Não sobrepor SQLite isolado a WAL/SHM de outra geração.

O restore parcial do app pelo Supervisor altera código/config/dados e pode iniciar o app
conforme o estado salvo no backup; revisar isso antes da execução. Não restaurar Core ou
outros apps por engano, nem fornecer senha em argumentos/logs. Conferir depois versão,
schema 8, migrations 001–008, integridade/FKs e invariantes financeiras, mantendo parado
até aprovação para reabertura. Não depender do conteúdo futuro da branch estável para
reconstruir a versão antiga: preservar imagem/fontes pinadas com o conjunto de recuperação.

STOP em divergência de identidade, schema, checksum, FKs, conteúdo financeiro, erro de
autenticação, start inesperado ou encerramento forçado não explicado. Não alterar dados
para acomodar o teste. Recuperação sintética aprovada não é restore real homologado.

## Limitações

O build/testes ARM64 são Docker/emulação, não rebuild/install/watchdog/restore do Supervisor
ou execução nativa no Raspberry Pi. O devcontainer oficial permite um Supervisor real, mas
requer privilégios/Engine interno e autorização/isolamento específicos; não foi iniciado.
[Guia oficial](https://contributors.home-assistant.io/os/supervisor/development/).

Base e dependências fixadas controlam os insumos, não fazem auditoria de vulnerabilidades
nem garantem disponibilidade futura de registries/PyPI. Uma atualização de Python/Debian
ou de bibliotecas precisa de revisão e testes, sem trocar hashes silenciosamente.
