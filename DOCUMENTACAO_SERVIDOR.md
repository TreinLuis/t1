# Documentação do servidor — guia para os três integrantes

## 1. Visão geral

O servidor oferece arquivos estáticos por HTTP/1.1 implementado manualmente sobre TCP.
Cada conexão tem uma thread e um buffer próprio. A lógica não pressupõe que um recv
corresponda a uma requisição. Nenhum módulo HTTP de servidor é utilizado.

```text
server.i_main()
  → HttpServer(...).i_start(): socket → bind → listen(128)
      → i_accept_loop(): accept → thread daemon
          → i_serve_connection(): ConnectionHandler.i_run()
              ┌→ RequestReader.i_read_request()
              │    recv → buffer → CRLF CRLF → parse → consumir corpo
              │    preserva bytes da próxima mensagem
              │  → RequestHandler.i_handle(request)
              │    → FileResolver.i_resolve(path) → arquivo aberto/fstat
              │    → HttpResponse (200 ou erro)
              │  → i_keep_alive() → Connection e demais headers
              │  → i_send(): i_to_head_bytes() → sendall(headers)
              │               i_body_bytes() → sendall(blocos)
              └── se persistente, volta para a próxima requisição
                  senão/timeout/EOF/erro: i_close() → shutdown → drenar → close
```

## 2. Como rodar e verificar a rede

Python 3.9+ já instalado na VDI; nenhuma dependência externa. Na pasta `t1`:

```bash
python3 server.py --port 8080 --root ./www --server-name Grupo-NomeDosIntegrantes
```

No Windows use `python`/`py -3` se necessário. Os argumentos são:

| Opção | Tipo/padrão | Efeito |
|---|---|---|
| `--port` | int, obrigatório | 1025–65535 |
| `--root` | str, obrigatório | Diretório existente; caminho relativo ao terminal |
| `--host` | str, `0.0.0.0` | IPv4 de escuta; manter padrão no trabalho; loopback rejeitado |
| `--idle-timeout` | float, `5.0` | Limite positivo/finito sem novos bytes |
| `--server-name` | str, `Grupo-Redes-T1` | ASCII imprimível enviado em Server |
| `--verbose` | bool, falso | Log de detalhes de erros |
| `--help` | flag | Ajuda e saída |

Descubra os IPs com `ipconfig`, teste `ping -n 20 IP`, anote o RTT e confira captura na
interface real no Wireshark. Em Linux/macOS: `ip addr`/`ifconfig`, `ping -c 20 IP`.
Abra `http://IP_DO_SERVIDOR:8080/` em outra máquina. `0.0.0.0` não é o destino do navegador.
Se o firewall bloquear a porta na VDI, solicite liberação ao professor; não precisa
instalar pacote nem executar este servidor como administrador. O grupo precisa confirmar
o ambiente real; os testes locais não fazem essa verificação por ele.

## 3. Estrutura e propriedade dos recursos

