# Finance V17 0.1.22-open-finance.1 — preparação local

## Identidade e escopo

Repositório público: ildegardes/finance-v2-ha. Branch local existente: master.
Parent autorizado: `5fd21c75443891e13202c56bb79700dd1da730ea` (Fase A).
Base publicada da Fase A: `f634d2b7ff9b6616ef2f02624027efb1ac066a99`.
O SHA do commit desta preparação é obtido pelo Git, sem autorreferência no documento.

Os cinco arquivos de versão/documentação foram preservados exatamente como
deixados na tentativa anterior. Nenhuma mudança funcional foi acrescentada:
config.yaml, Dockerfile e __init__.py diferem somente na identificação da
versão; CHANGELOG.md e DOCS.md documentam a Fase A e suas limitações.

## Diagnóstico do patch anterior

O hunk anterior exigia uma linha em branco entre o assert da lista de arquivos
e `git('diff','--cached','--check')`. O arquivo real não contém essa linha.
Sua leitura binária confirmou 24 LF e zero CR no validador original; não foi
necessário converter EOL, restaurar arquivos ou alterar permissões. A nova
aplicação usou o contexto efetivamente existente e teve sucesso.

## Validador e manifesto

O validador mantém a base exata, diff --check, oito SHA-256 protegidos no
baseline/índice/working tree e auto-sync false. Admite exatamente os oito
assets já homologados mais os cinco metadados autorizados contra a base.
Contra o commit da Fase A, admite somente esses cinco metadados.

As três mudanças de versão são comparadas ao blob original após substituição
de um único marcador exato. Os dois documentos são vinculados a seus hashes
canônicos exatos. Todos os outros arquivos do produto, incluindo os assets,
precisam ser byte a byte iguais à Fase A, sem arquivos adicionados/removidos.
Migrations, autenticação, API, Pluggy, scheduler, dependências e lifecycle não
possuem exceções. Nenhuma opção genérica de bypass foi adicionada.

`RELEASE_0.1.22_MANIFEST.json` é um manifesto independente dos 76 arquivos do
produto, com SHA-256 de blobs Git canônicos e oito identidades protegidas.
Não inclui seu próprio hash nem presume um pacote ou imagem já construídos.
Os oito arquivos protegidos também exigem bytes exatos no working tree.
O BUILD_LOCK.json histórico permanece inalterado e continua descrevendo
somente a release 0.1.21 histórica, não esta release.

SHA-256 do manifesto novo:
`9348D2FF063779B1AFE88101E66E55FBC41820EFAA7697A013DF3A23CA2F6055`.

SHA-256 canônico do BUILD_LOCK histórico preservado:
`946D69A77973B5EAB186D8438F449A87656BFFFB06A42988AD4518B133502ED2`.

### Cinco SHA-256 de trabalho conferidos antes e depois

| Arquivo em finance-v17 | SHA-256 do working tree preservado |
| --- | --- |
| config.yaml | 1BC4E21209FDCDF0DE4BD3D248939A284E54A3E35E19ADC6846EA77160138461 |
| Dockerfile | 8B54B04B535A6142A8918137820DC5659967BC50D0C2F37981C3FB283C968074 |
| src/finance_v2/__init__.py | 2DE7418535D03A102651618F8A6933FEE13FFFCFC9F3BD97B7A5B8A7F4282479 |
| CHANGELOG.md | 2484EDC621A18215B50624E17D155CFCA04671A52548A0A9B4A4BA8C4C9813EE |
| DOCS.md | CCE2F8DD6D8204CB2736B7997EA3DCFB2F07946F97E588B3B622DF3CC15D106A |

Git core.autocrlf=true já era herdado nesta instalação. Por isso os blobs
canônicos desses metadados podem ter hashes diferentes dos arquivos CRLF
locais. Não houve alteração da configuração Git nem conversão dos arquivos
protegidos. O manifesto identifica explicitamente a representação usada.

## Testes efetivamente reexecutados

Windows; Node 24.19.0; Python 3.10.0; navegador Chromium/Edge headless local.

| Grupo | PASS | FAIL | SKIP |
| --- | ---: | ---: | ---: |
| Interface sintética, preferência/privacidade, abas, filtros e paginação | 33 | 0 | 0 |
| Regressões históricas de apresentação, asserts originais | 3 | 0 | 0 |
| MCP WSGI real: initialize, SSE, tools/list e rejeições | 6 | 0 | 0 |
| Validador real, incluindo seis controles negativos em memória | 7 | 0 | 0 |
| Total | 49 | 0 | 0 |

O anúncio MCP é exatamente 0.1.22-open-finance.1; protocolo 2025-03-26.
O código de transporte, ferramentas e autorização não foi modificado.
O teste MCP instala audit hook que rejeita abertura SQLite, conexão/bind
de socket e subprocessos. Não usa credenciais reais nem um servidor ativo.

Controles negativos executam o validador real com respostas Git somente de
leitura, capturadas e alteradas em memória. Rejeitam mudanças em opções,
imagem-base, API, bytes protegidos, documentação e manifesto; nunca escrevem
essas corrupções no produto ou no índice e não substituem os testes da UI.

Evidências novas e exclusivas:
`G:\Codex\FinancePhaseARelease-0.1.22-20261023-01`.
Incluem interface/RESULTS.json, TAP, screenshots sintéticos, histórico das
três regressões, logs MCP/validador e manifesto SHA-256 das evidências.
As execuções anteriores e seus resultados foram preservados.

Comandos de reprodução (diretórios de evidência precisam ser novos):

```powershell
node tests/verify_phase_a.cjs
node --test --test-reporter=tap tests/release_validator.cjs
python -B tests/release_mcp.py
node tests/run_phase_a.cjs 'G:\Codex\FinancePhaseARelease-NOVA-UI'
python -B tests/run_phase_a_regressions.py 'G:\Codex\FinancePhaseARelease-NOVA-REGRESSAO'
git diff --cached --check
```

O validador é explicitamente staged: preparar no índice apenas os arquivos
revisados antes de executá-lo. A regressão histórica lê os testes locais já
existentes em Finance_V2 sem importar suas fixtures ou modificar o workspace.

## Integridade e limites

- Oito de oito hashes protegidos aprovados; run.sh permanece com SHA-256
  `7FBDCE1C1A73A97AD757042956512D76BC3FB0DF6BDB023E17CB7F06BEC0B070`.
- As migrations 001–009 permanecem idênticas; zero novas migrations.
- Nenhum banco aberto, criado ou migrado. Nenhum backup ou credencial real utilizado.
- Nenhuma mudança de esquema, contrato HTTP, lógica financeira ou sincronização.
- Backend financeiro completo, build ARM64 e Supervisor não foram reexecutados
  nesta preparação de metadados/UI; não são declarados homologados aqui.
- Permanece a limitação preexistente de diálogo adicional ao editar receita
  recorrente, documentada e comprovada na Fase A. Nenhuma correção funcional
  foi feita para removê-la ou ocultá-la.
- Privacidade é projeção de apresentação, não criptografia ou autorização.
- Nenhum push, tag, release, nova branch ou operação Home Assistant executado.

LOCAL_PREPARATION_STATUS=READY
PUBLICATION_AUTHORIZED=False
PRODUCTION_DEPLOYMENT_AUTHORIZED=False
