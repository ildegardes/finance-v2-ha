# Finance V17 0.1.36-open-finance.1

## Atualização e reversão

Faça um backup recuperável do add-on com banco, opções e chave de credenciais quando utilizada. Atualize o catálogo pelo Supervisor do Home Assistant e instale a atualização do add-on Finance V17. Confira `migrations.current_version=16` em `/api/v2/health`. O slug permanece `finance_v17`. Para retornar à 0.1.35, guarde uma cópia separada dos dados atuais e restaure o backup anterior de schema 15 com suas opções e chave correspondentes.

## SnapTrade Personal e Charles Schwab

Na aba **Configuração** do add-on no Supervisor, marque `snaptrade_enabled`, preencha `snaptrade_client_id` com o Client ID e `snaptrade_consumer_key` com o Consumer Key da conta Personal. Salve e reinicie o add-on. Em uma instalação com Administração privada habilitada por HTTPS confiável e chave local protegida, **Open Finance › Conexões › SnapTrade › Credenciais protegidas** oferece os dois campos equivalentes e tem precedência sobre as opções. Trate o backup das opções ou da chave como material privado.

1. Abra **Open Finance › Conexões › SnapTrade**, clique em **Testar credenciais e descobrir contas** e confira a autorização e as contas da Charles Schwab que já estavam conectadas. O Finance consulta autorizações já existentes da conta Personal. Se a autorização precisar de reautenticação, resolva no portal da SnapTrade e repita a descoberta.
2. Clique em **Atualizar dados** ou **Atualizar esta conexão**. Abra **Contas e diagnóstico** para comparar o horário local, a referência do provedor e o intervalo importado, incluindo eventuais recursos parciais. Repita a atualização após o horário indicado quando houver bloqueio de taxa.
3. Em **Investimentos › Carteira unificada**, filtre por provedor, instituição, conta e mercado. Compare quantidade, preço, custo e valor da posição com o extrato da corretora quando cada campo estiver disponível. Expanda **Caixa, poder de compra e margem** para comparar os saldos. Confira ativos remunerados e caixa com o extrato, pois a corretora pode reportar fundos monetários dentro do caixa.
4. Em **Conexões › Cotações PTAX**, escolha o intervalo e clique em **Atualizar cotações do Banco Central**. Compare **Moedas originais**, **Converter para BRL** e **Converter para USD** na Visão geral ou na carteira. Confira data e taxa em **Taxas e datas da conversão**. A taxa é a PTAX de venda do BCB do próprio dia ou do dia útil anterior dentro da janela de sete dias. Valores sem taxa, de datas diferentes ou com cobertura insuficiente recebem diagnóstico de consolidação.
5. Compare **Atividades da corretora** e **Proventos internacionais** com o extrato, inclusive dividendos, juros, retenções, taxas e reinvestimentos. A importação inicial percorre a janela disponível no provedor. O histórico da carteira cresce com as coletas que tenham referências financeiras comparáveis. Consulte a [matriz de capacidades](../docs/open-finance/SNAPTRADE_CAPABILITIES.md) para os recursos opcionais.
6. Para automatizar, marque **Coleta automática** e salve o intervalo em **Conexões › SnapTrade**. O intervalo inicial é 24 h. O agendamento da SnapTrade é independente do Pluggy. Use a política de conexão para pausar, arquivar ou excluir um escopo da consolidação. Para desligar a integração, desmarque `snaptrade_enabled` nas opções e reinicie o add-on.

## Versões anteriores

### Finance V17 0.1.35-open-finance.1

## Atualização e reversão

Faça um backup recuperável do add-on com as opções, o banco e a chave de credenciais quando utilizada. Recarregue o catálogo e instale a versão pelo Supervisor. A inicialização aplica a migration 015. O healthcheck em `/api/v2/health` deve informar `migrations.current_version=15`.

Para retornar à 0.1.34, preserve uma cópia separada dos dados atuais e restaure o backup anterior de schema 14 junto com as respectivas opções e chave. Os snapshots anteriores continuam no banco. O slug é `finance_v17`.

## Reconhecimento e perspectivas

