# Evidências sintéticas da SnapTrade Personal

Capturas do navegador com o aplicativo WSGI, uma base SQLite descartável e uma corretora simulada. As larguras verificadas foram 390, 768, 1440 e 1920 px. Os cenários cobrem a carteira, saldos em moedas originais, BRL e USD, histórico em formação, atividades, proventos, estados vazio e parcial, limitação de chamadas, configuração de coleta e três níveis de privacidade.

A checagem automatizada verifica rótulos de controles, navegação por teclado entre abas, foco no detalhe do ativo, contraste no título da carteira e ausência de transbordamento horizontal nas quatro larguras. A validação com leitor de tela cabe ao proprietário.

O teste de volume projetou páginas de 12.000 atividades e 5.001 posições locais em 0,760 s, com pico de 14,2 MiB alocados pelo Python e 18 comandos SQLite no laboratório Windows. O teste não mede memória total do processo nem desempenho no equipamento do proprietário. A campanha C6R local concluiu 100 iterações com integridade e idempotência preservadas.

Para reproduzir as capturas, configure `OF_SNAPTRADE_SHOTS` e execute `python -m unittest discover -s tests -p test_snaptrade_036_ui.py` com `finance-v17/src` e `tests` em `PYTHONPATH` e o ambiente Playwright preparado pelo workflow.
