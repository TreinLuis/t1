# Comparação com o enunciado original

Revisão do projeto entregue em `t1` contra o enunciado original enviado pelo usuário.
**Resultado:** a implementação cobre os requisitos funcionais previstos e os testes
locais passaram. **A entrega acadêmica ainda depende das evidências de rede, do teste
presencial e do relatório final preenchido e exportado para PDF.**

## Implementação — Parte 1

| Requisito original | Situação no projeto | Evidência / observação |
|---|---|---|
| Executar na VDI sem admin/runtime adicional | Condicionado ao ambiente | Python 3.9+ e biblioteca padrão; confirmar que a VDI possui Python compatível |
| Usar socket/bind/listen/accept/recv/send | Implementado | server.py, http_parser.py e connection.py usam sockets TCP diretamente; sendall é a variante de envio completo |
| Nenhuma biblioteca HTTP de servidor | Atendido | Parsing e serialização próprios; urllib.parse.unquote apenas decodifica caminho |
| Porta acima de 1024 | Implementado | CLI aceita 1025–65535; porta 0 existe apenas no teste interno para o SO escolher porta temporária |
| Bind 0.0.0.0 | Implementado | Padrão da CLI e dos testes; manter --host padrão no laboratório; loopback é rejeitado |
| CLI --port e --root | Implementado | Ambos obrigatórios; demais parâmetros descritos no README |
| Request line e headers CRLF | Implementado/testado | RequestReader; erros de linha/cabeçalho, Host e versão na suíte |
| TCP como fluxo e preservação do excedente | Implementado/testado | Byte a byte, três pedidos juntos, pedido mais metade do próximo e corpo seguido de GET |
| Percent-decoding | Implementado/testado | FileResolver; valida antes de resolver destino; query separada |
| GET / HEAD com mesmo Content-Length | Implementado/testado | GET/HEAD para sucesso/erros; HEAD em pipeline e erros de parsing; Date depende do instante |
| Demais métodos 405 e Allow | Implementado/testado | RequestHandler; DELETE e POST com corpo |
| Status line HTTP/1.1 | Implementado/testado | HttpResponse; cliente independente confere versão |
| Content-Length inclusive erros/HEAD | Implementado/testado | fstat para arquivo; tamanho dos bytes UTF-8 para erro |
| MIME das oito extensões mínimas | Implementado/testado | Tabela com 12 extensões; desconhecida application/octet-stream |
| Date IMF-fixdate GMT | Implementado/testado | email.utils com UTC/usegmt; independente de locale |
| Server identifica grupo | Implementado; personalizar | --server-name; padrão genérico Grupo-Redes-T1 |
| 200, 400, 403, 404, 405 | Implementado/testado | tests/test_http.py e comandos curl documentados |
| Arquivos fora da raiz nunca servidos por traversal | Implementado/testado para entradas de rede | realpath/commonpath; traversal codificado, prefixo semelhante, symlink de pasta e index; raiz deve ser administrada e estável |
| Pelo menos três ataques, um codificado | Scripts prontos; evidência real pendente | Oito vetores no teste remoto; tabela de três no relatório para preencher |
| Concorrência sem bloquear por cliente lento | Implementado/testado localmente | 12 clientes progrediram com outro incompleto; threads daemon por conexão |
| Duas máquinas clientes simultâneas | Pendente de laboratório | Guardar log/captura com dois IPs e tempos sobrepostos |
| Justificativa de concorrência | Modelo/documentação prontos | Threads por simplicidade de I/O bloqueante; escala limitada pelo número de threads |
| Convenção de identificadores escolhida pelo usuário | Aplicada ao código escrito | Métodos i_* e variáveis *_a; construtores/context manager ligados aos protocolos nativos do Python |

## Parte 2 e medição

| Requisito | Situação | Evidência / próximo passo |
|---|---|---|
| HTTP/1.1 persistente por padrão | Implementado/testado | Dez pedidos sequenciais e pipeline no mesmo socket |
| Connection: close na resposta e fechamento | Implementado/testado | Token close tem prioridade e testes confirmam EOF |
| Timeout ocioso sugerido 5 s | Implementado/testado | CLI padrão 5 s; suíte usa 0,7 s para acelerar e testa silêncio/cabeçalho/corpo parcial |
| C1: dez conexões, dez pedidos | Benchmark pronto/testado localmente | tests/benchmark.py --mode c1; suíte confirma 10 conexões |
| C2: uma conexão, dez pedidos | Benchmark pronto/testado localmente | --mode c2; suíte confirma 1 conexão e mesmo total de corpo HTTP |
| Medir em máquinas distintas | Pendente | Usar IP real; loopback só foi usado para testes de software |
| Registrar RTT médio | Pendente | ipconfig/ping antes da captura; campos no relatório |
| Handshakes completos, pacotes, bytes e tempo | Roteiro pronto; valores pendentes | Wireshark/tshark; contar streams com handshake confirmado, sem duplicar retransmissões |
| Capturas C1/C2 .pcapng | Pendente | capturas/README.md explica arquivos esperados; nenhum PCAP vazio/fictício foi criado |