A condição de revisão continua disponível na Central de classificação. A projeção acrescenta `economic_recognition` com fonte, natureza e componente do fluxo. Uma classificação manual válida, regra personalizada confirmada ou regra nativa determinística pode fornecer evidência. Categorias reconhecidas do provedor, como Livrarias e Energia elétrica, exigem débito efetivado, moeda do escopo, valor e descrição compatível. Transferências genéricas, PIX sem finalidade, venda ambígua de ativos e resgates sem prova de principal ficam fora do subtotal econômico. O salário pode ser reconhecido por uma rubrica determinística.

A visão Bancária mantém os totais brutos. O detalhamento explica entradas e saídas por natureza, com quantidades e acesso às movimentações. A visão Econômica informa os valores bancários identificados. Dados parciais mantêm os subtotais conhecidos. Uma direção sem evidência permanece indisponível enquanto a cobertura for insuficiente. O ranking usa o mesmo recorte do subtotal.

Compras de cartão identificadas e estornos comprovados aparecem separadamente, pela data lançada no cartão. A identificação exige lançamento efetivado e evidência compatível. Uma parcela vale pelo lançamento individual daquela data. Contratos de parcelamento, faturas, limites e pagamentos bancários não geram novas despesas de cartão. A separação evita misturar a data bancária com a data da compra sem reconciliar a cobertura de ambos os produtos.

O saldo de cartões usa obrigações de titular identificadas, da mesma moeda e data financeira comparável. Obrigações independentes podem somar entre instituições, com uma conexão por instituição no subtotal. Reportamos o tipo de saldo e quantos cartões entraram no cálculo. Em caso de valores de tipos diferentes, o saldo utilizado tem precedência. Limites e faturas são projeções próprias. Motivos de exclusão ficam no card. Zero informado continua zero.

## Patrimônio e Movimentações

O card patrimonial pode escolher uma conexão ativa independentemente do filtro geral. A seleção automática usa o único histórico elegível quando disponível. Uma posição conhecida pode aparecer durante a formação do histórico. A série usa referências financeiras comparáveis e registra as datas de coleta separadamente. Coletas equivalentes preservam a observação anterior. A variação patrimonial inclui movimentações de capital e mudanças de valor de mercado.

A aba Movimentações oferece 25, 50, 100, 250 e 500 registros por página. A preferência inicial é 50 e fica no navegador. A ordenação ocorre no servidor sobre o recorte completo, com magnitude decimal e desempate por identidade. Cada consulta usa uma moeda. Grupos por instituição e categoria organizam a página já ordenada. A ordenação por valor ou descrição desativa o agrupamento por data. Privacidade total substitui a ordem financeira pela data enquanto estiver ativa.

## Sincronização automática

A frequência padrão de leitura local do cache é 24 horas. A interface permite 1, 2, 4, 6, 12, 24 ou 48 horas. A opção administrativa do Supervisor e a permissão de cada conexão são condições para a coleta automática. A preferência auditada na aplicação pode pausar a execução e tem precedência sobre o intervalo padrão do Supervisor. O estado previamente desativado continua desativado. O worker reavalia a preferência em até 15 segundos. A alteração vale para novos ciclos, preservando o lease da execução atual.

Após reiniciar, a próxima coleta é reconstruída a partir do resultado e horário persistidos. Uma coleta manual completa também conta como reconciliação local válida. Falhas transitórias têm intervalo de recuperação de cinco minutos. Falhas de autenticação ou consentimento esperam até 24 horas, limitadas pelo intervalo de rotina. A coleta manual permanece disponível.