A árvore completa, com cada arquivo, está no [README](README.md#arquivos).
Os seis módulos de produção não importam `tests`. `tests/client.py` é um leitor
independente de respostas e não reaproveita o parser do servidor, evitando validar
um erro com a mesma implementação que o produziu.

| Recurso | Quem cria | Quem encerra |
|---|---|---|
| Socket de escuta | HttpServer.i_start | HttpServer.i_shutdown |
| Socket aceito | accept | ConnectionHandler.i_close; shutdown do servidor acorda a thread |
| Thread daemon | HttpServer.i_accept_loop | Retorna de i_serve_connection; servidor aguarda com join |
| Buffer HTTP | RequestReader.i_init | Descartado ao terminar a conexão |
| Arquivo aberto | RequestHandler.i_handle | HttpResponse.i_close no finally de i_send |
| Fixtures de testes | tests/run_all.py | TemporaryDirectory ao terminar |

Os identificadores abaixo refletem o código entregue. Construtores usam o método
`i_init`, associado ao protocolo nativo `__init__`; em `RawClient`, `i_enter`/`i_exit`
são associados a `__enter__`/`__exit__` para permitir `with`. Esses nomes especiais são
ligações exigidas pelo Python, sem lógica adicional. Os métodos gerados por dataclass
não são implementados manualmente.

## 4. Referência por módulo

### server.py

#### HttpServer

Orquestra a escuta. Os campos de estado são inicializados em i_init; port_a é atualizado após bind para permitir porta temporária nos testes.

##### `HttpServer.i_init`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpServer.i_init(self_a, host_a: str, port_a: int, root_a: str, idle_timeout_a: float=5.0, server_name_a: str='Grupo-Redes-T1') -> None` |
| O que faz | Valida configuração e prepara estado compartilhado. |
| Como faz | Rejeita loopback, timeout não positivo/infinito e Server não ASCII; cria resolver, handler, config, Event, Lock e conjuntos. |
| Erros/conexão | ValueError em configuração/raiz inválida; OSError na resolução do host; ainda não aceita conexões. |
| Quem chama | server.i_main e tests/run_all.py, por HttpServer(...). |
| Por quê | Validar antes do bind evita iniciar uma configuração inutilizável. |
| Quem chama internamente | `ConnectionConfig`, `threading_a.Event`, `threading_a.Lock`, `set`, `ipaddress_a.ip_address`, `ValueError`, `any`, `RequestHandler`, `socket_a.gethostbyname`, `math_a.isfinite`, `FileResolver`, `ord` |

##### `HttpServer.i_start`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpServer.i_start(self_a) -> None` |
| O que faz | Abre o socket de escuta e executa o servidor até parar. |
| Como faz | Cria AF_INET/SOCK_STREAM, SO_REUSEADDR, bind, listen(128), timeout de accept de 0,25 s; guarda porta efetiva e entra no accept loop. |
| Erros/conexão | OSError sobe ao chamador; finally sempre chama i_shutdown. Porta 0 é usada apenas internamente pelos testes. |
| Quem chama | server.i_main ou thread da suíte local. |
| Por quê | SO_REUSEADDR facilita reinício; timeout permite observar o pedido de parada. |
| Quem chama internamente | `socket_a.socket`, `self_a.sock_a.setsockopt`, `self_a.sock_a.bind`, `self_a.sock_a.listen`, `self_a.sock_a.settimeout`, `logging_a.info`, `self_a.i_accept_loop`, `self_a.i_shutdown`, `self_a.sock_a.getsockname` |

##### `HttpServer.i_accept_loop`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpServer.i_accept_loop(self_a) -> None` |
| O que faz | Aceita clientes e cria uma thread daemon por socket. |
| Como faz | A cada accept prepara worker; com Lock verifica parada, registra socket/thread e inicia; timeout volta ao laço. |
| Erros/conexão | Timeout não é falha; OSError durante shutdown termina, outro OSError propaga. Socket aceito após parada é fechado. |
| Quem chama | HttpServer.i_start. |
| Por quê | Espera de um cliente ocorre no worker e não bloqueia novas conexões. |
| Quem chama internamente | `self_a.stopping_a.is_set`, `threading_a.Thread`, `self_a.sock_a.accept`, `self_a.connections_a.add`, `self_a.workers_a.add`, `worker_a.start`, `sock_a.close` |

##### `HttpServer.i_serve_connection`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpServer.i_serve_connection(self_a, sock_a: socket_a.socket, addr_a: tuple) -> None` |
| O que faz | Executa o handler de uma conexão e retira seu registro. |
| Como faz | Constrói ConnectionHandler, chama i_run e no finally remove socket e thread dos conjuntos sob Lock. |
| Erros/conexão | O handler trata erros de socket; finally limpa registros mesmo se outra exceção subir. |
| Quem chama | Thread criada em i_accept_loop. |
| Por quê | Centraliza o ciclo de vida e evita acumular referências a workers já concluídos. |
| Quem chama internamente | `ConnectionHandler(sock_a, addr_a, self_a.config_a).i_run`, `self_a.connections_a.discard`, `self_a.workers_a.discard`, `ConnectionHandler`, `threading_a.current_thread` |

##### `HttpServer.i_shutdown`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpServer.i_shutdown(self_a) -> None` |
| O que faz | Interrompe escuta e conexões ativas e aguarda workers. |
| Como faz | Marca Event, fecha listener, copia conjuntos sob Lock, faz SHUT_RDWR nos sockets e join de até um segundo por thread. |
| Erros/conexão | Ignora OSError de sockets já encerrados; não faz join na própria thread. |
| Quem chama | Finally de i_start e suíte local. |
| Por quê | Acordar recv bloqueado evita esperar todo o timeout ocioso ao encerrar. |
| Quem chama internamente | `self_a.stopping_a.set`, `self_a.sock_a.close`, `list`, `sock_a.shutdown`, `threading_a.current_thread`, `worker_a.join` |

##### `i_main`

| Campo | Descrição |
|---|---|
| Assinatura | `i_main() -> None` |
| O que faz | Interpreta CLI, configura log e executa HttpServer. |
| Como faz | Argparse exige porta/raiz, valida porta alta, configura formato com thread e captura Ctrl+C ou erros de inicialização. |
| Erros/conexão | Argparse retorna código 2 para uso inválido; OSError/ValueError produz saída 1; Ctrl+C é encerramento solicitado. |
| Quem chama | Bloco if __name__ da CLI. |
| Por quê | Uma entrada única mantém parâmetros documentados e erros legíveis. |
| Quem chama internamente | `argparse_a.ArgumentParser`, `parser_a.add_argument`, `parser_a.parse_args`, `logging_a.basicConfig`, `parser_a.error`, `HttpServer`, `server_a.i_start`, `logging_a.info`, `parser_a.exit` |

### connection.py

#### ConnectionConfig

Dataclass imutável: handler_a: RequestHandler, idle_timeout_a: float, server_name_a: str. Construtor gerado recebe esses três valores; compartilhada entre workers.

#### ConnectionHandler

Dona do socket aceito, endereço, config e reader. Só uma thread executa i_run para essa conexão.

##### `ConnectionHandler.i_init`

| Campo | Descrição |
|---|---|
| Assinatura | `ConnectionHandler.i_init(self_a, sock_a: socket_a.socket, addr_a: tuple, config_a: ConnectionConfig) -> None` |
| O que faz | Guarda socket, endereço, configuração e cria um RequestReader. |
| Como faz | Usa limite de 16384 bytes para cabeçalhos, com buffer exclusivo da conexão. |
| Erros/conexão | Não inicia leitura; socket será liberado pelo finally de i_run. |
| Quem chama | HttpServer.i_serve_connection, por ConnectionHandler(...). |
| Por quê | Estado por conexão impede misturar bytes de clientes diferentes. |
| Quem chama internamente | `RequestReader` |

##### `ConnectionHandler.i_run`

| Campo | Descrição |
|---|---|
| Assinatura | `ConnectionHandler.i_run(self_a) -> None` |
| O que faz | Processa pedidos sequencialmente no mesmo socket. |
| Como faz | Aplica timeout; lê pedido e corpo; pede resposta; decide persistência; adiciona Date/Server/Connection; envia e registra bytes; repete se permitido. |
| Erros/conexão | HttpParseError vira erro HTTP com close; IdleTimeout/EOF termina silenciosamente; OSError encerra. Finally sempre chama i_close. |
| Quem chama | HttpServer.i_serve_connection. |
| Por quê | Separar leitura de parsing e política de conexão permite preservar o fluxo corretamente. |
| Quem chama internamente | `self_a.sock_a.settimeout`, `self_a.i_close`, `response_a.headers_a.update`, `self_a.i_send`, `logging_a.info`, `logging_a.debug`, `self_a.reader_a.i_read_request`, `self_a.config_a.handler_a.i_handle`, `self_a.i_keep_alive`, `HttpResponse.i_error`, `i_format_http_date` |

##### `ConnectionHandler.i_keep_alive`

| Campo | Descrição |
|---|---|
| Assinatura | `ConnectionHandler.i_keep_alive(self_a, request_a: HttpRequest) -> bool` |
| O que faz | Decide se aceita outro pedido na conexão. |
| Como faz | Separa Connection por vírgula, normaliza tokens; close vence; HTTP/1.0 só persiste com keep-alive; demais versões aceitas 1.x persistem. |
| Erros/conexão | Não realiza I/O e não fecha diretamente. |
| Quem chama | ConnectionHandler.i_run. |
| Por quê | Connection é uma lista case-insensitive, não uma comparação simples de string. |
| Quem chama internamente | `token_a.strip().lower`, `request_a.i_header('connection').split`, `token_a.strip`, `request_a.i_header` |

##### `ConnectionHandler.i_send`

| Campo | Descrição |
|---|---|
| Assinatura | `ConnectionHandler.i_send(self_a, response_a: HttpResponse) -> int` |
| O que faz | Envia cabeçalhos e blocos do corpo; retorna total de bytes HTTP. |
| Como faz | sendall dos cabeçalhos, iteração de i_body_bytes e sendall por bloco; finally fecha o arquivo da resposta. |
| Erros/conexão | OSError no envio/leitura propaga para i_run, que encerra; não tenta uma segunda resposta parcial. |
| Quem chama | ConnectionHandler.i_run. |
| Por quê | sendall lida com escritas parciais; finally libera o arquivo também em HEAD e erro. |
| Quem chama internamente | `response_a.i_to_head_bytes`, `self_a.sock_a.sendall`, `len`, `response_a.i_body_bytes`, `response_a.i_close` |

##### `ConnectionHandler.i_close`

| Campo | Descrição |
|---|---|
| Assinatura | `ConnectionHandler.i_close(self_a) -> None` |
| O que faz | Encerra a conexão com drenagem limitada. |
| Como faz | SHUT_WR; calcula deadline total de 0,2 s; lê dados até EOF/deadline; close no finally. |
| Erros/conexão | Ignora OSError, incluindo timeout ou peer que já desconectou. |
| Quem chama | Finally de ConnectionHandler.i_run. |
| Por quê | Reduz risco de RST por dados não lidos sem permitir drenagem infinita. |
| Quem chama internamente | `self_a.sock_a.shutdown`, `self_a.sock_a.close`, `time_a.monotonic`, `self_a.sock_a.settimeout`, `self_a.sock_a.recv` |

### http_parser.py

#### HttpRequest

Dataclass: method_a, target_a, path_a, query_a, version_a (str), headers_a (dict, padrão vazio), body_a (bytes, padrão vazio). Construtor gerado nessa ordem; path_a permanece codificado até FileResolver.

##### `HttpRequest.i_header`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpRequest.i_header(self_a, name_a: str) -> str` |
| O que faz | Busca valor de cabeçalho sem distinguir maiúsculas. |
| Como faz | Converte nome para minúsculas e usa get com string vazia para ausência. |
| Erros/conexão | Sem I/O; não altera conexão. |
| Quem chama | RequestReader e ConnectionHandler.i_keep_alive. |
| Por quê | O parser armazena todos os nomes em minúsculas, preservando os valores. |
| Quem chama internamente | `self_a.headers_a.get`, `name_a.lower` |

#### HttpParseError

Exception com status_a e head_only_a. A mensagem fica em Exception.args; só texto fixo vai à resposta HTML.

##### `HttpParseError.i_init`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpParseError.i_init(self_a, status_a: int, message_a: str) -> None` |
| O que faz | Cria exceção de parsing com código HTTP e mensagem. |
| Como faz | Inicializa Exception, guarda status_a e inicia head_only_a como falso; o parser pode marcá-lo para HEAD. |
| Erros/conexão | É levantada por RequestReader e tratada por ConnectionHandler.i_run. |
| Quem chama | Pontos de validação do parser, por HttpParseError(...). |
| Por quê | Transporta informação suficiente para gerar erro seguro sem expor a entrada na página HTML. |
| Quem chama internamente | `super().__init__`, `super` |

#### IdleTimeout

Subclasse de Exception sem métodos próprios. Distingue timeout de leitura e provoca fechamento silencioso.

#### ConnectionClosedByPeer

Subclasse de Exception sem métodos próprios. Representa EOF de recv; provocará fechamento silencioso.

#### RequestReader

Mantém sock_a, max_header_bytes_a e buffer_a. Não fecha o socket; isso pertence ao ConnectionHandler.

##### `RequestReader.i_init`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader.i_init(self_a, sock_a: socket_a.socket, max_header_bytes_a: int=16384) -> None` |
| O que faz | Prepara leitor e buffer vazio. |
| Como faz | Guarda socket e limite de cabeçalho fornecido; não consome bytes. |
| Erros/conexão | Sem I/O; o dono do socket é ConnectionHandler. |
| Quem chama | ConnectionHandler.i_init. |
| Por quê | O buffer precisa existir por toda a conexão, não por recv. |
| Quem chama internamente |  |

##### `RequestReader.i_read_request`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader.i_read_request(self_a) -> HttpRequest` |
| O que faz | Lê exatamente uma requisição completa. |
| Como faz | Procura CRLF CRLF; aplica limite à mensagem; preserva HEAD em rejeição; separa e retém excedente; interpreta head; consome Content-Length; retorna HttpRequest. |
| Erros/conexão | HttpParseError→resposta/close; IdleTimeout/ConnectionClosedByPeer→close silencioso; OSError→close. |
| Quem chama | ConnectionHandler.i_run. |
| Por quê | Preservar o excedente resolve fragmentação, pipeline e corpo seguido de outra mensagem. |
| Quem chama internamente | `self_a.buffer_a.find`, `self_a.i_recv_more`, `HttpParseError`, `self_a.buffer_a.startswith`, `self_a.i_parse_head`, `self_a.i_read_body`, `int`, `len`, `request_a.i_header` |

##### `RequestReader.i_read_body`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader.i_read_body(self_a, n_a: int) -> bytes` |
| O que faz | Retira n bytes do corpo e guarda o resto. |
| Como faz | Valida 0≤n≤1 MiB; recebe até ter n bytes; devolve prefixo e mantém excedente. |
| Erros/conexão | Limite inválido gera 400; timeout/EOF propaga e termina a conexão sem resposta adicional. |
| Quem chama | RequestReader.i_read_request. |
| Por quê | Mesmo um método não suportado pode ter corpo; consumi-lo evita dessincronização. |
| Quem chama internamente | `HttpParseError`, `len`, `self_a.i_recv_more` |

##### `RequestReader.i_recv_more`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader.i_recv_more(self_a) -> None` |
| O que faz | Acrescenta ao buffer os próximos bytes de TCP. |
| Como faz | recv(4096); converte timeout; EOF vira exceção específica; soma dados ao buffer. |
| Erros/conexão | socket.timeout→IdleTimeout; recv vazio→ConnectionClosedByPeer; outros OSError propagam. |
| Quem chama | i_read_request e i_read_body. |
| Por quê | Centraliza diferenças entre silêncio, EOF e novos dados. |
| Quem chama internamente | `self_a.sock_a.recv`, `ConnectionClosedByPeer`, `IdleTimeout` |

##### `RequestReader.i_parse_head`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader.i_parse_head(self_a, data_a: bytes) -> HttpRequest` |
| O que faz | Interpreta linha inicial, campos e regras de framing. |
| Como faz | Decodifica ISO-8859-1 para correspondência byte-a-byte; separa CRLF; valida Host, Transfer-Encoding, Content-Length e Expect; separa query; monta HttpRequest. |
| Erros/conexão | 400 para framing/Host inválido, 417 para Expect; marca HEAD antes de propagar HttpParseError. Corpo é consumido depois. |
| Quem chama | RequestReader.i_read_request. |
| Por quê | Validação anterior à leitura do corpo evita ambiguidades e espera por 100-continue não implementado. |
| Quem chama internamente | `data_a.decode('iso-8859-1').split`, `self_a.i_parse_request_line`, `self_a.i_parse_headers`, `headers_a.get`, `target_a.partition`, `HttpRequest`, `data_a.decode`, `HttpParseError`, `int`, `lines_a[0].startswith`, `re_a.fullmatch`, `len` |

##### `RequestReader.i_parse_request_line`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader.i_parse_request_line(self_a, line_a: str) -> tuple` |
| O que faz | Extrai método, target e versão de uma linha. |
| Como faz | Exige três campos separados por espaço; método token; target ASCII sem controles/fragmento; versão HTTP/d.d; major 1; GET/HEAD com caminho iniciado por /. |
| Erros/conexão | 400 para sintaxe; 505 para major incompatível; todos fecham a conexão no handler. |
| Quem chama | RequestReader.i_parse_head. |
| Por quê | Parser estrito delimita o subconjunto de origem do laboratório, sem fingir suporte a proxy. |
| Quem chama internamente | `line_a.split`, `HttpParseError`, `TOKEN_a.fullmatch`, `any`, `re_a.fullmatch`, `len`, `all`, `target_a.startswith`, `ord` |

##### `RequestReader.i_parse_headers`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader.i_parse_headers(self_a, lines_a: list) -> dict` |
| O que faz | Produz dicionário de cabeçalhos normalizados. |
| Como faz | Exige dois-pontos, nome token sem espaço antes de :, valor sem controles; remove OWS; rejeita Host/Content-Length/Transfer-Encoding repetidos; combina outros campos por vírgula. |
| Erros/conexão | HttpParseError 400 fecha a conexão. Host vazio ou com separadores proibidos também é rejeitado. |
| Quem chama | RequestReader.i_parse_head. |
| Por quê | Framing único evita interpretações contraditórias de uma mesma sequência de bytes. |
| Quem chama internamente | `line_a.split`, `name_a.lower`, `value_a.strip`, `any`, `HttpParseError`, `TOKEN_a.fullmatch`, `ord` |

### http_response.py

##### `i_format_http_date`

| Campo | Descrição |
|---|---|
| Assinatura | `i_format_http_date() -> str` |
| O que faz | Produz a data HTTP do instante atual em GMT. |
| Como faz | datetime UTC e format_datetime(usegmt=True). |
| Erros/conexão | Sem I/O de rede; função não altera conexão. |
| Quem chama | RequestHandler.i_handle e ConnectionHandler.i_run. |
| Por quê | email.utils não depende do locale para nomes de dias e meses. |
| Quem chama internamente | `i_format_datetime`, `i_datetime.now` |

##### `i_guess_content_type`

| Campo | Descrição |
|---|---|
| Assinatura | `i_guess_content_type(path_a: str) -> str` |
| O que faz | Escolhe MIME pela extensão, ignorando caixa. |
| Como faz | splitext, lower e tabela de 12 extensões; fallback application/octet-stream. |
| Erros/conexão | Não abre arquivo nem altera conexão. |
| Quem chama | RequestHandler.i_handle e teste de MIME. |
| Por quê | Tabela própria produz resultados previsíveis entre sistemas operacionais. |
| Quem chama internamente | `MIME_TYPES_a.get`, `os_a.path.splitext(path_a)[1].lower`, `os_a.path.splitext` |

#### HttpResponse

Dataclass: status_a: int, headers_a: dict={}, body_a: bytes=b'', head_only_a: bool=False, file_a: Optional[BinaryIO]=None. Cada dicionário default é independente. O stream aberto é liberado em i_close.

##### `HttpResponse.i_to_head_bytes`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpResponse.i_to_head_bytes(self_a) -> bytes` |
| O que faz | Serializa status e headers em bytes HTTP. |
| Como faz | Consulta razão padronizada, gera linhas Name: Value, junta com CRLF e termina com linha vazia. |
| Erros/conexão | KeyError para status interno não registrado ou erro de encoding em uso indevido; entradas reais usam valores controlados/ASCII. |
| Quem chama | ConnectionHandler.i_send. |
| Por quê | HTTP é gerado manualmente; não usa biblioteca pronta de servidor. |
| Quem chama internamente | `lines_a.extend`, `('\r\n'.join(lines_a) + '\r\n\r\n').encode`, `self_a.headers_a.items`, `'\r\n'.join` |

##### `HttpResponse.i_body_bytes`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpResponse.i_body_bytes(self_a) -> Iterator[bytes]` |
| O que faz | Gera corpo em memória ou blocos do arquivo. |
| Como faz | HEAD termina sem yield; erro produz body_a; arquivo lê no máximo 65536 bytes por bloco até o Content-Length anunciado. |
| Erros/conexão | OSError se arquivo truncar; i_send libera descritor e i_run fecha socket. |
| Quem chama | ConnectionHandler.i_send. |
| Por quê | Memória limitada e nenhum byte além do tamanho anunciado caso o arquivo cresça. |
| Quem chama internamente | `int`, `self_a.file_a.read`, `len`, `min`, `OSError` |

##### `HttpResponse.i_close`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpResponse.i_close(self_a) -> None` |
| O que faz | Fecha o arquivo associado, se houver. |
| Como faz | Chama close do BinaryIO; resposta HTML sem arquivo não exige ação. |
| Erros/conexão | Falha de I/O pode propagar ao handler; socket será encerrado. |
| Quem chama | Finally de ConnectionHandler.i_send. |
| Por quê | Uma única dona do descritor evita vazamento de recursos. |
| Quem chama internamente | `self_a.file_a.close` |

##### `HttpResponse.i_error`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpResponse.i_error(cls_a, status_a: int, extra_headers_a: Optional[dict]=None) -> 'HttpResponse'` |
| O que faz | Constrói resposta de erro com HTML curto em português. |
| Como faz | Consulta textos fixos, codifica UTF-8, calcula len dos bytes, define Content-Length/Type e une extra_headers como Allow. |
| Erros/conexão | Status deve existir nas tabelas; política de fechamento é decidida em ConnectionHandler. |
| Quem chama | RequestHandler.i_handle e ConnectionHandler.i_run. |
| Por quê | Tamanho calculado após encode é correto também com caracteres acentuados. |
| Quem chama internamente | `f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>{status_a} {REASONS_a[status_a]}</title><h1>{status_a}</h1><p>{MESSAGES_a[status_a]}</p></html>\n'.encode`, `headers_a.update`, `cls_a`, `str`, `len` |

### file_resolver.py

#### ForbiddenError

Exception sem métodos próprios; sinaliza contenção/caminho proibido e vira 403 no handler.

#### NotFoundError

Exception sem métodos próprios; sinaliza ausência de arquivo regular e vira 404.

#### FileResolver

Guarda root_a canonicalizado. URL não controla a raiz; resolução retorna caminho absoluto seguro para raiz estável.

##### `FileResolver.i_init`

| Campo | Descrição |
|---|---|
| Assinatura | `FileResolver.i_init(self_a, root_a: str) -> None` |
| O que faz | Canonicaliza e valida o diretório raiz. |
| Como faz | realpath e isdir; armazena root_a absoluto. |
| Erros/conexão | ValueError se a raiz não existe; servidor não inicia. |
| Quem chama | HttpServer.i_init, por FileResolver(...). |
| Por quê | Todas as verificações usam a mesma raiz real. |
| Quem chama internamente | `os_a.path.realpath`, `os_a.path.isdir`, `ValueError` |

##### `FileResolver.i_inside_root`

| Campo | Descrição |
|---|---|
| Assinatura | `FileResolver.i_inside_root(self_a, path_a: str) -> str` |
| O que faz | Canonicaliza destino e comprova contenção na raiz. |
| Como faz | realpath seguido de commonpath; ValueError de drives incompatíveis é tratado como fora da raiz. |
| Erros/conexão | ForbiddenError se fora; handler converte para 403 sem necessariamente fechar. |
| Quem chama | FileResolver.i_resolve, inclusive para index.html. |
| Por quê | Comparação por componentes evita www-secret e resolve symlinks. |
| Quem chama internamente | `os_a.path.realpath`, `ForbiddenError`, `os_a.path.commonpath` |

##### `FileResolver.i_resolve`

| Campo | Descrição |
|---|---|
| Assinatura | `FileResolver.i_resolve(self_a, raw_path_a: str) -> str` |
| O que faz | Resolve URL para arquivo regular seguro. |
| Como faz | Verifica %XX; unquote UTF-8 estrito; rejeita NUL, barra invertida e :; junta raiz; verifica contenção; acrescenta index se diretório e valida novamente; exige isfile. |
| Erros/conexão | ForbiddenError para caminho proibido; NotFoundError se ausente/não regular; OSError tratado pelo handler. |
| Quem chama | RequestHandler.i_handle. |
| Por quê | Decodificar antes de validar captura traversal codificado; índice e symlinks não escapam da raiz estável. |
| Quem chama internamente | `re_a.search`, `self_a.i_inside_root`, `os_a.path.isdir`, `ForbiddenError`, `i_unquote`, `any`, `os_a.path.join`, `os_a.path.isfile`, `NotFoundError`, `path_a.startswith`, `path_a.lstrip` |

### request_handler.py

#### RequestHandler

Guarda resolver_a e server_name_a. Não retém request/resposta entre chamadas.

##### `RequestHandler.i_init`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestHandler.i_init(self_a, resolver_a: FileResolver, server_name_a: str) -> None` |
| O que faz | Guarda resolver e identificador do servidor. |
| Como faz | Somente configuração compartilhada para leitura. |
| Erros/conexão | Nenhum I/O de rede; criação pelo servidor. |
| Quem chama | HttpServer.i_init, por RequestHandler(...). |
| Por quê | Handler é compartilhável porque não guarda estado de um pedido. |
| Quem chama internamente |  |

##### `RequestHandler.i_handle`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestHandler.i_handle(self_a, request_a: HttpRequest) -> HttpResponse` |
| O que faz | Transforma pedido em resposta pronta para envio. |
| Como faz | Outros métodos→405/Allow; GET/HEAD→resolve, open binário, fstat e MIME; arquivo passa à resposta; traduz erros; define flag HEAD e headers comuns. |
| Erros/conexão | Forbidden/Permission→403; ausência/não regular→404; outro OSError→500; arquivo não transferido é fechado em finally. |
| Quem chama | ConnectionHandler.i_run. |
| Por quê | GET e HEAD seguem o mesmo cálculo de headers, diferindo apenas na produção de corpo. |
| Quem chama internamente | `response_a.headers_a.update`, `HttpResponse.i_error`, `self_a.resolver_a.i_resolve`, `open`, `os_a.fstat`, `HttpResponse`, `i_format_http_date`, `file_a.fileno`, `stat_a.S_ISREG`, `NotFoundError`, `file_a.close`, `str`, `i_guess_content_type` |

### tests/client.py

#### RawClient

Cliente de teste com sock_a e buffer_a; fornece context manager via aliases nativos e interpreta respostas à mão.

##### `RawClient.i_init`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.i_init(self_a, host_a: str, port_a: int, timeout_a: float=4.0) -> None` |
| O que faz | Abre conexão TCP de teste e buffer vazio. |
| Como faz | create_connection com timeout configurável. |
| Erros/conexão | OSError se servidor indisponível; falha no teste. |
| Quem chama | Testes e i_exchange, por RawClient(...). |
| Por quê | Cliente independente não compartilha parser HTTP com servidor. |
| Quem chama internamente | `socket_a.create_connection` |

##### `RawClient.i_send`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.i_send(self_a, data_a: bytes) -> None` |
| O que faz | Envia bytes fornecidos integralmente. |
| Como faz | sendall no socket. |
| Erros/conexão | OSError falha no teste; with garante fechamento. |
| Quem chama | Testes de conformidade/stream/concorrência. |
| Por quê | Permite criar pedidos malformados que bibliotecas HTTP recusariam. |
| Quem chama internamente | `self_a.sock_a.sendall` |

##### `RawClient.i_read_response`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.i_read_response(self_a, head_only_a: bool=False) -> tuple` |
| O que faz | Lê uma resposta por Content-Length e preserva excedente. |
| Como faz | Acumula head, valida versão e headers únicos; para HEAD lê zero bytes; devolve status, headers e corpo. |
| Erros/conexão | AssertionError em EOF/versão/duplicação; ValueError em formato; OSError de rede. |
| Quem chama | Scripts de teste. |
| Por quê | Leitor separado revela erros de framing no servidor. |
| Quem chama internamente | `self_a.buffer_a.split`, `head_a.decode('iso-8859-1').split`, `lines_a[0].split`, `self_a.i_receive`, `AssertionError`, `line_a.split`, `value_a.strip`, `int`, `len`, `head_a.decode`, `name_a.lower` |

##### `RawClient.i_receive`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.i_receive(self_a) -> None` |
| O que faz | Recebe e acumula bytes da resposta. |
| Como faz | recv(65536); EOF prematuro falha. |
| Erros/conexão | AssertionError em EOF ou OSError de rede. |
| Quem chama | RawClient.i_read_response. |
| Por quê | Centraliza verificação de truncamento. |
| Quem chama internamente | `self_a.sock_a.recv`, `AssertionError` |

##### `RawClient.i_close`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.i_close(self_a) -> None` |
| O que faz | Libera socket do teste. |
| Como faz | close no socket. |
| Erros/conexão | OSError eventual de recurso. |
| Quem chama | i_exit e chamadores diretos. |
| Por quê | Evita conexões sobrando ao fim dos testes. |
| Quem chama internamente | `self_a.sock_a.close` |

##### `RawClient.i_enter`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.i_enter(self_a) -> 'RawClient'` |
| O que faz | Entrega o cliente ao bloco with. |
| Como faz | Retorna self_a. |
| Erros/conexão | Não altera rede. |
| Quem chama | Protocolo __enter__ do Python. |
| Por quê | Permite cleanup automático. |
| Quem chama internamente |  |

##### `RawClient.i_exit`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.i_exit(self_a, *args_a) -> None` |
| O que faz | Fecha o cliente ao sair de with. |
| Como faz | Chama i_close; não suprime exceções. |
| Erros/conexão | Falha original do teste permanece visível. |
| Quem chama | Protocolo __exit__ do Python. |
| Por quê | Libera recursos mesmo quando uma asserção falha. |
| Quem chama internamente | `self_a.i_close` |

##### `i_request`

| Campo | Descrição |
|---|---|
| Assinatura | `i_request(path_a: str='/test.txt', method_a: str='GET', connection_a: str='keep-alive', version_a: str='HTTP/1.1') -> bytes` |
| O que faz | Monta pedido HTTP de teste em bytes ASCII. |
| Como faz | Interpola método/caminho/versão e Host/Connection com CRLF. |
| Erros/conexão | UnicodeEncodeError se uso fora do subconjunto ASCII de teste. |
| Quem chama | Testes e cliente de concorrência. |
| Por quê | Mantém fixtures fáceis de ler e modificar. |
| Quem chama internamente | `f'{method_a} {path_a} {version_a}\r\nHost: laboratorio\r\nConnection: {connection_a}\r\n\r\n'.encode` |

##### `i_exchange`

| Campo | Descrição |
|---|---|
| Assinatura | `i_exchange(data_a: bytes, head_only_a: bool=False) -> tuple` |
| O que faz | Executa um único pedido e lê sua resposta. |
| Como faz | Abre RawClient em with, envia bytes e lê com opção HEAD. |
| Erros/conexão | Propaga falhas de rede/framing para unittest. |
| Quem chama | HttpTests. |
| Por quê | Reduz repetição sem reutilizar implementação do servidor. |
| Quem chama internamente | `RawClient`, `client_a.i_send`, `client_a.i_read_response` |

##### `i_run_suite`

| Campo | Descrição |
|---|---|
| Assinatura | `i_run_suite(suite_a: unittest_a.TestSuite) -> bool` |
| O que faz | Executa TestSuite e imprime PASS/FAIL. |
| Como faz | TextTestRunner verbosity 2; consulta resultado; devolve bool. |
| Erros/conexão | Falhas/erros ficam no resultado, não são escondidos. |
| Quem chama | i_remote_main e run_all.py. |
| Por quê | Exit code final pode indicar sucesso real a scripts. |
| Quem chama internamente | `unittest_a.TextTestRunner(verbosity=2).run`, `print`, `result_a.wasSuccessful`, `unittest_a.TextTestRunner`, `len` |

##### `i_remote_main`

| Campo | Descrição |
|---|---|
| Assinatura | `i_remote_main(case_a: type) -> None` |
| O que faz | Lê host/porta e executa a classe de testes remotos. |
| Como faz | Atualiza HOST_a/PORT_a; loader usa prefixo i_test_; carrega e executa classe. |
| Erros/conexão | SystemExit 0 se passou, 1 se falhou; argparse 2 se uso inválido. |
| Quem chama | Blocos principais de test_http.py e test_stream.py. |
| Por quê | Permite mesmo teste contra máquina local ou remota. |
| Quem chama internamente | `argparse_a.ArgumentParser`, `parser_a.add_argument`, `parser_a.parse_args`, `SystemExit`, `i_run_suite`, `unittest_a.defaultTestLoader.loadTestsFromTestCase` |

### tests/test_http.py

#### HttpTests

TestCase de conformidade remota; utiliza www entregue e os helpers independentes de client.py.

##### `HttpTests.i_test_get_and_required_headers`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.i_test_get_and_required_headers(self_a) -> None` |
| O que faz | Confere GET 200, corpo literal, tamanho em bytes, MIME, Date, Server e close. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `i_exchange`, `self_a.assertEqual`, `self_a.assertTrue`, `self_a.assertRegex`, `i_request`, `'Arquivo de teste do Trabalho 1.\n'.encode`, `int`, `len` |

##### `HttpTests.i_test_head_same_headers_and_no_body`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.i_test_head_same_headers_and_no_body(self_a) -> None` |
| O que faz | Compara GET e HEAD em 200/403/404; ignora apenas Date; confirma EOF sem corpo. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self_a.subTest`, `i_exchange`, `i_request`, `RawClient`, `connection_a.i_send`, `connection_a.i_read_response`, `self_a.assertEqual`, `get_headers_a.pop`, `headers_a.pop`, `connection_a.sock_a.recv`, `int`, `len` |

##### `HttpTests.i_test_bad_requests_close`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.i_test_bad_requests_close(self_a) -> None` |
| O que faz | Envia request line/header/Host/framing inválidos e headers excessivos; espera 400 e EOF. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self_a.subTest`, `RawClient`, `connection_a.i_send`, `connection_a.i_read_response`, `self_a.assertEqual`, `int`, `len`, `connection_a.sock_a.recv` |

##### `HttpTests.i_test_traversal_vectors`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.i_test_traversal_vectors(self_a) -> None` |
| O que faz | Verifica oito vetores, incluindo os cinco exigidos, NUL, drive e prefixo www-secret; espera 403. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self_a.subTest`, `self_a.assertEqual`, `i_exchange`, `i_request` |

##### `HttpTests.i_test_not_found_and_directory_index`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.i_test_not_found_and_directory_index(self_a) -> None` |
| O que faz | Confere 404 ausente e subdiretório sem index, 200 na raiz com index e na página explícita. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self_a.assertEqual`, `i_exchange`, `i_request` |

##### `HttpTests.i_test_method_not_allowed`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.i_test_method_not_allowed(self_a) -> None` |
| O que faz | Confere DELETE→405 e Allow GET, HEAD. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `i_exchange`, `self_a.assertEqual`, `i_request` |

##### `HttpTests.i_test_query_percent_encoding_and_header_case`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.i_test_query_percent_encoding_and_header_case(self_a) -> None` |
| O que faz | Confere percent-decoding, query ignorada, header sem espaço e nomes de headers com caixa mista. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self_a.assertEqual`, `i_exchange` |

##### `HttpTests.i_test_http_10_and_close_token`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.i_test_http_10_and_close_token(self_a) -> None` |
| O que faz | Confere fechamento HTTP/1.0 padrão, keep-alive explícito e prioridade de CLOSE em lista. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self_a.assertEqual`, `i_request`, `i_exchange` |

##### `HttpTests.i_test_binary_mime_and_version`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.i_test_binary_mime_and_version(self_a) -> None` |
| O que faz | Confere MIME de SVG e 505 para HTTP/2.0 textual; não negocia HTTP/2. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `i_exchange`, `self_a.assertEqual`, `i_request` |

##### `HttpTests.i_test_expect_rejected_without_waiting_for_body`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.i_test_expect_rejected_without_waiting_for_body(self_a) -> None` |
| O que faz | Envia Expect com Content-Length mas sem corpo; espera 417 imediato. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self_a.assertEqual`, `i_exchange` |

### tests/test_stream.py

#### StreamTests

TestCase de fragmentação, pipeline, corpo e sequência persistente.

##### `StreamTests.i_test_fragmented_byte_by_byte`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.i_test_fragmented_byte_by_byte(self_a) -> None` |
| O que faz | Escreve um byte por vez com pequeno intervalo e recebe 200 ao completar. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `RawClient`, `i_request`, `self_a.assertEqual`, `connection_a.i_send`, `time_a.sleep`, `bytes`, `connection_a.i_read_response` |

##### `StreamTests.i_test_three_pipelined_requests`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.i_test_three_pipelined_requests(self_a) -> None` |
| O que faz | Envia três pedidos em uma send; confirma três status na ordem 200,404,200 e EOF. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `RawClient`, `self_a.assertEqual`, `i_request`, `connection_a.sock_a.send`, `len`, `connection_a.sock_a.recv`, `connection_a.i_read_response`, `range` |

##### `StreamTests.i_test_complete_plus_half_next_request`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.i_test_complete_plus_half_next_request(self_a) -> None` |
| O que faz | Envia pedido completo e metade do seguinte; lê primeiro, completa segundo e verifica 200. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `i_request`, `len`, `RawClient`, `connection_a.i_send`, `self_a.assertEqual`, `connection_a.i_read_response` |

##### `StreamTests.i_test_body_consumed_before_next_request`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.i_test_body_consumed_before_next_request(self_a) -> None` |
| O que faz | POST com cinco bytes seguido de GET produz 405 e 200 sem perder fronteira. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `RawClient`, `connection_a.i_send`, `self_a.assertEqual`, `i_request`, `connection_a.i_read_response` |

##### `StreamTests.i_test_head_then_get`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.i_test_head_then_get(self_a) -> None` |
| O que faz | Pipeline HEAD/GET confirma que HEAD não injeta corpo na próxima resposta. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `RawClient`, `connection_a.i_send`, `self_a.assertEqual`, `i_request`, `connection_a.i_read_response` |

##### `StreamTests.i_test_sequential_persistent_connection`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.i_test_sequential_persistent_connection(self_a) -> None` |
| O que faz | Dez pedidos sequenciais no mesmo socket retornam 200 e keep-alive. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `RawClient`, `range`, `connection_a.i_send`, `self_a.assertEqual`, `i_request`, `connection_a.i_read_response` |

### tests/concurrency_test.py

##### `i_fetch`

| Campo | Descrição |
|---|---|
| Assinatura | `i_fetch(host_a: str, port_a: int) -> int` |
| O que faz | Faz um GET concorrente e devolve bytes do corpo. |
| Como faz | Abre cliente, envia Connection close, exige 200 e retorna len. |
| Erros/conexão | AssertionError se não 200; OSError em falha de rede. |
| Quem chama | Workers do ThreadPoolExecutor em i_run. |
| Por quê | Cada cliente tem conexão real independente. |
| Quem chama internamente | `RawClient`, `connection_a.i_send`, `connection_a.i_read_response`, `len`, `i_request`, `AssertionError` |

##### `i_run`

| Campo | Descrição |
|---|---|
| Assinatura | `i_run(host_a: str, port_a: int, clients_a: int=10) -> None` |
| O que faz | Prova atendimento enquanto outro pedido está incompleto. |
| Como faz | Envia metade de header; executa N clientes paralelos; só depois completa lento e exige 200; imprime tempo/bytes. |
| Erros/conexão | Asserção ou erro de rede interrompe; with fecha os sockets. |
| Quem chama | i_main e teste local de concorrência. |
| Por quê | Confirma sobreposição sem depender somente de logs ou sleeps longos. |
| Quem chama internamente | `time_a.perf_counter`, `print`, `RawClient`, `slow_a.i_send`, `ThreadPoolExecutor`, `list`, `AssertionError`, `pool_a.map`, `slow_a.i_read_response`, `sum`, `range`, `i_fetch` |

##### `i_main`

| Campo | Descrição |
|---|---|
| Assinatura | `i_main() -> None` |
| O que faz | Configura teste concorrente pela CLI. |
| Como faz | Lê host/porta/--clients, exige clients positivo e executa i_run. |
| Erros/conexão | Argparse 2 para parâmetros; erro/asserção produz FAIL e saída 1. |
| Quem chama | Bloco principal do script. |
| Por quê | Teste repetível com carga escolhida pelo grupo. |
| Quem chama internamente | `argparse_a.ArgumentParser`, `parser_a.add_argument`, `parser_a.parse_args`, `parser_a.error`, `i_run`, `parser_a.exit` |

### tests/benchmark.py

##### `i_read_response`

| Campo | Descrição |
|---|---|
| Assinatura | `i_read_response(sock_a: socket_a.socket, buffer_a: bytes) -> tuple` |
| O que faz | Consome uma resposta 200 e devolve buffer residual/tamanho do corpo. |
| Como faz | Delimita head, valida status e Content-Length, rejeita Transfer-Encoding; descarta corpo em blocos. |
| Erros/conexão | ValueError em EOF, tamanho inválido ou resposta incompatível; OSError de rede. |
| Quem chama | benchmark.i_run. |
| Por quê | A medição deve esperar o corpo inteiro sem guardar arquivo grande. |
| Quem chama internamente | `buffer_a.split`, `head_a.decode('iso-8859-1').split`, `dict`, `int`, `sock_a.recv`, `ValueError`, `min`, `len`, `head_a.decode`, `lines_a[0].split`, `name_a.lower`, `value_a.strip`, `line_a.split` |

##### `i_run`

| Campo | Descrição |
|---|---|
| Assinatura | `i_run(host_a: str, port_a: int, path_a: str='/test.txt', requests_a: int=10, mode_a: str='c1') -> dict` |
| O que faz | Executa N pedidos sequenciais no modo escolhido. |
| Como faz | C1 abre/fecha por pedido; C2 mantém socket e fecha no último; lê cada corpo antes do próximo; mede perf_counter e devolve métricas. |
| Erros/conexão | Erros propagam após close no finally; pressupõe argumentos validados por i_main. |
| Quem chama | benchmark.i_main e suíte integrada. |
| Por quê | Isola a diferença de número de conexões mantendo caminho e quantidade. |
| Quem chama internamente | `time_a.perf_counter`, `print`, `range`, `f'GET {path_a} HTTP/1.1\r\nHost: {host_a}:{port_a}\r\nConnection: {connection_a}\r\n\r\n'.encode`, `sock_a.sendall`, `i_read_response`, `sock_a.close`, `socket_a.create_connection`, `mode_a.upper`, `sock_a.recv`, `ValueError` |

##### `i_main`

| Campo | Descrição |
|---|---|
| Assinatura | `i_main() -> None` |
| O que faz | Lê CLI do benchmark e valida parâmetros. |
| Como faz | Exige host/porta/mode, requests positivo e path ASCII seguro; executa i_run. |
| Erros/conexão | Argparse 2 no uso inválido; ValueError/OSError gera saída 1. |
| Quem chama | Bloco principal do benchmark. |
| Por quê | Evita medir silenciosamente respostas de erro ou caminho incorreto. |
| Quem chama internamente | `argparse_a.ArgumentParser`, `parser_a.add_argument`, `parser_a.parse_args`, `parser_a.error`, `any`, `i_run`, `args_a.path.startswith`, `parser_a.exit`, `ord` |

### tests/run_all.py

O bloco principal cria diretório temporário, copia www, adiciona large.bin, inicia HttpServer em thread com bind 0.0.0.0/porta 0 e timeout 0,7 s. Aguarda inicialização, executa HttpTests/StreamTests/LocalTests e, no finally, encerra servidor e aguarda thread. Verifica que nenhum worker sobrou e retorna exit code 0/1. Não é uma função separada.

#### LocalTests

TestCase adicional com fixtures criadas por run_all.py; executado junto dos testes remotos contra servidor temporário.

##### `LocalTests.i_test_symlinks_and_prefix`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.i_test_symlinks_and_prefix(self_a) -> None` |
| O que faz | Cria root e diretório irmão temporários; verifica symlink externo de pasta/index e prefixo semelhante. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `tempfile_a.TemporaryDirectory`, `root_a.mkdir`, `outside_a.mkdir`, `(outside_a / 'secret.txt').write_text`, `FileResolver`, `Path`, `(root_a / 'link').symlink_to`, `(root_a / 'index.html').symlink_to`, `str`, `self_a.skipTest`, `self_a.subTest`, `self_a.assertRaises`, `resolver_a.i_resolve` |

##### `LocalTests.i_test_idle_and_incomplete_timeout`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.i_test_idle_and_incomplete_timeout(self_a) -> None` |
| O que faz | Testa silêncio, cabeçalho parcial e corpo parcial; espera EOF pelo timeout de 0,7 s. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `client_a.RawClient`, `conn_a.i_send`, `self_a.assertEqual`, `conn_a.sock_a.recv` |

##### `LocalTests.i_test_large_file`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.i_test_large_file(self_a) -> None` |
| O que faz | Compara todos os bytes de binário de 2 MiB e MIME genérico após streaming. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `bytes`, `client_a.RawClient`, `conn_a.i_send`, `conn_a.i_read_response`, `self_a.assertEqual`, `range`, `client_a.i_request` |

##### `LocalTests.i_test_all_mime_types`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.i_test_all_mime_types(self_a) -> None` |
| O que faz | Verifica as 12 extensões da tabela pelo MIME esperado. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self_a.assertTrue`, `i_guess_content_type('x.' + ext_a).startswith`, `i_guess_content_type` |

##### `LocalTests.i_test_head_malformed_no_body`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.i_test_head_malformed_no_body(self_a) -> None` |
| O que faz | HEAD com header sem dois-pontos produz 400, sem corpo e com EOF. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `client_a.RawClient`, `conn_a.i_send`, `self_a.assertEqual`, `conn_a.sock_a.recv`, `conn_a.i_read_response` |

##### `LocalTests.i_test_head_oversized_no_body`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.i_test_head_oversized_no_body(self_a) -> None` |
| O que faz | HEAD com header acima de 16 KiB retorna 400 e tamanho hipotético positivo, mas nenhum byte de corpo. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `client_a.RawClient`, `conn_a.i_send`, `conn_a.i_read_response`, `self_a.assertEqual`, `self_a.assertGreater`, `int`, `conn_a.sock_a.recv` |

##### `LocalTests.i_test_concurrent_slow_client`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.i_test_concurrent_slow_client(self_a) -> None` |
| O que faz | Executa 12 clientes enquanto outro está incompleto e depois conclui o lento. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `i_concurrency` |

##### `LocalTests.i_test_benchmarks`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.i_test_benchmarks(self_a) -> None` |
| O que faz | Executa C1 e C2 com dez pedidos; compara conexões 10/1 e bytes HTTP iguais. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via i_run_suite; loader configurado com prefixo i_test_. |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `i_benchmark`, `self_a.assertEqual` |

**Inventário:** 72 funções/métodos escritos no projeto descritos acima; nenhum omitido. As ligações nativas e os construtores gerados por dataclass estão descritos junto às respectivas classes.


## 5. Tabela de comportamento

| Situação | Resposta | Conexão |
|---|---|---|
| GET de arquivo regular existente | 200, headers e corpo | Persiste em HTTP/1.1, salvo close |
| HEAD válido ou erro identificável como HEAD | Mesmo status/headers do GET, sem corpo | Segue mesma política; Content-Length do corpo hipotético |
| Request line inválida ou versão malformada | 400 | Fecha |
| Header sem `:` ou nome inválido | 400 | Fecha |
| HTTP/1.1 sem Host ou Host duplicado | 400 | Fecha |
| Cabeçalhos acima de 16 KiB | 400 | Fecha; HEAD reconhecido não recebe corpo |
| Content-Length inválido/repetido ou corpo >1 MiB | 400 | Fecha |
| Transfer-Encoding presente | 400 | Fecha; chunked não implementado |
| Expect presente | 417 | Fecha, sem esperar o corpo |
| Versão principal diferente de 1 | 505 | Fecha |
| Traversal, symlink externo, NUL ou barra invertida | 403 | Pode persistir: framing já conhecido |
| Arquivo ausente/diretório sem index | 404 | Pode persistir |
| Outro método sintaticamente válido | 405, Allow: GET, HEAD | Pode persistir após consumir o corpo |
| Connection contém token close | Connection: close | Fecha após enviar resposta |
| HTTP/1.0 sem keep-alive | Resposta HTTP/1.1, Connection: close | Fecha |
| HTTP/1.0 com keep-alive | Connection: keep-alive | Persiste |
| Timeout entre pedidos ou durante pedido incompleto | Nenhuma nova resposta | Fecha silenciosamente |
| Cliente encerra envio antes de completar pedido | Nenhuma nova resposta | Fecha |
| Erro de leitura/envio após iniciar resposta | Não tenta enviar segunda resposta | Fecha; cliente detecta truncamento |

Erros de parsing têm precedência sobre a escolha do método: por exemplo, POST sem Host
retorna 400. `Date` representa o instante de cada resposta, então GET e HEAD feitos em
segundos diferentes podem ter datas diferentes; os testes comparam os demais cabeçalhos.

## 6. Fluxo de bytes e buffer

**Fragmentada:** primeiro recv traz `GET /te`, o segundo `st.txt HTTP/1.1\r\nHost: x\r\n`,
o terceiro `\r\n`. Apenas no terceiro existe CRLF CRLF e o parser tem o cabeçalho completo.

**Várias juntas:** um recv traz `[GET A completo][GET B completo][GET C completo]`.
`i_read_request` retira somente A; depois retira B e C nas próximas voltas do loop.
As respostas são serializadas na ordem dos pedidos da mesma conexão.

**Inteira mais parte da próxima:** um recv traz `[A completo][GET /B HT]`.
O parser entrega A e guarda `GET /B HT`. Depois junta novos bytes até completar B.

```python
end_a = self_a.buffer_a.find(b'\r\n\r\n')
(head_a, self_a.buffer_a) = (
    self_a.buffer_a[:end_a], self_a.buffer_a[end_a + 4:]
)
```

Com Content-Length, `i_read_body(n_a)` tira exatamente n bytes antes de devolver a
requisição. Por exemplo, POST com cinco bytes seguido de GET não confunde `abcde`
com uma nova request line. O servidor responde 405 ao POST e pode processar o GET.
O limite de headers se aplica à mensagem atual, não à soma de pedidos completos no buffer.
`recv(4096)` não garante receber 4096 bytes, e `sendall` não garante uma trama por chamada.

## 7. Segurança

`FileResolver.i_resolve` executa, nesta ordem:

1. Verifica sequências `%XX` e decodifica uma vez como UTF-8, de forma estrita.
2. Rejeita NUL, barra invertida e `:`; exige caminho iniciado por `/`.
3. Remove barras iniciais para juntar o caminho à raiz, sem trocar o drive.
4. Usa `realpath` para normalizar componentes e resolver links simbólicos.
5. Usa `commonpath` para confirmar a raiz inteira; prefixos de texto não bastam.
6. Se for diretório, junta `index.html` e repete a verificação de contenção.
7. Só permite arquivo regular existente; o handler abre e verifica novamente o tipo por fstat.

```python
resolved_a = os_a.path.realpath(path_a)
inside_a = os_a.path.commonpath([self_a.root_a, resolved_a]) == self_a.root_a
if not inside_a:
    raise ForbiddenError('O caminho sai do diretório raiz')
```

| Vetor | Esperado |
|---|---|
| `/../../Windows/System32/drivers/etc/hosts` | 403 |
| `/%2e%2e/%2e%2e/secret.txt` | 403 |
| `/assets/../../../secret.txt` | 403 |
| `/%2e%2e%2f%2e%2e%2fsecret.txt` | 403 |
| `/..%5c..%5csecret.txt` | 403 |

Testes extras cobrem `/../www-secret/secret.txt`, NUL, drive do Windows, symlink de
diretório e symlink do index. A comparação ocorre antes de verificar existência;
assim, tentativa de sair da raiz dá 403 mesmo que o alvo não exista.

Raiz e conteúdo são administrados pelo grupo e devem permanecer estáveis. `realpath`
seguido de `open` não é uma operação atômica contra outro processo alterando symlinks;
esta implementação portátil não promete isolamento contra um atacante local com
permissão de escrita. O servidor não oferece endpoints para criar ou alterar arquivos.

## 8. Concorrência, persistência e fechamento

Cada `accept` produz uma thread daemon e um `RequestReader`. Objetos de configuração
e handler são compartilhados para leitura; arquivos e buffers ficam por resposta/conexão.
`logging` sincroniza escritas. O lock do servidor protege os conjuntos de sockets e threads,
sem abranger leitura de arquivo ou espera por clientes. O log inclui IP:porta, thread,
método, caminho, status e bytes HTTP enviados (headers e corpo), não bytes TCP/IP.

`i_keep_alive` interpreta Connection como lista de tokens sem distinguir maiúsculas.
Close tem prioridade. HTTP/1.1 persiste por padrão; HTTP/1.0 exige keep-alive.
O timeout é entre novos bytes, inclusive durante uma mensagem. Um cliente que envia
um byte antes de cada timeout pode continuar conectado; não existe deadline total
de requisição nem limite global de threads. Isso é uma limitação de escala do laboratório.

```python
self_a.sock_a.shutdown(socket_a.SHUT_WR)
deadline_a = time_a.monotonic() + 0.2
```

No encerramento normal, SHUT_WR sinaliza fim de envio; a leitura drena por até 0,2 s,
com deadline total, e close libera o socket. A drenagem reduz RST por dados pendentes,
mas não garante entrega se o peer/reset/rede falhar. Ctrl+C encerra o accept; shutdown
do servidor interrompe sockets ativos e aguarda suas threads. Não é um graceful shutdown
de longa duração: respostas em andamento podem ser interrompidas ao parar o programa.

## 9. Como testar

```bash
python3 tests/run_all.py
python3 tests/test_http.py IP_DO_SERVIDOR 8080
python3 tests/test_stream.py IP_DO_SERVIDOR 8080
python3 tests/concurrency_test.py IP_DO_SERVIDOR 8080 --clients 10
```

`run_all.py` inicia e encerra um servidor temporário com timeout de 0,7 s e adiciona
testes locais de symlinks, arquivo binário de 2 MiB, MIME, timeout e C1/C2. Os scripts
remotos usam o servidor já ativo e os arquivos `www` do projeto. A saída esperada é PASS,
sem falhas/erros e exit code zero. Um skip de symlink no Windows deve ser registrado.

Os comandos curl para cada código estão na tabela de conformidade do
[README](README.md#conformidade-com-curl); use `--path-as-is` nos ataques. HEAD deve
ter Content-Length positivo em arquivo/erro não vazio, mas zero bytes de corpo.
Confirme manualmente em duas máquinas a simultaneidade exigida pelo professor.

## 10. Como medir C1/C2

1. `ipconfig` e `ping -n 20 IP`; anote RTT e perda.
2. Inicie Wireshark na interface real com captura `tcp port 8080`.
3. Rode `python3 tests/benchmark.py IP 8080 --path /test.txt --requests 10 --mode c1`.
4. Aguarde FIN/ACK, salve `capturas/c1.pcapng`; repita com `--mode c2` e `c2.pcapng`.
5. Confira streams, handshake completo e ausência de tráfego estranho; documente retransmissões.
6. Em cada captura, obtenha pacotes, soma frame.len e tempo última−primeira trama.

```bash
tshark -r capturas/c1.pcapng -Y "tcp.flags.syn == 1 && tcp.flags.ack == 1" -T fields -e tcp.stream
tshark -r capturas/c1.pcapng -q -z io,stat,0
tshark -r capturas/c1.pcapng -q -z conv,tcp
tshark -r capturas/c1.pcapng -Y "tcp.port == 8080" -T fields -e frame.time_relative -e frame.len
```

Repita com c2. No Wireshark, use `tcp.port == 8080`, `tcp.stream == N`,
`tcp.flags.syn == 1 && tcp.flags.ack == 1`, `tcp.flags.fin == 1` e
`tcp.analysis.retransmission`. SYN/ACK retransmitido não é novo handshake; confirme os
três passos por stream. Estatísticas de arquivo só representam o experimento se a captura
estiver restrita a ele. O README detalha como capturar com tshark e classificar overhead.

`economia_P = 100·(P1−P2)/P1`; `economia_B = 100·(B1−B2)/B1`.
Para objetos pequenos e sem perdas: `T_C1 ≈ 2·N·RTT`; `T_C2 ≈ (N+1)·RTT`;
diferença ≈ `(N−1)·RTT`. Cada conexão exige um handshake; pedidos sequenciais continuam
custando um RTT cada. O modelo omite transmissão, processamento, encerramento e detalhes
de ACKs. Compare previsão e medição discutindo essas limitações. Tempo do benchmark,
bytes de corpos HTTP e métricas de captura são grandezas diferentes.

## 11. Problemas comuns

| Sintoma | Causa provável / ação |
|---|---|
| Outra máquina não conecta | IP errado, firewall, VLAN ou servidor parado; confirmar ping/TCP e pedir apoio |
| Address already in use | Porta ocupada; encerrar instância anterior ou escolher outra porta alta |
| Raiz inexistente | Terminal em outra pasta; conferir --root ou usar caminho absoluto |
| 403 no arquivo | Caminho proibido, symlink externo ou permissão de leitura |
| 404 em /sub/ | Não há index.html; use /sub/pagina.html |
| Captura vazia | Interface errada, captura em loopback ou filtro com sintaxe errada |
| Cabeçalho Date diferente | Respostas geradas em segundos diferentes; comportamento esperado |
| Corpo parece truncado em HEAD | HEAD não tem corpo; Content-Length informa tamanho hipotético |
| Slow client perde conexão | Timeout sem bytes; aumentar --idle-timeout se necessário no ensaio |
| C2 quase não ganha tempo localmente | RTT local muito baixo; medir entre máquinas |
| HTTP não aparece no Wireshark | Usar Decode As HTTP na porta |
| Teste de symlink pulado | Windows não permitiu criação; repetir em ambiente com permissão |
| Browser não carrega imagem | Conferir GET /imagem.svg, MIME, caminho e painel Rede |
| 417 em upload | Expect não suportado; trabalho serve arquivos GET/HEAD |

## 12. Perguntas para a apresentação

1. **Por que recv não entrega uma requisição pronta?** TCP é fluxo; `RequestReader.i_read_request` acumula e delimita por CRLF CRLF.
2. **Onde fica o começo do próximo pedido?** Em `buffer_a`, preservado por `i_read_request` e `i_read_body`.
3. **Como HEAD evita corpo?** `RequestHandler.i_handle` marca `head_only_a`; `HttpResponse.i_body_bytes` retorna sem produzir bytes.
4. **Por que o tamanho de HEAD não é zero?** Content-Length descreve o corpo que GET enviaria; é calculado por fstat ou pelo erro HTML.
5. **Por que Host é necessário?** Identifica a autoridade HTTP/1.1; `i_parse_head` rejeita ausência e `i_parse_headers` rejeita duplicação.
6. **Por que commonpath e não startswith?** `FileResolver.i_inside_root` compara componentes e não confunde www com www-secret.
7. **Por que decodificar primeiro?** `%2e%2e` precisa virar `..` antes de validar o destino em `i_resolve`.
8. **Como symlinks são tratados?** realpath revela o destino, inclusive do index, e commonpath verifica a raiz.
9. **O que acontece com POST com corpo?** `i_read_body` consome Content-Length e `i_handle` retorna 405 com Allow.
10. **Por que fechar depois de 400?** Framing pode ser inválido; `ConnectionHandler.i_run` não reutiliza o fluxo ambíguo.
11. **Como a conexão permanece aberta?** `i_run` volta ao mesmo reader enquanto `i_keep_alive` permitir.
12. **Close e keep-alive juntos: quem vence?** Close, conforme `i_keep_alive`.
13. **Por que uma thread por conexão?** `i_accept_loop` continua aceitando enquanto outra thread espera I/O; é simples para o laboratório.
14. **O GIL impede esse teste?** A espera por I/O permite outras threads progredirem; a carga é majoritariamente rede/arquivo.
15. **O timeout mede duração total?** Não; `settimeout` limita cada espera sem bytes. `i_recv_more` converte a exceção em IdleTimeout.
16. **Como um arquivo grande não ocupa toda a RAM?** `i_body_bytes` lê blocos de até 65536 bytes e `i_send` envia cada bloco.
17. **Por que shutdown antes de close?** `i_close` sinaliza fim do envio e drena dados pendentes por tempo limitado.
18. **Date depende do idioma do Windows?** Não; `i_format_http_date` usa email.utils com UTC e usegmt=True.
19. **Qual a diferença entre persistência e pipelining?** Persistência reutiliza conexão; pipelining envia vários pedidos sem esperar. O benchmark faz sequência, não pipeline.
20. **De onde vêm os nove RTTs extras de C1?** Com dez pedidos, há dez handshakes em C1 e um em C2, no modelo simplificado.
21. **O número de sendall equivale ao de pacotes?** Não; TCP pode segmentar/agrupar. Pacotes são medidos na captura.
22. **Todos os ACKs são overhead de abertura?** Não; há ACKs de dados e encerramento. Identificar fase/seq/ack por stream.
23. **Onde confirmar interoperabilidade?** `www/index.html` referencia CSS e SVG; outro grupo deve ver todos carregados no navegador.
24. **O que os testes locais não demonstram?** RTT real, duas máquinas, firewall/VDI e interoperabilidade presencial; ver comparação do enunciado.

## 13. Glossário

| Termo | Significado |
|---|---|
| RTT | Tempo de ida e volta entre os pontos medidos |
| Handshake | SYN, SYN/ACK e ACK que estabelecem uma conexão TCP |
| Keep-alive | Reutilização da conexão para novas mensagens HTTP |
| Pipelining | Vários pedidos enviados na conexão antes de receber todas as respostas |
| IMF-fixdate | Formato fixo de data HTTP com dia/mês em inglês e GMT |
| Percent-encoding | Representação de um byte como `%HH` em URI |
| Traversal | Tentativa de escapar da raiz usando componentes de caminho |
| TIME_WAIT | Estado TCP que conserva informações após encerramento para lidar com segmentos atrasados |
| CRLF | Bytes 13 e 10 usados como terminador de linha HTTP |
| Framing | Regras para separar cabeçalhos, corpo e a mensagem seguinte |
| FIN / RST | Sinalização de encerramento normal / reinicialização abrupta de conexão |

Referências técnicas: [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html),
[RFC 9112](https://www.rfc-editor.org/rfc/rfc9112.html) e
[manual tshark](https://www.wireshark.org/docs/man-pages/tshark.html).
