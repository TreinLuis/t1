# Trabalho 1 — Servidor HTTP/1.1 sobre sockets TCP

Projeto em Python 3.9 ou superior, somente biblioteca padrão, sem instalação de pacotes.
O servidor lê e escreve HTTP manualmente usando sockets TCP. Execute os comandos abaixo
a partir da pasta `t1`. No Windows, troque `python3` por `python` ou `py -3`, conforme a VDI.

## Design em dez linhas

1. `server.py` aceita conexões IPv4 e cria uma thread daemon por conexão.
2. `connection.py` mantém o ciclo de requisições de uma conexão persistente.
3. `http_parser.py` acumula bytes até CRLF CRLF e preserva o excedente.
4. `request_handler.py` implementa GET, HEAD e 405 com Allow.
5. `file_resolver.py` decodifica o caminho e restringe arquivos à raiz real.
6. `http_response.py` serializa cabeçalhos e produz blocos de até 64 KiB.
7. HTTP/1.1 persiste por padrão; `Connection: close` encerra após a resposta.
8. Timeout sem novos bytes encerra conexões ociosas ou requisições incompletas.
9. `tests/` contém clientes de sockets, testes locais/remotos e o benchmark C1/C2.
10. Capturas e relatório são preenchidos pelo grupo com evidência real da rede.

## Executar

```bash
python3 server.py --port 8080 --root ./www --server-name Grupo-NomeDosIntegrantes
```

Abra `http://IP_DO_SERVIDOR:8080/` de **outra máquina**. Encerre o servidor com Ctrl+C.
`0.0.0.0` é o endereço de escuta, não o endereço a colocar no navegador.

| Argumento | Tipo | Padrão | Efeito |
|---|---|---|---|
| `--port` | inteiro | obrigatório | Porta entre 1025 e 65535 |
| `--root` | caminho | obrigatório | Diretório existente a servir; relativo ao diretório de execução |
| `--host` | texto | `0.0.0.0` | Bind IPv4; mantenha o padrão no trabalho; loopback é rejeitado |
| `--idle-timeout` | real | `5.0` | Segundos máximos sem receber novos bytes; positivo e finito |
| `--server-name` | texto ASCII | `Grupo-Redes-T1` | Identificador enviado em Server; personalize para o grupo |
| `--verbose` | flag | desligado | Inclui detalhes de rejeições e interrupções no log |
| `-h`, `--help` | flag | — | Mostra ajuda e sai |

A raiz deve ser administrada pelo grupo. Não permita que processos não confiáveis
alterem arquivos/symlinks durante a execução. A resolução protege contra caminhos
enviados pela rede; não fornece isolamento do sistema de arquivos contra um atacante local.
Mantenha também o conteúdo estável durante as medições para comparar o mesmo recurso.

## Antes do laboratório

Em ambas as máquinas Windows:

```bat
ipconfig
ping -n 20 IP_DA_OUTRA_MAQUINA
```

Em Linux/macOS, use `ip addr`/`ifconfig` e `ping -c 20 IP_DA_OUTRA_MAQUINA`.
Anote IPs, interface usada, perda e RTT médio. Confirme que o Wireshark lista e captura
na interface Ethernet/Wi-Fi real. Se não houver alcance, comunique ao professor.
Se ping estiver bloqueado por política, confirme também a conexão TCP com curl e peça orientação.
O firewall do Windows deve permitir entrada TCP na porta escolhida. Na VDI sem privilégios,
peça ao professor a liberação necessária; o programa não altera o firewall.

## Arquivos

```text
t1/
├── server.py                 # Aceitação TCP e CLI
├── connection.py             # Ciclo HTTP persistente e fechamento
├── http_parser.py            # Parser manual e buffer
├── http_response.py          # Cabeçalhos, MIME, Date e streaming
├── file_resolver.py          # Resolução segura da raiz
├── request_handler.py        # GET, HEAD e erros
├── tests/
│   ├── client.py             # Cliente TCP compartilhado pelos testes
│   ├── test_http.py          # Conformidade e segurança pela rede
│   ├── test_stream.py        # Fragmentação, pipelining e corpo
│   ├── concurrency_test.py   # Cliente lento mais N clientes
│   ├── benchmark.py          # C1/C2 com sockets crus
│   └── run_all.py            # Suíte integrada local e fixtures temporárias
├── www/
│   ├── index.html            # Página para interoperabilidade
│   ├── style.css             # Recurso externo referenciado
│   ├── imagem.svg            # Imagem externa referenciada
│   ├── test.txt              # Recurso fixo para benchmark
│   └── sub/pagina.html       # Página em subdiretório sem index
├── secret.txt               # Fora de www, para demonstrar traversal
├── capturas/README.md        # Capturas reais a produzir
├── README.md
├── DOCUMENTACAO_SERVIDOR.md  # Estudo do código e apresentação
├── RELATORIO_modelo.md       # Modelo sucinto para preencher e exportar como PDF
├── COMPARACAO_ENUNCIADO.md   # Adequação ao original e pendências reais
└── PLANO.md                 # Registro de implementação e validação
```

## Testes

Sem iniciar outro servidor, execute a suíte local:

```bash
python3 tests/run_all.py
```

Ela inicia o servidor em `0.0.0.0` numa porta temporária, acessa-o por loopback, cria
fixtures temporárias, executa os testes e encerra sockets/threads. O resultado esperado
é `PASS` e código de saída zero. **É validação de software; não substitui a experiência
entre máquinas distintas.** No Windows, o teste de symlink pode ser pulado se a conta
não tiver permissão para criá-lo. Os demais testes continuam.

Com o servidor rodando, execute de outra máquina:

```bash
python3 tests/test_http.py IP_DO_SERVIDOR 8080
python3 tests/test_stream.py IP_DO_SERVIDOR 8080
python3 tests/concurrency_test.py IP_DO_SERVIDOR 8080 --clients 10
```

`test_http.py` usa os arquivos `www` entregues e valida status, headers, HEAD, query,
traversal, versões e requisições malformadas. `test_stream.py` envia bytes separados,
três pedidos em uma escrita, pedido mais metade do próximo, corpo seguido de outro
pedido e dez pedidos sequenciais. O teste de concorrência só passa se outros clientes
terminarem enquanto o cliente incompleto ainda puder terminar normalmente.
As falhas produzem código de saída não zero. Rode também dois clientes em **duas máquinas**
ao mesmo tempo e guarde o log com os dois IPs: várias conexões de um só PC não comprovam
sozinhas o requisito presencial.

### Conformidade com curl

No PowerShell, use `curl.exe` para evitar o alias de `Invoke-WebRequest`.
Troque `IP_DO_SERVIDOR` pelo IP real.

| Resultado | Comando |
|---|---|
| 200 GET | `curl -i http://IP_DO_SERVIDOR:8080/test.txt` |
| 200 HEAD | `curl -I http://IP_DO_SERVIDOR:8080/test.txt` |
| 400 sem Host | `curl --http1.1 -i -H "Host:" http://IP_DO_SERVIDOR:8080/` |
| 403 traversal simples | `curl --path-as-is -i http://IP_DO_SERVIDOR:8080/../../Windows/System32/drivers/etc/hosts` |
| 403 traversal codificado | `curl --path-as-is -i http://IP_DO_SERVIDOR:8080/%2e%2e/%2e%2e/secret.txt` |
| 403 traversal em subdiretório | `curl --path-as-is -i http://IP_DO_SERVIDOR:8080/assets/../../../secret.txt` |
| 404 | `curl -i http://IP_DO_SERVIDOR:8080/inexistente` |
| 405 e Allow | `curl -i -X POST http://IP_DO_SERVIDOR:8080/test.txt` |
| Fechamento explícito | `curl -v -H "Connection: close" http://IP_DO_SERVIDOR:8080/test.txt` |

Curl normalmente não gera request lines arbitrariamente malformadas; esses casos são
validados por sockets em `test_http.py`. `--path-as-is` é indispensável para curl não
normalizar `../` antes de enviar a requisição.

## Medir C1 e C2

1. Registre o RTT médio com 20 pings, IPs, interface e configurações do servidor.
2. Use `/test.txt`, 10 requisições e os mesmos computadores para ambos os cenários.
3. Inicie a captura na interface real do cliente ou servidor, sempre no mesmo ponto.
4. Execute apenas C1, aguarde o fechamento TCP, pare e salve `capturas/c1.pcapng`.
5. Repita para C2 e salve `capturas/c2.pcapng`. Não misture navegação/testes na captura.
6. Repita pares C1/C2 se desejar; reporte quantidade de repetições e estatística adotada.

```bash
python3 tests/benchmark.py IP_DO_SERVIDOR 8080 --path /test.txt --requests 10 --mode c1
python3 tests/benchmark.py IP_DO_SERVIDOR 8080 --path /test.txt --requests 10 --mode c2
```

O benchmark mostra tempo total, média por pedido, conexões criadas e bytes dos corpos HTTP.
Ele espera cada resposta completa antes de enviar a seguinte. C2 envia `Connection: close`
apenas no último pedido para que o encerramento também apareça na captura.
Os bytes impressos **não são** bytes totais de rede. O tempo de `perf_counter` também
não é exatamente o intervalo primeira–última trama: registre separadamente.

### Wireshark e tshark

**Filtro de captura (BPF):** `tcp port 8080`.
**Filtro de exibição:** `tcp.port == 8080`.
São sintaxes distintas. Opcionalmente restrinja o par com `host IP_DO_CLIENTE`
(captura) ou `ip.addr == IP_DO_CLIENTE` (exibição).

```bash
tshark -D
tshark -i NUMERO_DA_INTERFACE -f "tcp port 8080" -w capturas/c1.pcapng
```

Rode C1 em outro terminal/máquina, espere os FIN/ACK, e interrompa tshark com Ctrl+C.
Repita o comando de captura alterando o destino para `c2.pcapng`, então rode C2.
Se tshark não estiver disponível, faça tudo pela interface do Wireshark.

