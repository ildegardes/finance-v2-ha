# PR 11 — identidade OCI e qualificação pendente

## Identidade dos objetos

- Build ARM64 reconstruído a partir de `git archive` do commit `a78879fcc1aa01354c339de8259a193b44c51b10`. A árvore Git de `finance-v17` desse commit e de `ab86731` é a mesma: `cd98820694d460c382075fc0769d875b30d05fa3`. Os commits diferem somente no workflow e em documentação; isto comprova a identidade da árvore do contexto, não homologação funcional.
- Dockerfile: SHA-256 `ba15e7081fd251c5586fa493cae2697d3e396b492666d28c61b9588f01ebf1b7`; dependências: SHA-256 `a1f3bc227364f80a373b16f4ed1c5115581109a54a899246d724478a09bf0ab1`.
- Host: Docker Engine 29.9.2, Buildx 0.38.1, BuildKit 0.34.0, armazenamento overlay2. Guest: Engine 29.7.2, armazenamento containerd overlayfs.
- O índice OCI do arquivo aponta para o **manifesto** `sha256:13a42f670435331367096f40f2e4829b3d0b0bba589e5348df0c1c9fcef30d68`, que aponta para a **configuração** `sha256:6973ab983f758a0a0d9c91341dabee5a2a2f073bd5adb45d8d6828927e900295`. São objetos diferentes, não uma divergência nos bytes do mesmo objeto. O guest apresentou o manifesto como ID; o host apresentou o digest da configuração como ID.
- O manifesto, a configuração e as 12 camadas originais foram lidos do armazenamento containerd do guest e seus SHA-256 conferiram com os blobs no arquivo exportado; os digests das camadas correspondem, na ordem, aos 12 DiffIDs da configuração. Plataforma `linux/arm64`. Entrypoint, Cmd, ambiente, usuário, labels, histórico e RootFS normalizados no `docker inspect` coincidiram entre host e guest. Isso não significa que o Supervisor tenha executado a imagem.
- SHA-256 do arquivo compactado transferido, conferido na origem e no guest: `ffc2f77612e08263e19bc66b18bf9fbcff9d92d0a5e44a0932be3e106cbe5eb0`. O digest do índice do arquivo é `sha256:f036887e9c405129aabf7ab4920feb355eec081b13a690434b1e69051debee46`.

## Isolamento e bloqueio

A VM descartável usa uma sobreposição própria, com a cadeia de referência montada somente para leitura e sem portas publicadas. A regra de saída observada começa por REJECT, e as opções examinadas desabilitam sincronização automática e usam identificadores bancários sintéticos. A origem de todos os dados, tokens e volumes do disco herdado não foi auditada integralmente: não declarar o laboratório completamente sintético.

A tentativa de preparar o script de troca da imagem e inicialização do add-on foi rejeitada pela política automática com `blocked by policy`, sem motivo mais específico disponibilizado. Não repetir a operação por outro mecanismo. Instalação e atualização permanecem `BLOCKED_BY_POLICY`; não foi executada homologação da candidata no Supervisor.

Para retomar, um operador autorizado deve primeiro estabelecer um laboratório Supervisor independente criado do zero, sem rotas nem volumes de produção, com credenciais e dados sintéticos e saída bloqueada. Deve então obter um procedimento de instalação explicitamente permitido pelo ambiente, sem reduzir controles, e registrar o identificador da VM, os objetos OCI comparáveis e a imagem efetivamente executada. Só depois devem ser testados instalação, autenticação, portas, restart, atualização sobre cópia descartável, integridade, backup restaurável e rollback que preserve dados posteriores. O procedimento operacional final depende dessas evidências; este documento não autoriza alterar produção.

## Verificações independentes e ressalvas

- Analytics: 32 testes; administração sintética: 17; privacidade de saída: 6. Os testes de interface para visão geral, movimentações, atributos privados, concorrência de produtos e Conexões passaram localmente. Não equivalem à homologação integral dos quatro marcos.
- Inspeção das seis capturas móveis sintéticas: os valores estavam mascarados, mas a máscara genérica `R$` também aparecia para USD e quantidades em Investimentos. A interface foi corrigida para usar máscara neutra nesses campos; os testes verificam ocultação visual, atributos acessíveis e alternância. As capturas anteriores permanecem como evidência do defeito, não representam o estado corrigido. As capturas de Visão geral e Conexões mostram o menu lateral aberto sobre o conteúdo e não permitem avaliar toda a área nessa região. São amostras, não uma auditoria responsiva completa.
- Não houve teste real de leitor de tela. Antes de homologar acessibilidade, operador deve percorrer as seis abas com leitor de tela, verificar nomes, estados, foco, mensagens, gráficos e privacidade; registrar ambiente e resultados. Inspeção da árvore acessível não substitui esse teste.
