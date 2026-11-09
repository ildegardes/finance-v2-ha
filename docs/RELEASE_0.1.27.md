# Finance V17 0.1.27-open-finance.1

## Atualização e configuração

Este complemento mantém o repositório, slug finance_v17, porta 8766 e persistência /data. A instalação existente permanece 8327184f_finance_v17 quando atendida pelo mesmo repositório oficial. O banco migra do schema 10 para 11; não basta rebaixar o código para voltar ao schema 10.

As credenciais existentes continuam nas opções do complemento: pluggy_itau_client_id, pluggy_itau_client_secret, pluggy_itau_item_id e os três campos equivalentes pluggy_santander_*. Não é necessário cadastrar novamente esses valores. O Supervisor fornece /data/options.json ao contêiner; o lançador protegido converte essas opções para o contexto privado em memória, e cada banco possui cliente e API Key separados. O runtime não depende de cofre do Windows, caminhos do PC01 ou staging externo. Não execute o módulo ha_pluggy_options isoladamente em terminal com logs: sua saída privada é capturada pelo lançador.

Novos campos opcionais pluggy_itau_access_mode e pluggy_santander_access_mode têm padrão strict. Para aplicações pessoais MeuPluggy previamente verificadas, selecione meupluggy_personal explicitamente. Não altere Client ID, Client Secret ou Item ID como parte da atualização. Sandbox permanece separado.

Sincronização automática permanece desativada por padrão. Mantenha open_finance_auto_sync_enabled=false durante a atualização e validação manual. A atualização não emite consentimento, não cria conexões nem promove registros staging ao financeiro oficial.

## Consentimentos

No perfil pessoal, uma coleta financeira efetivamente concluída aparece separada da auditoria: “Coleta financeira concluída”, “Consentimento não validado” e resultado geral PARTIAL. O resultado bruto FAILED/ITEM_ID_DIFFERENT continua preservado e consentimentos estrangeiros são rejeitados. Esta apresentação não concede autorização e não ignora expiração, revogação, identidade incompatível ou escopo financeiro divergente. Strict e sandbox não recebem essa tolerância de apresentação.

## Procedimento de atualização manual

1. Conferir versão atual 0.1.26, banco schema 10 e auto-sync desativado. Fazer backup pré-atualização recuperável do complemento com configuração e /data, além de garantir disponibilidade da imagem/código anterior.
2. No catálogo de complementos, verificar atualização do repositório oficial e versão oferecida 0.1.27-open-finance.1. Não adicionar repositório alternativo nem criar uma segunda instalação.
3. Atualizar o complemento existente em janela controlada. A instalação e reinicialização ficam sob controle do proprietário.
4. Conferir API /api/v2/health: status e banco ok, schema 11 e migrations 11/11 atualizadas. Confirmar configurações preservadas sem exibir seus conteúdos.
5. Conferir registros oficiais, staging, seis áreas Open Finance, privacidade e histórico. Coleta manual e ativação automática são decisões operacionais posteriores; não são disparadas pela release.

## Recuperação coordenada

Interromper diante de erro de migração/integridade, perda de configuração, identidade incompatível ou indisponibilidade persistente da API. Preservar logs sanitizados e a cópia do estado afetado antes de novas tentativas. Manter o complemento parado e auto-sync desativado. Restaurar pelo Supervisor o backup pré-atualização, incluindo configuração e /data schema 10, com imagem/código 0.1.26 correspondente comprovadamente disponível. Confirmar que a imagem selecionada é a anterior antes de iniciar, para impedir reaplicação automática da migration 011. Validar saúde, schema 10, migrations e dados após restauração. Um downgrade somente do código, mantendo banco schema 11, não é recuperação válida. A reversão descarta alterações posteriores ao backup; a homologação em laboratório não garante os mesmos tempos ou disponibilidade de imagem na instalação do proprietário.

## Privacidade das respostas HTTP

As projeções HTTP omitem os identificadores de associação de Item e os valores configurados de credenciais, inclusive no histórico. As identidades internas persistidas e todas as guardas de escopo permanecem intactas; referências de contas, produtos e faturas necessárias à navegação são preservadas. Esta projeção não deve ser reutilizada para autorização ou persistência.