A última atualização do Item vem de `lastUpdatedAt`. `nextAutoSyncAt` é uma previsão da Pluggy. A API pode omitir a previsão ou fornecer um horário já passado. Os horários da aplicação vêm dos registros locais de tentativa e sucesso. Os metadados documentados do Item não fornecem uma revisão imutável de todas as coleções. A coleta usa a reconciliação de cache existente e não solicita atualização bancária. [Item](https://docs.pluggy.ai/en/reference/items/items-retrieve) · [Transações](https://docs.pluggy.ai/en/docs/products/transactions)

## Regressões do chaveiro

A qualificação da 0.1.34 em Windows pulou quatro casos porque a proteção de arquivo depende de `O_NOFOLLOW`, permissões POSIX e identidade do usuário Linux. Os quatro fazem parte do CI Linux desta versão.

| Teste | Relevância na distribuição | Condição de execução |
| --- | --- | --- |
| `test_opt_in_owner_permissions_and_idempotent_restarts` | Exige opção do proprietário e confirma permissões e reinicialização | Linux, permissão 0600 e sistema de arquivos POSIX |
| `test_missing_key_with_encrypted_credentials_never_creates_replacement` | Protege contra substituição de uma chave perdida com credenciais existentes | Linux com suporte a `O_NOFOLLOW` |
| `test_insecure_file_or_symlink_fails_closed` | Rejeita elo simbólico e permissões abertas | Linux, chmod e criação de links simbólicos |
| `test_sqlite_snapshot_and_matching_private_key_restore_credentials` | Qualifica restauração de SQLite e chave compatíveis | Linux e chave sintética com permissões POSIX |

---

## Referência operacional da versão anterior

# Finance V17 0.1.34-open-finance.1

## Atualização e reversão

Faça um backup recuperável do add-on antes da atualização. Recarregue o catálogo e instale a versão 0.1.34-open-finance.1 pelo Supervisor. A inicialização aplica a migration aditiva 014 e o healthcheck em `/api/v2/health` deve indicar `migrations.current_version=14`. A configuração e os dados permanecem em `/data`.

Para retornar à 0.1.33, preserve um backup separado com os dados posteriores à atualização e restaure o backup de schema 13 anterior à instalação. A versão anterior exige seu próprio schema. As migrações 001 a 013 continuam sendo as já distribuídas.

## Perspectivas e categorias

- A visão **Econômica** usa receitas e despesas bancárias identificadas, pelo período da data bancária. A visão **Bancária** usa todos os movimentos efetivados no escopo. A decomposição separa capital, transferências internas, liquidações e registros em revisão.
- O ranking e a listagem usam a mesma categoria efetiva. As categorias Finance V17 usam chave derivada do texto canônico da classificação, independente da tradução na interface. Categorias do provedor mantêm sua chave de origem. A categoria original e a evidência continuam disponíveis nos detalhes.
- Pagamentos de fatura ficam no grupo de liquidações. A cobertura das compras, estornos e parcelamentos de cartões ainda é analisada separadamente. A mistura de data da compra, liquidação bancária e competência exigiria evidência temporal e reconciliação adicionais.
- Aplicações e resgates de principal confirmados aparecem como movimentos patrimoniais. Resgates com composição desconhecida permanecem em revisão. O Aplic Aut Mais tem resumo de volumes, créditos, tributos e registros correspondentes. A posição do produto depende de identificação explícita no provedor.
- Rendimentos são somados pelos créditos bancários classificados, com cada crédito em uma categoria de provento. A comparação usa janelas de mesma duração quando os dois intervalos têm cobertura datada e classificação econômica suficiente.

## Posições, cartões e histórico

- Saldo, investimentos e cartões mostram as últimas posições conhecidas. O período controla os movimentos. As datas financeiras e as observações ficam nos detalhes da posição.
- O saldo utilizado pode ser consolidado para obrigações individuais de titulares, com identificadores distintos, mesma moeda e mesma coleta da conexão. Limites compartilhados e faturas ficam separados.
- O histórico de revisões anterior a esta versão guarda mudanças de registros. A migration 014 cria snapshots prospectivos. Apenas coletas bem-sucedidas com cobertura de investimentos verificada e posições válidas geram registros. Ausência de posição e falhas preservam a última observação registrada.
- A série exige pelo menos duas datas financeiras comparáveis na mesma moeda e conexão. Quando há várias conexões, selecione uma para evitar sobreposição. A variação inclui os efeitos de aportes, resgates e mudanças de mercado. Os pontos representam observações reais.
- Em **Qualidade dos dados**, disponibilidade dos recursos, completude temporal, classificação e disponibilidade de histórico ficam separadas. Uma coleção retornada integralmente pode ter um intervalo financeiro desconhecido.

## Privacidade e identidades

O ícone ao lado de **Sair** define a privacidade da aplicação. **Valores visíveis** mostra valores e gráficos. **Ocultar valores** mantém as proporções. **Privacidade total** oculta também gráficos e rankings financeiros. A preferência segue o perfil do navegador, com sincronização entre abas da mesma origem. A proteção visual atua sobre a apresentação dos dados já autorizados.

As identidades locais são monogramas e silhuetas genéricas desenhados no projeto em CSS. Os nomes comerciais identificam a instituição, o produto e a bandeira. Ícones não oficiais usam cores e iniciais, sem dependência de arquivos de marca licenciados ou serviços externos. Produtos desconhecidos recebem a mesma silhueta genérica. A homologação no Supervisor e o teste com leitor de tela ficam com o proprietário.

## Classificação financeira

Em **Open Finance → Movimentações**, use **Classificar movimentação** para salvar uma decisão individual. Categoria, natureza, origem e estado de revisão são campos separados. A área Detalhes preserva a categoria do provedor e explica a condição aplicada.

A precedência é decisão manual, regra personalizada, regra nativa e categoria original. Regras de mesma prioridade com resultados divergentes geram revisão. A direção bancária e a categoria original continuam disponíveis como contexto.

Use **Central de classificação** para revisar padrões recorrentes. Em **Gerenciar regras**, crie ou edite uma regra. Defina a conexão, os termos da descrição e, quando necessário, uma conta, uma direção e uma moeda. Para salário, crie uma regra do seu próprio remetente após conferir o significado dos créditos. A origem é local, auditável e sem chamadas a serviços externos.

Uma regra prospectiva vale para novas identidades importadas por coletas iniciadas após aquela revisão. A decisão individual usa a identidade estável da movimentação e permanece disponível nas reimportações. A atualização aplica a leitura automática das regras nativas vigentes aos dados existentes, sem registrar alterações manuais ou lotes retroativos por conta própria.

Para aplicar ao histórico, selecione uma regra e **Simular histórico**. Revise intervalo, quantidade, conflitos, exceções protegidas e amostra. Marque a confirmação para aplicar. Uma mudança concorrente relevante invalida a simulação. Em **Auditoria e reversão**, a reversão restaura somente decisões do lote que ainda estão vigentes e preserva alterações posteriores independentes.

## Referência operacional de versões anteriores

As seis áreas consultam projeções tipadas do staging, sem criar lançamentos oficiais.
Contas e cartões navegam para movimentos, faturas e referências de extratos;
posições navegam para suas movimentações. Dados ausentes/null/zero e cache
desatualizado são distintos. O histórico é de observações, não rentabilidade calculada.
Downloads de extratos e consolidação patrimonial não comprovada permanecem desabilitados.

GET domain e relations não autenticam na Pluggy nem coletam dados.
Coleta completa, reconciliação incremental e retomada exigem ação explícita do proprietário.
Incremental significa upsert/revisão das alterações numa varredura completa limitada;
retomada repete coleções idempotentemente, sem confiar em cursor antigo.
Consentimentos estrangeiros continuam rejeitados. O diagnóstico não autoriza ignorar a guarda.

O default de open_finance_auto_sync_enabled nesta candidata é **false**.
Isso não modifica opções existentes: uma configuração persistida true precisa de
decisão operacional explícita antes de qualquer futura inicialização.
Não iniciar esta candidata com configuração copiada da produção durante ensaios.

Detalhes: ../docs/open-finance/GATE_B_CONTRACTS.md. A recuperação de schema11
para schema10 exige restaurar juntos código 0.1.26, configuração e banco correspondentes;
trocar somente o código não reverte a migration. Backup/restore real pelo Supervisor
não foi executado no Gate B.

## Documentação histórica de 0.1.25 (defaults anteriores)

Schema 10; migrations 001–010 preservadas. Atualizar de 0.1.23 não exige migration nova.
Python 3.12.7, oauthlib 3.3.1 e Unicode13 versionado. Notices em
`src/finance_v2/UNICODE13_NOTICES.md`. O slug continua finance_v17, porta 8766,
armazenamento /data e repositório público de distribuição permanecem os mesmos.

## Ativação sem sobrescrever preferências

O default `open_finance_auto_sync_enabled` é **true para opções novas**, mas
`open_finance_enabled` e as duas conexões continuam false em instalações novas.
Não há chamadas sem integração habilitada e credenciais/Item configurados.

**Atualização da instalação existente:** um false persistido é respeitado. O
Supervisor combina defaults com opções persistidas; mudar o default não habilita
silenciosamente esta instalação. Não há migração de opções, escrita em
/data/options.json pelo Finance ou acesso administrativo ao Supervisor.

Depois da atualização pelo proprietário, para a instalação já configurada e com
integração/conexões habilitadas, a ação adicional é abrir Configuração do add-on e
habilitar **open_finance_auto_sync_enabled**, salvar e iniciar/reiniciar quando
autorizado. Não alterar os Client IDs, Client Secrets ou Item IDs existentes.
O primeiro ciclo começa após a criação do servidor HTTP. Se a flag efetiva
permanecer false, **não haverá ingestão automática**. As opções são lidas no startup;
não existe hot reload. Não se exige recadastrar uma conexão válida.

| Opção | Default novo | Efeito |
|---|---|---|
| open_finance_enabled | false | Habilita a integração configurada |
| open_finance_auto_sync_enabled | true | Coleta periódica de cache, respeitando false persistido |
| pluggy_itau_enabled | false | Habilita o preset Itaú |
| pluggy_santander_enabled | false | Habilita o preset Santander |
| pluggy_*_client_id/client_secret/item_id | vazio | Aplicação/Item próprios de cada instituição |

Não presumir credenciais iguais. Opção incompleta afeta somente o banco correspondente,
com diagnóstico fixo OPEN_FINANCE_CONNECTION_INVALID_ITAU/SANTANDER. Nenhuma opção ou
credencial é apagada. Vínculo divergente com staging existente resulta em
CONNECTION_BINDING_CHANGED; não substituir Item ou apagar staging para contorná-lo.

## O que a sincronização faz

Um worker por conexão usa a mesma ingestão de `POST /api/v2/open-finance/coverage-sync`.
Configuração, hash do vínculo e escopo dos IDs são conferidos. O Item e os metadados
de recursos/consentimentos são lidos antes dos produtos. Autorização expirada,
revogada ou Item exigindo ação do usuário é registrada sem renovar consentimento.
Quando metadados de consentimento não estão disponíveis, não se inventa sua validade;
os endpoints e estados de cobertura do provedor continuam sendo respeitados.

São chamadas GET de cache e, quando necessário, POST /auth para chave temporária.
Não há atualização remota do Item, saldo em tempo real, SCR, pagamento, transferência
ou renovação de autorização. Dados podem estar desatualizados no provedor; ingestão
do cache não é comprovação de uma nova coleta pela instituição.

Após sucesso automático recente, o restart aguarda o intervalo restante de uma hora,
sem criar outra execução. Falha automática recente recebe backoff mínimo de cinco
minutos em restart; interrupções permitem retomada. Decisão e lease compartilham
transação SQLite. A ação manual continua disponível e auditada. Cada instituição é
independente; lease ativo impede sobreposição. Não há polling agressivo.

Chamadas automáticas usam timeout de socket de 2s e orçamento de execução de 120s.
Um I/O que não coopera é desacoplado da autoridade de persistência; sua resposta
tardia não pode gravar. Há no máximo uma chamada não resolvida por conexão.
Cancelamento finaliza como INTERRUPTED/AUTO_SYNC_CANCELLED. Se o banco recusar a
finalização, CANCELLATION_FINALIZATION_DEFERRED mantém recuperação pelo lease de
300s e fencing. Não se anuncia sucesso de uma coleta interrompida.

## Interface e verificação

As seis áreas consultam staging: Visão geral (contas/saldos), Fluxo (transações e
categorias), Cartões (contas CREDIT, limites/faturas), Ativos (posições/movimentos),
Crédito (empréstimos) e Conexões (Item, consentimentos, recursos e histórico).
Ao abrir ou trocar de área, os dados atualmente persistidos são consultados.
Não há promessa de atualização por push de uma aba já aberta.

Conexões mostra estado da última execução e cobertura. Conferir cada instituição:
SUCCEEDED não significa todos os produtos disponíveis. EMPTY, NOT_AVAILABLE,
NOT_AUTHORIZED, NOT_COLLECTED e FAILED têm significados diferentes; zero e ausência
não são equivalentes. Item OUTDATED pode fornecer cache antigo, identificado pelos
metadados originais. CONSENT_EXPIRED, CONSENT_NOT_ACTIVE, ITEM_REAUTH_REQUIRED e
ITEM_USER_ACTION_REQUIRED exigem revisão do proprietário, não sincronizações repetidas.

Não inferir saldos de transações, patrimônio consolidado, retorno histórico ou
proveniência F07 sem evidência. Revisões não são novas posições. NOT_SEEN preserva
histórico sem afirmar exclusão. Categorias originais são preservadas.
Nenhum registro staging é promovido para despesa, receita, pagamento, cartão,
fatura ou recorrência oficial. O scheduler financeiro permanece separado.

O botão de olho mantém a privacidade global: valores ocultos por padrão, preferência
localStorage e máscara R$ ••••••. Isso não é criptografia ou autorização; dados seguem
na API/memória. Não publicar screenshots com dados reais.

## Segurança e recuperação

Não imprimir options.json, environment, Client Secrets, API keys, Items ou números
completos. O stdout de ha_pluggy_options é transporte privado capturado pelo wrapper;
nunca executá-lo isoladamente em terminal ou com set -x. Campos password e backups
não substituem controle de acesso ao host. OAuth/MCP não recebe acesso owner-only
ao staging. Sessões de escrita continuam exigindo CSRF.

Antes de instalação em produção: verificar estado atual, proteção consistente
imediatamente anterior e recuperação conjunta de código, configuração e /data.
Manter cópia externa verificada e janela operacional. Nada nesta documentação
executa backup, parada, atualização ou sincronização.

Se houver falha, preservar logs sanitizados e o conjunto SQLite/WAL/SHM; não apagar
leases para fabricar sucesso. Restaurar versão e configuração compatíveis com o
mesmo banco. Ao voltar para **0.1.23**, restaurar auto-sync **false**: essa versão
rejeita true antes da API. Downgrade de código não é restauração de dados.
O backup antigo schema 9 não equivale a rollback de uma instalação schema 10.

Build e testes Docker/ARM64 emulado não são homologação Supervisor/HAOS real.
Consultar o relatório versionado em docs/open-finance/RELEASE_0.1.24.md para
evidências, limitações, gates e instruções operacionais propostas.

## Diagnóstico 0.1.25

Esta versão acrescenta somente eventos OPEN_FINANCE_DIAGNOSTIC para localizar
ACCOUNT_SCOPE_MISMATCH e AUTH_FAILED. Campos fechados identificam etapa, recurso,
categoria, status HTTP e correlação de execução local; não expõem Item/conta,
credencial, payload ou dados financeiros. Os códigos públicos e as guardas não mudam.
Opções, auto-sync, consentimentos e schema 10 continuam como na 0.1.24.
Não iniciar novas sincronizações para validar este diagnóstico sem autorização.
Procedimento e rollback: docs/open-finance/RELEASE_0.1.25.md no repositório.


## D08 — candidata 0.1.26-open-finance.1

A interface distingue recusa de autenticação sem causa confirmada, divergência de escopo, consentimento expirado/inativo, comunicação e falha interna. Não altere credenciais ou Item apenas por AUTH_FAILED. A guarda de escopo continua estrita; divergências reais Itaú/Santander dependem de diagnóstico autorizado. Nenhuma coleta inicia por abrir a tela.

Uma falha pode ocorrer após páginas confirmadas no staging; consulte histórico e cobertura antes de repetir. Nenhum resultado bancário é promovido a lançamento oficial. Não há migration nova. O cache de API Key continua em memória por cliente, com expiração e uma renovação por GET 401; respostas antigas não invalidam chave diferente recém-renovada.

Publicação e atualização requerem autorizações separadas. Preservar a instalação existente finance_v17, /data e configuração. Rollback de código para 0.1.25 é compatível com schema 10, mas incidente de dados exige recuperação coordenada com configuração e backup schema 10 contemporâneo; não usar backup schema 9. Os procedimentos detalhados acompanham D08_GITHUB_UPDATE_INSTRUCTIONS.md.
# Chave das conexões Pluggy gerenciadas

O add-on guarda as credenciais gerenciadas cifradas no SQLite e usa
`/data/pluggy-keyring.json` como arquivo de chave separado. O arquivo tem
permissão `0600` e pertence ao usuário efetivo do serviço. O provisionamento
cria a primeira chave somente quando a origem administrativa privada está
configurada e ainda não existem credenciais gerenciadas. Reiniciar o add-on
preserva a chave existente. A opção `pluggy_admin_origin` fica vazia por padrão.

Para administrar conexões no Supervisor, use uma conexão direta pela rede
privada. Em `/ssl`, instale um certificado dedicado
`finance-v17-admin.pem` e a chave correspondente
`finance-v17-admin-key.pem`. O certificado deve conter o endereço IP privado
no Subject Alternative Name e ser confiável no navegador. O Supervisor monta
`/ssl` somente para leitura. Na configuração do add-on, informe a origem exata,
por exemplo `https://192.168.1.10:8767`, e habilite o mapeamento da porta
`8767/tcp`, que vem desativado. Acesse `/app/` nessa origem e autentique-se
com o token do proprietário. Mantenha a porta TLS fora do Cloudflare Tunnel
e de encaminhamentos públicos. A porta HTTP 8766 continua atendendo as
rotas existentes, com a administração do registro bloqueada.

Em **Instituições Financeiras**, salve um rascunho e use **Verificar Item e
recursos** para conferir o Item e os recursos declarados pela Pluggy. A
verificação consulta apenas a primeira página de recursos e indica quando há
mais páginas. A ativação exige confirmação separada. A coleta financeira pode
ser iniciada manualmente após a ativação.

A ação **Consultar conectores** usa as credenciais do rascunho para ler uma
página do [catálogo Pluggy](https://v2.docs.pluggy.ai/en/reference/connector/connectors-list).
Se você selecionar um conector, a ativação confere o ID retornado no Item.
A lista é filtrada pelo perfil. Para MeuPluggy pessoal, o conector 200
identifica o proxy e a identidade financeira continua vinculada ao Item.
**Ver detalhes** mostra estado administrativo, revisão e reserva de execução
no acesso privado. A API de detalhes também disponibiliza eventos administrativos recentes.

Ao escolher **Arquivar**, confira a inspeção de dependências antes de confirmar.
A confirmação verifica novamente integridade, dependências, execução e lease.
Registros financeiros vinculados permanecem preservados e impedem a substituição.

As regras de mapeamento de diretórios e portas são descritas na
[referência de configuração do Supervisor](https://contributors.home-assistant.io/apps/reference/configuration/).

Em caso de `CREDENTIAL_KEY_RESTORE_REQUIRED`, recupere o arquivo da mesma
geração do banco. Uma chave perdida não pode ser derivada dos dados cifrados.
O add-on mantém as consultas locais e as conexões legadas disponíveis enquanto
o acesso às credenciais gerenciadas falha com diagnóstico sanitizado.

Um backup que contém o banco e o arquivo de chave permite decifrar as credenciais.
Proteja o backup com criptografia e acesso restrito. Mantenha o material de
recuperação da chave protegido e fora de logs, repositórios e chamados de
suporte. Valide uma restauração em instância descartável com o banco e a chave
da mesma geração, confirmando integridade SQLite e leitura das credenciais
sintéticas. Para retornar a uma versão que só aceita o schema 11, restaure um
backup anterior à migração, após preservar os dados novos para conciliação.
Recibos pendentes da recuperação Santander da versão 0.1.28 precisam ser
reconciliados nessa versão antes da migração, pois seus fingerprints incluem
o schema 11.
