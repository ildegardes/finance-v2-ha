# Evidências da revisão de dependências — 23/10/2026

Candidata ainda não instalada/publicada no canal estável: **0.1.21-open-finance.1**.
Pai da revisão: `41361fbbd28d3f349e4679740bdf43fbd6fc2cd8`; baseline
`32a0d5858776e65d7a0acfcab0a80584baab1718`. O commit final é informado no Draft PR #2.

## Alteração mínima

Somente dois arquivos de build do app mudaram: Dockerfile e requirements-deploy.txt.
Base oficial fixada pelo índice SHA-256
`60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d`.
Seu config ARM64 é o mesmo do ensaio anterior:
`f5c5392dc59e48c69cc44052ea25634db038b6c4432686587d5033876702ec27`.
O índice inclui amd64 e arm64; o novo build executado foi ARM64 por emulação.

Mantidos gunicorn 23.0.0, tzdata 2025.2, oauthlib 3.3.1 e packaging 26.3, já observados
no build anterior aprovado. packaging passa a ser explícita. As quatro wheels universais
foram verificadas contra SHA-256 PyPI e instaladas com require-hashes/only-binary. Nenhum
extra foi habilitado; Python continua 3.12.7. Isso controla insumos sem upgrade funcional.
Não constitui auditoria de vulnerabilidades ou garantia de disponibilidade dos downloads.

Código Python/JS/CSS, OAuth/MCP, scheduler, configuração, migrations e oito artefatos
protegidos permanecem byte a byte idênticos ao pai. Documentos novos de revisão ficam
fora do contexto finance-v17 e não são incorporados à imagem como código de execução.

## Resultados efetivamente executados nesta revisão

| Grupo | Resultado |
| --- | --- |
| Build do Dockerfile exato, linux/arm64 emulado | PASS; Python 3.12.7, oauthlib 3.3.1; 22,047 s |
| Conteúdo runtime da imagem candidata | 69/69 arquivos exatos; pip check PASS |
| Regressão principal selecionada | 321 PASS / 0 FAIL / 0 ERROR / 0 SKIP; 542,954 s totais |
| Migration sintética 8→9 | 11/11 PASS, incluídos nos 321; rollback/reaplicação/FKs/preservação |
| Lifecycle | 12/12 PASS; erros espontâneos 1, resistente 124, TERM/INT 0 |
| Controles híbridos originais | 40 PASS preservados, mais 21 controles da revisão delimitada |
| pip real offline, válido/hash errado/dependência sem pin | 3/3 classificações corretas; dois negativos rejeitados |
| Recuperação coordenada código/config/banco | PASS sintético; retorno schema 8 com 35 tabelas oficiais idênticas |
| Autenticação/replay nas três fases integradas | Não autenticado 401; leitura/replay 200; pagamento único |
| ZIP produto reconstruído duas vezes | Bytes idênticos; 75 arquivos; oito protegidos preservados |

Os 321 IDs cobrem Pluggy artificial, staging/consulta, Unicode13/HTTP, configuração,
HTTP financeiro, OAuth/MCP e scheduler. Não são 321 testes mais 11 migrations: estes
11 são subconjunto. Cenário de filho resistente detecta KILL e código 124; não é
shutdown gracioso. Os três containers de aplicação real encerraram com exit 0 e sem
KILL observado. O runtime não teve rede externa, portas publicadas ou dados reais.

Imagem candidata local, não enviada a registry:
`sha256:d0065e3b11b1ddf3c7b5a479783da8df3baab0b8da584af22868be9d570a2bd3`.
ZIP revisado do produto:
`2F34EEE7F1813B3B961B0261C55892203D1E74BE0C3E771A9A1105EA3D986119`.
ZIP original preservado:
`2053AE69D827A1D7EB074FB404C1E5033A88DF48BA7BE94459AF752D1C193315`.

Preparação teve um erro do seletor de wheel, corrigido apenas no instrumental para
aceitar a tag universal py2.py3 de tzdata. Controle de digest foi reforçado para
recalcular o JSON OCI bruto. Evidências iniciais foram preservadas; não houve correção
de teste histórico ou do comportamento financeiro para obter aprovação.

## Riscos e autorização

Build/install/watchdog/restore pelo Supervisor e execução nativa no Raspberry Pi:
**NOT_TESTED**. Não houve novo ensaio visual de navegador ou acesso bancário. Recuperação
artificial não comprova restauração do backup real. Ver [procedimento e gates](DEPLOYMENT.md).

Prontidão técnica local: **READY_FOR_REVIEW**. Prontidão operacional: **CONDITIONAL/NO-GO
nesta etapa**, até decisão de canal, risco residual Supervisor/restore, janela e autorizações
separadas. O canal opt-in não é update in-place do slug estável. Não há aprovação para merge,
update, start ou migration em produção. O Finance V17 instalado deve continuar parado.