```bash
tshark -r capturas/c1.pcapng -Y "tcp.flags.syn == 1 && tcp.flags.ack == 1" -T fields -e tcp.stream
tshark -r capturas/c1.pcapng -q -z io,stat,0
tshark -r capturas/c1.pcapng -q -z conv,tcp
tshark -r capturas/c1.pcapng -Y "tcp.port == 8080" -T fields -e frame.number -e frame.time_relative -e frame.len -e tcp.stream -e tcp.flags -e tcp.len
```

Repita substituindo `c1` por `c2`. Em *Statistics → Capture File Properties*, obtenha
contagem, bytes e duração, usando capturas já restritas ao experimento. Se houver tráfego
extra, filtre as tramas e some apenas `frame.len` do experimento. Tempo da captura = último
`frame.time_relative` menos primeiro. Use a mesma convenção de bytes nos dois cenários:
`frame.len` representa tamanho das tramas capturadas, sem assumir preâmbulo/IFG da mídia.

SYN/ACK é um indicador de handshake; conte **streams distintos** e confira SYN, SYN/ACK
e ACK de cada um. Retransmissões de SYN/ACK não são novos handshakes. Em uma execução
sem falhas, C1 deve ter 10 conexões e C2 uma; isso é expectativa, não resultado medido.

Filtros de exibição úteis:

```text
tcp.port == 8080
tcp.flags.syn == 1 && tcp.flags.ack == 1
tcp.stream == NUMERO_DO_STREAM
http.request.method == "GET"
tcp.flags.fin == 1
tcp.analysis.retransmission
tcp.flags.ack == 1 && tcp.len == 0
```

Se HTTP não for reconhecido, use *Analyze → Decode As → HTTP* para a porta.
Um GET pode ocupar múltiplas tramas, e uma trama pode transportar ACK e dados.

### Overhead de abrir e fechar

Para cada stream C1, marque SYN, SYN/ACK e ACK final do handshake; depois os FIN e seus
ACKs de encerramento. Some quantidade e `frame.len` das tramas **sem dados HTTP** usadas
nessas fases. O filtro `tcp.flags.ack == 1 && tcp.len == 0` ajuda a localizar candidatos,
mas também inclui ACKs de dados: não os some indiscriminadamente. Use sequência,
acknowledgment e posição na conversa para identificar a finalidade.
Se o ACK de handshake ou FIN estiver junto de dados, a trama não é “só overhead”; indique
o critério usado, reporte-a separadamente e não conte seus bytes duas vezes.

### Cálculos

```text
economia_pacotes(%) = 100 × (pacotes_C1 − pacotes_C2) / pacotes_C1
economia_bytes(%)   = 100 × (bytes_C1 − bytes_C2) / bytes_C1
T_C1 ≈ 2 × N × RTT
T_C2 ≈ (N + 1) × RTT
T_C1 − T_C2 ≈ (N − 1) × RTT
```

O modelo supõe pedidos sequenciais, objetos pequenos, TCP sem perda, um RTT de handshake
por conexão e um RTT de pedido/resposta. Ignora transmissão, processamento e tempo de
encerramento. Para N=10, há nove handshakes extras em C1. Delayed ACK, Nagle, perdas,
escalonamento e tamanho de arquivo podem afastar o resultado do modelo. Persistência
tende a economizar mais tempo com RTT maior e mais requisições por conexão.

## Interoperabilidade e entrega

Abra a página do outro grupo e peça que abram a sua. Confirme HTML, CSS e imagem em
Ferramentas do Desenvolvedor → Rede; registre todos com sucesso. Faça o teste nos dois sentidos.

Preencha [RELATORIO_modelo.md](RELATORIO_modelo.md), inclua imagens anotadas e exporte para
`RELATORIO.pdf` pelo editor disponível. A documentação extensa é material de estudo;
o relatório entregue deve permanecer sucinto. Confira [COMPARACAO_ENUNCIADO.md](COMPARACAO_ENUNCIADO.md).

O [guia de estudo](GUIA_DE_ESTUDO_NAO_ENTREGAR.md) explica cada método e a comunicação entre os módulos; é material interno do grupo e deve ficar fora da entrega.

Antes de compactar, exclua o guia de estudo, `__pycache__`, `.pyc`, logs temporários e arquivos de build.
Inclua código, README, `www`, relatório PDF e capturas `.pcapng` verdadeiras. Os scripts
de teste podem acompanhar. Um integrante entrega o ZIP/TAR no Moodle com o grupo cadastrado.
Não há capturas nem resultados de rede inventados neste projeto.

## Escopo e referências

Suporte didático: GET/HEAD de origem, HTTP/1.0/1.x, Content-Length, persistência e arquivos
estáticos. Cabeçalhos limitados a 16 KiB; corpo de pedido até 1 MiB. Transfer-Encoding
retorna 400, Expect retorna 417, versão major incompatível retorna 505. Não implementa
TLS, proxy, chunked, compressão, ranges ou caching condicional. Não é implementação
completa de todos os requisitos de um servidor HTTP de produção.

Referências: [RFC 9112](https://www.rfc-editor.org/rfc/rfc9112.html) para framing e conexões;
[RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) para semântica e Date;
[manual do tshark](https://www.wireshark.org/docs/man-pages/tshark.html) para captura e estatísticas.
