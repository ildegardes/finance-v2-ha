# Qualificação Finance V17 0.1.27-open-finance.1

Versão 0.1.27-open-finance.1; schema 11. Base pública: 3c4e131e6592a1155cb06910c5188bf2fd5793b2 (0.1.26-open-finance.1).

## Execuções locais desta release

- Windows AMD64/Python 3.10.0: 469 testes Python aprovados, sem skips; 147 verificações de interface/navegação/presentação aprovadas.
- ARM64/Python 3.12.7, código da imagem instalada: 472 testes aprovados, sem skips. Cobertura financeira, MCP/autenticação, Open Finance, workers, leases/fencing, encerramento, configuração do Supervisor e privacidade HTTP.
- Supervisor real 2026.10.5 em HAOS 18.3, kernel ARM64 próprio, QEMU full-system AArch64: build, instalação, inicialização, saúde, importação sintética, replay, histórico, interface, reinicialização e persistência aprovados. Supervisor supported=true e healthy=true. Não é um teste em Raspberry Pi físico.
- Atualização real no Supervisor isolado: 0.1.26/schema 10 para 0.1.27/schema 11; migration 011 aplicada uma vez. As 44 tabelas preexistentes e seus valores/relacionamentos foram preservados; integrity_check=ok, zero violações de FK. Migrations 001–010 intactas e nenhuma migration 012.
- Restauração coordenada realmente executada pelo Supervisor no laboratório: backup sintético do complemento recuperou código/imagem 0.1.26, opções e banco schema 10, sem reaplicar 011. Não usar apenas downgrade do código.
- Configuração real de entrada /data/options.json, com valores sintéticos: credenciais separadas por banco, valores antigos preservados na atualização, cenários ausentes/incompletos e auto-sync desativado. ADDON_CONFIG_CREDENTIALS=PASS; PC01_VAULT_RUNTIME_DEPENDENCY=FALSE.
- Os oito arquivos protegidos foram preservados. Fonte original, evidências bancárias privadas e travas históricas intactas. Nenhuma nova chamada Pluggy, leitura de cofre ou modificação de produção nesta homologação.

Imagem ARM64 homologada: `sha256:6f320b79e8bcdd3f81ff58e8bea22250d0639ca3286167c210ee48c356fcebf7`. A distribuição normal do Home Assistant continua usando build pelo Supervisor a partir do código do repositório, com imagem-base por digest e dependências por hash; o digest local de outra construção pode diferir. O arquivo ARM64 anexo é o artefato exato homologado, não uma publicação em registry.

## Limites e operação

A auditoria de consentimento pode permanecer FAILED/ITEM_ID_DIFFERENT e o geral PARTIAL, mesmo quando a coleta financeira pessoal terminou. A interface distingue esses resultados, sem validar consentimento estrangeiro. A causa externa não foi resolvida por esta release. Strict e sandbox mantêm suas políticas. Atualizações e ativação de sincronização no Home Assistant operacional ficam a cargo do proprietário.

As execuções acima são locais e no laboratório, não checks do GitHub Actions. Algumas suítes históricas usam adaptação documentada apenas das expectativas de metadados (versão/schema/lista de rotas); as assertivas financeiras não foram reduzidas. Compatibilidade ARM64 foi testada em Supervisor real em QEMU; não foi executado build Linux amd64 nesta release.

Consultar RELEASE_0.1.27.md para atualização, perfil pessoal e recuperação.