## Relatório e apresentação

| Item do original | Material entregue | Situação final |
|---|---|---|
| Arquitetura e conformidade | README, documentação e seções 1–2 do modelo | Completar respostas observadas |
| Três tentativas de traversal | Modelo seção 3, curl e testes | Anexar evidência real |
| GET completo de outra máquina com handshake/FIN | Roteiro e seção 4 | Capturar/anotar tramas reais |
| Atendimento simultâneo | Teste e seção 5 | Comprovar dois IPs de máquinas distintas |
| RTT e tabela C1/C2 | Modelo seções 6–7 | Preencher quatro métricas da captura |
| Economia percentual de pacotes e bytes | Fórmulas prontas | Substituir com números medidos |
| Overhead de abrir/fechar C1 | Roteiro e seção 8 | Classificar tramas de controle; não somar todos os ACKs cegamente |
| Análise de RTT e conclusão | Modelo seções 9–10 | Confrontar previsão (N−1)·RTT com medição |
| Página HTML com recursos para interoperabilidade | www/index.html, style.css e imagem.svg | Abrir de outra máquina e testar nos dois sentidos com outro grupo |
| Todos explicarem qualquer trecho | DOCUMENTACAO_SERVIDOR.md, referência completa e 24 perguntas | Estudo/apresentação são responsabilidade dos integrantes |
| PDF único sucinto | RELATORIO_modelo.md | Preencher e exportar RELATORIO.pdf; documentação de estudo não substitui relatório |
| ZIP/TAR sem temporários | Árvore pronta para organizar | Remover caches/logs, incluir PDF/capturas reais e compactar após coleta |
| Até três integrantes/Moodle/uma entrega/prazo | Campos e checklist no README | Cadastrar/confirmar grupo, cronograma e integrante que envia |

## Diferenças e limites explicitados

- O projeto fica em `t1`, conforme solicitado, e mantém a pasta `tests` após confirmação do usuário.
- Os nomes finais seguem a escolha do usuário pelo original; a documentação usa os nomes reais do código.
- A verificação inicial entre máquinas, exigida antes da implementação, não pôde ser feita
  neste ambiente de desenvolvimento. O grupo deve confirmá-la no laboratório e registrar a situação.
- A suíte foi executada no macOS com Python 3.9; Windows/Linux/VDI não foram executados aqui.
  Só APIs portáteis da biblioteca padrão foram utilizadas, mas o ambiente real precisa ser validado.
- Nenhum resultado local foi inserido como medição de desempenho exigida pelo professor.
- O original não exige todos os recursos de um servidor HTTP de produção. Este projeto
  rejeita Transfer-Encoding e Expect e limita cabeçalhos/corpos, como descrito no README.
- A proteção de caminho segue a arquitetura solicitada (realpath + commonpath); não isola
  contra um processo local hostil trocando symlinks entre validação e abertura. A raiz deve
  ser controlada pelo grupo. Arquivos servidos não devem mudar durante o experimento.

## Verificação executada

`python3 tests/run_all.py`: **24 testes, zero falhas e zero erros**, com sockets TCP reais
locais, incluindo teste regressivo de HEAD com cabeçalhos excessivos. A revisão independente
encontrou esse caso; foi reproduzido antes da correção e passou depois. A documentação
contém referência das 72 funções/métodos escritos, além das classes sem métodos e dataclasses.

Também foi iniciado o servidor pela CLI, e os scripts HTTP, fluxo, concorrência e benchmark nos dois modos terminaram com código zero. Foram verificadas rejeições de porta baixa, timeout NaN e bind loopback. Ctrl+C encerrou o servidor sem traceback.

Os números de tempo/pacotes/bytes de rede, o RTT, as capturas, o teste em duas máquinas,
a interoperabilidade presencial e o PDF final **permanecem pendentes**, sem resultados inventados.
