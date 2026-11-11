# Implantação proposta e critérios de execução

Esta é uma instrução para revisão. O PR é draft; não há merge, release estável ou instalação autorizada. Não há comandos para executar SQL em produção.

1. Revisar o diff, o manifesto, os resultados Windows/ARM64/Supervisor e os oito hashes protegidos. A base deve permanecer a tag declarada e schema 11; o slug finance_v17, porta 8766, /data e nomes de configuração permanecem iguais. A instalação do repositório oficial conserva o slug 8327184f_finance_v17.
2. Obter autorização separada para eventual merge/distribuição/atualização. Este procedimento não torna a branch uma atualização estável disponível.
3. Antes de qualquer manutenção real, comprovar backup consistente e atual de configuração, banco e arquivos auxiliares necessários, com procedimento de restauração testado. Preservar o backup e os recibos privados; não colocar banco, options.json ou recibos no GitHub. Não usar cópia isolada do SQLite principal enquanto há WAL ativo.
4. Confirmar auto-sync desativado, ausência de coletas concorrentes e compromisso de não iniciá-las durante a manutenção. A operação verifica novamente runs e leases; não os limpa. Qualquer lease, mesmo vencido, exige investigação separada.
5. Após eventual implantação autorizada, acessar a interface com a credencial do proprietário e abrir Conexões. A abertura não executa manutenção. Clicar em Verificar elegibilidade.
6. Prosseguir apenas com ELIGIBLE, CURRENT_BINDING_MATCH=MISMATCH, SWAPPED_BINDING_MATCH=MATCH, 26 falhas AUTH_FAILED, zero dados importados e nenhum bloqueio. Se aparecer ALREADY_CORRECT, não há correção necessária; não interpretar como autorização de coleta.
7. Após autorização expressa para a correção em produção, marcar a confirmação de backup e clicar em Corrigir vínculo Santander. Confirmar o diálogo. A preparação/confirmacão é de uso único; não repetir diante de resultado incerto. O backend repetirá todas as verificações em transação.
8. Conferir APPLIED, uma linha alterada, histórico e dados protegidos preservados. Consultar novamente a elegibilidade por ação explícita e comprovar CURRENT_BINDING_MATCH=MATCH. Não iniciar sincronização nesta operação.
9. COMMITTED_AUDIT_PENDING significa que houve commit e falta fechar a auditoria. Não restaurar nem repetir cegamente; inspecionar a elegibilidade e usar **Reconciliar auditoria Santander**. Essa ação apenas classifica o recibo pelo estado encontrado. Falha de rede do navegador também exige inspeção antes de qualquer nova confirmação.
10. Qualquer coleta posterior, mudança de credenciais, atualização ou ativação de agendamento exige autorização própria. A guarda de consentimento e as 66 referências Itaú sem fatura permanecem inalteradas.

## GO / NO_GO

GO para revisão da candidata: suítes locais e homologação declarada aprovadas, artefato rastreável e protegido, nenhum dado real incluído. GO para executar em produção exige ainda autorização separada, backup recuperável, instalação aprovada e todas as verificações dinâmicas ELIGIBLE. Qualquer dependência financeira, vínculo desconhecido, alteração de schema/configuração, histórico diferente, lease, run ativo, falha de integridade ou auditoria ambígua é NO_GO. Não há fallback para apagar histórico ou relaxar os critérios.

Se o acesso passar pelo Cloudflare Tunnel, use uma rota privada ou confira a política do Cloudflare Access e a proteção do caminho direto até o serviço. Para origem HTTPS pública encaminhada a HTTP local, teste a origem exata e a sessão em homologação. O aplicativo compara a origem WSGI ou a lista FINANCE_V2_CORS_ORIGINS e ignora cabeçalhos encaminhados como prova de identidade. Confira o atributo Secure do cookie no navegador e mantenha a administração em acesso privado enquanto a configuração não estiver validada.
