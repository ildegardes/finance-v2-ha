# Finance V17 0.1.26-open-finance.1 — Release candidate D08

Corrige renovação concorrente desnecessária de API Key causada por 401 tardio e melhora a apresentação das falhas de coleta. Uma resposta atrasada de progresso não substitui mais o resultado final. Histórico e coleta compartilham mensagens sanitizadas sem confundir AUTH_FAILED com credenciais inválidas.

Não corrige por suposição a rejeição real Santander ou a divergência de Item Itaú. Essas integrações permanecem NOT_VERIFIED até diagnóstico real autorizado. Não normaliza Item IDs nem relaxa autorização por escopo. Não exporta API Keys.

Schema 10 e migrations 001–010 intactos; oito arquivos protegidos preservados. Nenhuma mudança em dados oficiais, OAuth/MCP, contratos HTTP, configuração, auto-sync, scheduler ou lifecycle. O anúncio MCP muda somente para a nova versão.

Atualização futura deve usar o mesmo repositório, diretório e slug do add-on existente; não excluir/reinstalar, não criar outra instalação e não copiar banco entre slugs. Publicação e operação no Home Assistant exigem autorizações separadas.

Pré-requisitos: revisão do commit e testes D08; recuperação disponível de código/imagem 0.1.25, configuração e /data schema 10 consistentes; identificação do estado instalado e flags de auto-sync/watchdog. Iniciar uma instalação com auto-sync já habilitado pode disparar as tarefas existentes; essa operação não está autorizada por esta preparação.

Rollback de código mantém compatibilidade estrutural com schema 10. Falha de dados exige recuperação coordenada da mesma captura de código/imagem, configuração e /data, com aceite de perda de alterações posteriores. Não restaurar backup schema 9 como se fosse equivalente. Restauração pelo Supervisor não foi ensaiada nesta D08.

Limitações: dados bancários reais não consultados; causas externas não comprovadas; testes Docker ARM64 emulado não equivalem à homologação HAOS/Supervisor. Ver D08_RELEASE_REPORT.md e D08_GITHUB_UPDATE_INSTRUCTIONS.md antes de qualquer publicação ou operação.
