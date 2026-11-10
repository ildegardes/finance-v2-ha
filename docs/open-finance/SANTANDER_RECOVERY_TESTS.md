# Evidências de qualificação da candidata

Resultados novos desta tarefa, com dados exclusivamente sintéticos:

| Ambiente | Execuções aprovadas | Escopo |
| --- | ---: | --- |
| Windows / Python 3.10 | 219 | 14 arquivos unittest executados em processos separados |
| Imagem ARM64 / Python 3.12.7 | 219 | Mesmos 14 arquivos, rede none, raiz somente leitura, bases sintéticas temporárias |
| Navegador Edge / Playwright | 89 | 7 suítes; 9 casos novos da administração e 80 regressões de interface/navegação |

As 32 execuções específicas da recuperação estão incluídas nos totais Python; não são somadas novamente. Os totais contam execuções por suíte, não alegam exclusividade de todos os casos herdados/importados. CI GitHub será verificado separadamente; estes resultados são locais.

## Supervisor real isolado

HAOS ARM64 em QEMU de sistema completo, kernel aarch64 próprio, AppArmor habilitado e Docker interno aarch64. Supervisor 2026.10.5 supported=true e healthy=true. Discos predecessores montados somente leitura e disco filho exclusivo; sem volumes de produção. Nenhum teste foi feito no Raspberry Pi operacional. Emulação não substitui medição de desempenho em hardware físico.

Build e atualização 0.1.27 para 0.1.28 executados pelo Supervisor local. A aplicação instalada confirmou 93 arquivos de runtime/migrations/lançador contra a candidata. Imagem Supervisor: `sha256:a1bd974c4db42d65622b00b6c4ba694755ef3bdc413741ce47e157c9d358916f`. Build Docker ARM64 separado: `sha256:abab65f24760ec32b4a595fc561ea33da0b8cde6fe917f611c2e57d40787a6cb`. Estes são identificadores/digests de configuração de imagem, não um digest de registry publicado. Há diferenças esperadas de metadados/labels Supervisor; não é alegada identidade binária entre builds.

Pela API HTTP da aplicação realmente instalada: Settings carregado, ELIGIBLE para o par invertido, atualização de exatamente uma célula, preservação de todas as demais células, 26 runs Santander preservados, Itaú e manual preservados, repetição ALREADY_CORRECT sem UPDATE, recibos 0700/0600, reinício pelo Supervisor, persistência e reversão seletiva aprovados. Schema 11, FK e integrity_check permaneceram válidos. Auto-sync desligado; saída de rede bloqueada durante os testes operacionais.

## Falhas do instrumental preservadas e resolvidas

A descoberta global inicial misturou testes que instalam audithooks irreversíveis no processo Python. As suítes foram isoladas por arquivo, sem relaxar essas guardas. Uma fixture pública de configuração era procurada fora do checkout; agora está versionada junto ao teste. O teste de recuperação schema10 exigia o código predecessor externo: a fixture utilizada foi conferida contra o commit público 3c4e131e6592a1155cb06910c5188bf2fd5793b2 (77 arquivos, mesma informação exceto finais de linha).

No laboratório, a primeira carga sintética foi semeada antes de o Supervisor regenerar options.json. O controlador recusou o binding desconhecido, sem atualização. A fixture foi ajustada após a materialização das opções; não houve correção no produto para aceitar o vínculo. Outra tentativa do harness ocorreu antes da porta HTTP estar pronta; adicionou-se espera de readiness somente ao instrumental local. As evidências originais dessas falhas foram preservadas fora do repositório.

## Reproduzir

Definir PYTHONPATH para finance-v17/src e executar cada test_*.py por arquivo, com unittest discover, em processo separado. Para test_gate_b.py, preparar ../baseline/finance-v17/src e migrations com o código público 0.1.26 do commit acima. Não usar um banco real como fixture. Em ARM64, usar a imagem candidata com rede none, checkout somente leitura, /tmp descartável e VALIDATION_FIXTURE_ROOT em /tmp.

Executar `node --test tests/test_santander_binding_recovery_ui.cjs` para os nove casos novos. As suítes históricas de navegador exigem suas fixtures sintéticas qualificadas e Edge/Playwright. Não contam como verificações executadas pelo GitHub. Logs completos permanecem no diretório local de evidências; o JSON publicado traz resultados e SHA-256 desses artefatos, sem bancos, options.json, respostas financeiras ou recibos privados.
