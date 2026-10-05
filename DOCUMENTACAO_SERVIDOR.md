# Documentação do servidor — guia para os três integrantes

## 1. Visão geral

O servidor oferece arquivos estáticos por HTTP/1.1 implementado manualmente sobre TCP.
Cada conexão tem uma thread e um buffer próprio. A lógica não pressupõe que um recv
corresponda a uma requisição. Nenhum módulo HTTP de servidor é utilizado.

```text
server.main()
  → HttpServer(...).start(): socket → bind → listen(128)
      → _accept_loop(): accept → thread daemon
          → _serve_connection(): ConnectionHandler.run()
              ┌→ RequestReader.read_request()
              │    recv → buffer → CRLF CRLF → parse → consumir corpo
              │    preserva bytes da próxima mensagem
              │  → RequestHandler.handle(request)
              │    → FileResolver.resolve(path) → arquivo aberto/fstat
              │    → HttpResponse (200 ou erro)
              │  → _keep_alive() → Connection e demais headers
              │  → send(): to_head_bytes() → sendall(headers)
              │               body_bytes() → sendall(blocos)
              └── se persistente, volta para a próxima requisição
                  senão/timeout/EOF/erro: close() → shutdown → drenar → close
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
| Socket de escuta | HttpServer.start | HttpServer.shutdown |
| Socket aceito | accept | ConnectionHandler.close; shutdown do servidor acorda a thread |
| Thread daemon | HttpServer._accept_loop | Retorna de _serve_connection; servidor aguarda com join |
| Buffer HTTP | RequestReader.__init__ | Descartado ao terminar a conexão |
| Arquivo aberto | RequestHandler.handle | HttpResponse.close no finally de send |
| Fixtures de testes | tests/run_all.py | TemporaryDirectory ao terminar |

Os identificadores abaixo refletem o código revisado. As classes definem `__init__`
diretamente; em `RawClient`, `__enter__` e `__exit__` implementam o protocolo `with`.
Os métodos gerados por dataclass não são implementados manualmente. Os auxiliares
como `_parse_head` usam sublinhado inicial para indicar uso interno.

## 4. Referência por módulo

### server.py

#### HttpServer

Orquestra a escuta. Os campos de estado são inicializados em __init__; port é atualizado após bind para permitir porta temporária nos testes.

##### `HttpServer.__init__`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpServer.__init__(self, host: str, port: int, root: str, idle_timeout: float=5.0, server_name: str='Grupo-Redes-T1') -> None` |
| O que faz | Valida configuração e prepara estado compartilhado. |
| Como faz | Rejeita loopback, timeout não positivo/infinito e Server não ASCII; cria resolver, handler, config, Event, Lock e conjuntos. |
| Erros/conexão | ValueError em configuração/raiz inválida; OSError na resolução do host; ainda não aceita conexões. |
| Quem chama | server.main e tests/run_all.py, por HttpServer(...). |
| Por quê | Validar antes do bind evita iniciar uma configuração inutilizável. |
| Quem chama internamente | `ConnectionConfig`, `threading.Event`, `threading.Lock`, `set`, `ipaddress.ip_address`, `ValueError`, `any`, `RequestHandler`, `socket.gethostbyname`, `math.isfinite`, `FileResolver`, `ord` |

##### `HttpServer.start`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpServer.start(self) -> None` |
| O que faz | Abre o socket de escuta e executa o servidor até parar. |
| Como faz | Cria AF_INET/SOCK_STREAM, SO_REUSEADDR, bind, listen(128), timeout de accept de 0,25 s; guarda porta efetiva e entra no accept loop. |
| Erros/conexão | OSError sobe ao chamador; finally sempre chama shutdown. Porta 0 é usada apenas internamente pelos testes. |
| Quem chama | server.main ou thread da suíte local. |
| Por quê | SO_REUSEADDR facilita reinício; timeout permite observar o pedido de parada. |
| Quem chama internamente | `socket.socket`, `self.sock.setsockopt`, `self.sock.bind`, `self.sock.listen`, `self.sock.settimeout`, `logging.info`, `self._accept_loop`, `self.shutdown`, `self.sock.getsockname` |

##### `HttpServer._accept_loop`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpServer._accept_loop(self) -> None` |
| O que faz | Aceita clientes e cria uma thread daemon por socket. |
| Como faz | A cada accept prepara worker; com Lock verifica parada, registra socket/thread e inicia; timeout volta ao laço. |
| Erros/conexão | Timeout não é falha; OSError durante shutdown termina, outro OSError propaga. Socket aceito após parada é fechado. |
| Quem chama | HttpServer.start. |
| Por quê | Espera de um cliente ocorre no worker e não bloqueia novas conexões. |
| Quem chama internamente | `self.stopping.is_set`, `threading.Thread`, `self.sock.accept`, `self.connections.add`, `self.workers.add`, `worker.start`, `sock.close` |

##### `HttpServer._serve_connection`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpServer._serve_connection(self, sock: socket.socket, addr: tuple) -> None` |
| O que faz | Executa o handler de uma conexão e retira seu registro. |
| Como faz | Constrói ConnectionHandler, chama run e no finally remove socket e thread dos conjuntos sob Lock. |
| Erros/conexão | O handler trata erros de socket; finally limpa registros mesmo se outra exceção subir. |
| Quem chama | Thread criada em _accept_loop. |
| Por quê | Centraliza o ciclo de vida e evita acumular referências a workers já concluídos. |
| Quem chama internamente | `ConnectionHandler(sock, addr, self.config).run`, `self.connections.discard`, `self.workers.discard`, `ConnectionHandler`, `threading.current_thread` |

##### `HttpServer.shutdown`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpServer.shutdown(self) -> None` |
| O que faz | Interrompe escuta e conexões ativas e aguarda workers. |
| Como faz | Marca Event, fecha listener, copia conjuntos sob Lock, faz SHUT_RDWR nos sockets e join de até um segundo por thread. |
| Erros/conexão | Ignora OSError de sockets já encerrados; não faz join na própria thread. |
| Quem chama | Finally de start e suíte local. |
| Por quê | Acordar recv bloqueado evita esperar todo o timeout ocioso ao encerrar. |
| Quem chama internamente | `self.stopping.set`, `self.sock.close`, `list`, `sock.shutdown`, `threading.current_thread`, `worker.join` |

##### `main`

| Campo | Descrição |
|---|---|
| Assinatura | `main() -> None` |
| O que faz | Interpreta CLI, configura log e executa HttpServer. |
| Como faz | Argparse exige porta/raiz, valida porta alta, configura formato com thread e captura Ctrl+C ou erros de inicialização. |
| Erros/conexão | Argparse retorna código 2 para uso inválido; OSError/ValueError produz saída 1; Ctrl+C é encerramento solicitado. |
| Quem chama | Bloco if __name__ da CLI. |
| Por quê | Uma entrada única mantém parâmetros documentados e erros legíveis. |
| Quem chama internamente | `argparse.ArgumentParser`, `parser.add_argument`, `parser.parse_args`, `logging.basicConfig`, `parser.error`, `HttpServer`, `server.start`, `logging.info`, `parser.exit` |

### connection.py

#### ConnectionConfig

Dataclass imutável: handler: RequestHandler, idle_timeout: float, server_name: str. Construtor gerado recebe esses três valores; compartilhada entre workers.

#### ConnectionHandler

Dona do socket aceito, endereço, config e reader. Só uma thread executa run para essa conexão.

##### `ConnectionHandler.__init__`

| Campo | Descrição |
|---|---|
| Assinatura | `ConnectionHandler.__init__(self, sock: socket.socket, addr: tuple, config: ConnectionConfig) -> None` |
| O que faz | Guarda socket, endereço, configuração e cria um RequestReader. |
| Como faz | Usa limite de 16384 bytes para cabeçalhos, com buffer exclusivo da conexão. |
| Erros/conexão | Não inicia leitura; socket será liberado pelo finally de run. |
| Quem chama | HttpServer._serve_connection, por ConnectionHandler(...). |
| Por quê | Estado por conexão impede misturar bytes de clientes diferentes. |
| Quem chama internamente | `RequestReader` |

##### `ConnectionHandler.run`

| Campo | Descrição |
|---|---|
| Assinatura | `ConnectionHandler.run(self) -> None` |
| O que faz | Processa pedidos sequencialmente no mesmo socket. |
| Como faz | Aplica timeout; lê pedido e corpo; pede resposta; decide persistência; adiciona Date/Server/Connection; envia e registra bytes; repete se permitido. |
| Erros/conexão | HttpParseError vira erro HTTP com close; IdleTimeout/EOF termina silenciosamente; OSError encerra. Finally sempre chama close. |
| Quem chama | HttpServer._serve_connection. |
| Por quê | Separar leitura de parsing e política de conexão permite preservar o fluxo corretamente. |
| Quem chama internamente | `self.sock.settimeout`, `self.close`, `response.headers.update`, `self.send`, `logging.info`, `logging.debug`, `self.reader.read_request`, `self.config.handler.handle`, `self._keep_alive`, `HttpResponse.error`, `format_http_date` |

##### `ConnectionHandler._keep_alive`

| Campo | Descrição |
|---|---|
| Assinatura | `ConnectionHandler._keep_alive(self, request: HttpRequest) -> bool` |
| O que faz | Decide se aceita outro pedido na conexão. |
| Como faz | Separa Connection por vírgula, normaliza tokens; close vence; HTTP/1.0 só persiste com keep-alive; demais versões aceitas 1.x persistem. |
| Erros/conexão | Não realiza I/O e não fecha diretamente. |
| Quem chama | ConnectionHandler.run. |
| Por quê | Connection é uma lista case-insensitive, não uma comparação simples de string. |
| Quem chama internamente | `token.strip().lower`, `request.header('connection').split`, `token.strip`, `request.header` |

##### `ConnectionHandler.send`

| Campo | Descrição |
|---|---|
| Assinatura | `ConnectionHandler.send(self, response: HttpResponse) -> int` |
| O que faz | Envia cabeçalhos e blocos do corpo; retorna total de bytes HTTP. |
| Como faz | sendall dos cabeçalhos, iteração de body_bytes e sendall por bloco; finally fecha o arquivo da resposta. |
| Erros/conexão | OSError no envio/leitura propaga para run, que encerra; não tenta uma segunda resposta parcial. |
| Quem chama | ConnectionHandler.run. |
| Por quê | sendall lida com escritas parciais; finally libera o arquivo também em HEAD e erro. |
| Quem chama internamente | `response.to_head_bytes`, `self.sock.sendall`, `len`, `response.body_bytes`, `response.close` |

##### `ConnectionHandler.close`

| Campo | Descrição |
|---|---|
| Assinatura | `ConnectionHandler.close(self) -> None` |
| O que faz | Encerra a conexão com drenagem limitada. |
| Como faz | SHUT_WR; calcula deadline total de 0,2 s; lê dados até EOF/deadline; close no finally. |
| Erros/conexão | Ignora OSError, incluindo timeout ou peer que já desconectou. |
| Quem chama | Finally de ConnectionHandler.run. |
| Por quê | Reduz risco de RST por dados não lidos sem permitir drenagem infinita. |
| Quem chama internamente | `self.sock.shutdown`, `self.sock.close`, `time.monotonic`, `self.sock.settimeout`, `self.sock.recv` |

### http_parser.py

#### HttpRequest

Dataclass: method, target, path, query, version (str), headers (dict, padrão vazio), body (bytes, padrão vazio). Construtor gerado nessa ordem; path permanece codificado até FileResolver.

##### `HttpRequest.header`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpRequest.header(self, name: str) -> str` |
| O que faz | Busca valor de cabeçalho sem distinguir maiúsculas. |
| Como faz | Converte nome para minúsculas e usa get com string vazia para ausência. |
| Erros/conexão | Sem I/O; não altera conexão. |
| Quem chama | RequestReader e ConnectionHandler._keep_alive. |
| Por quê | O parser armazena todos os nomes em minúsculas, preservando os valores. |
| Quem chama internamente | `self.headers.get`, `name.lower` |

#### HttpParseError

Exception com status e head_only. A mensagem fica em Exception.args; só texto fixo vai à resposta HTML.

##### `HttpParseError.__init__`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpParseError.__init__(self, status: int, message: str) -> None` |
| O que faz | Cria exceção de parsing com código HTTP e mensagem. |
| Como faz | Inicializa Exception, guarda status e inicia head_only como falso; o parser pode marcá-lo para HEAD. |
| Erros/conexão | É levantada por RequestReader e tratada por ConnectionHandler.run. |
| Quem chama | Pontos de validação do parser, por HttpParseError(...). |
| Por quê | Transporta informação suficiente para gerar erro seguro sem expor a entrada na página HTML. |
| Quem chama internamente | `super().__init__`, `super` |

#### IdleTimeout

Subclasse de Exception sem métodos próprios. Distingue timeout de leitura e provoca fechamento silencioso.

#### ConnectionClosedByPeer

Subclasse de Exception sem métodos próprios. Representa EOF de recv; provocará fechamento silencioso.

#### RequestReader

Mantém sock, max_header_bytes e buffer. Não fecha o socket; isso pertence ao ConnectionHandler.

##### `RequestReader.__init__`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader.__init__(self, sock: socket.socket, max_header_bytes: int=16384) -> None` |
| O que faz | Prepara leitor e buffer vazio. |
| Como faz | Guarda socket e limite de cabeçalho fornecido; não consome bytes. |
| Erros/conexão | Sem I/O; o dono do socket é ConnectionHandler. |
| Quem chama | ConnectionHandler.__init__. |
| Por quê | O buffer precisa existir por toda a conexão, não por recv. |
| Quem chama internamente |  |

##### `RequestReader.read_request`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader.read_request(self) -> HttpRequest` |
| O que faz | Lê exatamente uma requisição completa. |
| Como faz | Procura CRLF CRLF; aplica limite à mensagem; preserva HEAD em rejeição; separa e retém excedente; interpreta head; consome Content-Length; retorna HttpRequest. |
| Erros/conexão | HttpParseError→resposta/close; IdleTimeout/ConnectionClosedByPeer→close silencioso; OSError→close. |
| Quem chama | ConnectionHandler.run. |
| Por quê | Preservar o excedente resolve fragmentação, pipeline e corpo seguido de outra mensagem. |
| Quem chama internamente | `self.buffer.find`, `self._recv_more`, `HttpParseError`, `self.buffer.startswith`, `self._parse_head`, `self.read_body`, `int`, `len`, `request.header` |

##### `RequestReader.read_body`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader.read_body(self, n: int) -> bytes` |
| O que faz | Retira n bytes do corpo e guarda o resto. |
| Como faz | Valida 0≤n≤1 MiB; recebe até ter n bytes; devolve prefixo e mantém excedente. |
| Erros/conexão | Limite inválido gera 400; timeout/EOF propaga e termina a conexão sem resposta adicional. |
| Quem chama | RequestReader.read_request. |
| Por quê | Mesmo um método não suportado pode ter corpo; consumi-lo evita dessincronização. |
| Quem chama internamente | `HttpParseError`, `len`, `self._recv_more` |

##### `RequestReader._recv_more`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader._recv_more(self) -> None` |
| O que faz | Acrescenta ao buffer os próximos bytes de TCP. |
| Como faz | recv(4096); converte timeout; EOF vira exceção específica; soma dados ao buffer. |
| Erros/conexão | socket.timeout→IdleTimeout; recv vazio→ConnectionClosedByPeer; outros OSError propagam. |
| Quem chama | read_request e read_body. |
| Por quê | Centraliza diferenças entre silêncio, EOF e novos dados. |
| Quem chama internamente | `self.sock.recv`, `ConnectionClosedByPeer`, `IdleTimeout` |

##### `RequestReader._parse_head`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader._parse_head(self, data: bytes) -> HttpRequest` |
| O que faz | Interpreta linha inicial, campos e regras de framing. |
| Como faz | Decodifica ISO-8859-1 para correspondência byte-a-byte; separa CRLF; valida Host, Transfer-Encoding, Content-Length e Expect; separa query; monta HttpRequest. |
| Erros/conexão | 400 para framing/Host inválido, 417 para Expect; marca HEAD antes de propagar HttpParseError. Corpo é consumido depois. |
| Quem chama | RequestReader.read_request. |
| Por quê | Validação anterior à leitura do corpo evita ambiguidades e espera por 100-continue não implementado. |
| Quem chama internamente | `data.decode('iso-8859-1').split`, `self._parse_request_line`, `self._parse_headers`, `headers.get`, `target.partition`, `HttpRequest`, `data.decode`, `HttpParseError`, `int`, `lines[0].startswith`, `re.fullmatch`, `len` |

##### `RequestReader._parse_request_line`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader._parse_request_line(self, line: str) -> tuple` |
| O que faz | Extrai método, target e versão de uma linha. |
| Como faz | Exige três campos separados por espaço; método token; target ASCII sem controles/fragmento; versão HTTP/d.d; major 1; GET/HEAD com caminho iniciado por /. |
| Erros/conexão | 400 para sintaxe; 505 para major incompatível; todos fecham a conexão no handler. |
| Quem chama | RequestReader._parse_head. |
| Por quê | Parser estrito delimita o subconjunto de origem do laboratório, sem fingir suporte a proxy. |
| Quem chama internamente | `line.split`, `HttpParseError`, `TOKEN.fullmatch`, `any`, `re.fullmatch`, `len`, `all`, `target.startswith`, `ord` |

##### `RequestReader._parse_headers`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestReader._parse_headers(self, lines: list) -> dict` |
| O que faz | Produz dicionário de cabeçalhos normalizados. |
| Como faz | Exige dois-pontos, nome token sem espaço antes de :, valor sem controles; remove OWS; rejeita Host/Content-Length/Transfer-Encoding repetidos; combina outros campos por vírgula. |
| Erros/conexão | HttpParseError 400 fecha a conexão. Host vazio ou com separadores proibidos também é rejeitado. |
| Quem chama | RequestReader._parse_head. |
| Por quê | Framing único evita interpretações contraditórias de uma mesma sequência de bytes. |
| Quem chama internamente | `line.split`, `name.lower`, `value.strip`, `any`, `HttpParseError`, `TOKEN.fullmatch`, `ord` |

### http_response.py

##### `format_http_date`

| Campo | Descrição |
|---|---|
| Assinatura | `format_http_date() -> str` |
| O que faz | Produz a data HTTP do instante atual em GMT. |
| Como faz | datetime UTC e format_datetime(usegmt=True). |
| Erros/conexão | Sem I/O de rede; função não altera conexão. |
| Quem chama | RequestHandler.handle e ConnectionHandler.run. |
| Por quê | email.utils não depende do locale para nomes de dias e meses. |
| Quem chama internamente | `format_datetime`, `datetime.now` |

##### `guess_content_type`

| Campo | Descrição |
|---|---|
| Assinatura | `guess_content_type(path: str) -> str` |
| O que faz | Escolhe MIME pela extensão, ignorando caixa. |
| Como faz | splitext, lower e tabela de 12 extensões; fallback application/octet-stream. |
| Erros/conexão | Não abre arquivo nem altera conexão. |
| Quem chama | RequestHandler.handle e teste de MIME. |
| Por quê | Tabela própria produz resultados previsíveis entre sistemas operacionais. |
| Quem chama internamente | `MIME_TYPES.get`, `os.path.splitext(path)[1].lower`, `os.path.splitext` |

#### HttpResponse

Dataclass: status: int, headers: dict={}, body: bytes=b'', head_only: bool=False, file: Optional[BinaryIO]=None. Cada dicionário default é independente. O stream aberto é liberado em close.

##### `HttpResponse.to_head_bytes`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpResponse.to_head_bytes(self) -> bytes` |
| O que faz | Serializa status e headers em bytes HTTP. |
| Como faz | Consulta razão padronizada, gera linhas Name: Value, junta com CRLF e termina com linha vazia. |
| Erros/conexão | KeyError para status interno não registrado ou erro de encoding em uso indevido; entradas reais usam valores controlados/ASCII. |
| Quem chama | ConnectionHandler.send. |
| Por quê | HTTP é gerado manualmente; não usa biblioteca pronta de servidor. |
| Quem chama internamente | `lines.extend`, `('\r\n'.join(lines) + '\r\n\r\n').encode`, `self.headers.items`, `'\r\n'.join` |

##### `HttpResponse.body_bytes`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpResponse.body_bytes(self) -> Iterator[bytes]` |
| O que faz | Gera corpo em memória ou blocos do arquivo. |
| Como faz | HEAD termina sem yield; erro produz body; arquivo lê no máximo 65536 bytes por bloco até o Content-Length anunciado. |
| Erros/conexão | OSError se arquivo truncar; send libera descritor e run fecha socket. |
| Quem chama | ConnectionHandler.send. |
| Por quê | Memória limitada e nenhum byte além do tamanho anunciado caso o arquivo cresça. |
| Quem chama internamente | `int`, `self.file.read`, `len`, `min`, `OSError` |

##### `HttpResponse.close`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpResponse.close(self) -> None` |
| O que faz | Fecha o arquivo associado, se houver. |
| Como faz | Chama close do BinaryIO; resposta HTML sem arquivo não exige ação. |
| Erros/conexão | Falha de I/O pode propagar ao handler; socket será encerrado. |
| Quem chama | Finally de ConnectionHandler.send. |
| Por quê | Uma única dona do descritor evita vazamento de recursos. |
| Quem chama internamente | `self.file.close` |

##### `HttpResponse.error`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpResponse.error(cls, status: int, extra_headers: Optional[dict]=None) -> 'HttpResponse'` |
| O que faz | Constrói resposta de erro com HTML curto em português. |
| Como faz | Consulta textos fixos, codifica UTF-8, calcula len dos bytes, define Content-Length/Type e une extra_headers como Allow. |
| Erros/conexão | Status deve existir nas tabelas; política de fechamento é decidida em ConnectionHandler. |
| Quem chama | RequestHandler.handle e ConnectionHandler.run. |
| Por quê | Tamanho calculado após encode é correto também com caracteres acentuados. |
| Quem chama internamente | `f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>{status} {REASONS[status]}</title><h1>{status}</h1><p>{MESSAGES[status]}</p></html>\n'.encode`, `headers.update`, `cls`, `str`, `len` |

### file_resolver.py

#### ForbiddenError

Exception sem métodos próprios; sinaliza contenção/caminho proibido e vira 403 no handler.

#### NotFoundError

Exception sem métodos próprios; sinaliza ausência de arquivo regular e vira 404.

#### FileResolver

Guarda root canonicalizado. URL não controla a raiz; resolução retorna caminho absoluto seguro para raiz estável.

##### `FileResolver.__init__`

| Campo | Descrição |
|---|---|
| Assinatura | `FileResolver.__init__(self, root: str) -> None` |
| O que faz | Canonicaliza e valida o diretório raiz. |
| Como faz | realpath e isdir; armazena root absoluto. |
| Erros/conexão | ValueError se a raiz não existe; servidor não inicia. |
| Quem chama | HttpServer.__init__, por FileResolver(...). |
| Por quê | Todas as verificações usam a mesma raiz real. |
| Quem chama internamente | `os.path.realpath`, `os.path.isdir`, `ValueError` |

##### `FileResolver._inside_root`

| Campo | Descrição |
|---|---|
| Assinatura | `FileResolver._inside_root(self, path: str) -> str` |
| O que faz | Canonicaliza destino e comprova contenção na raiz. |
| Como faz | realpath seguido de commonpath; ValueError de drives incompatíveis é tratado como fora da raiz. |
| Erros/conexão | ForbiddenError se fora; handler converte para 403 sem necessariamente fechar. |
| Quem chama | FileResolver.resolve, inclusive para index.html. |
| Por quê | Comparação por componentes evita www-secret e resolve symlinks. |
| Quem chama internamente | `os.path.realpath`, `ForbiddenError`, `os.path.commonpath` |

##### `FileResolver.resolve`

| Campo | Descrição |
|---|---|
| Assinatura | `FileResolver.resolve(self, raw_path: str) -> str` |
| O que faz | Resolve URL para arquivo regular seguro. |
| Como faz | Verifica %XX; unquote UTF-8 estrito; rejeita NUL, barra invertida e :; junta raiz; verifica contenção; acrescenta index se diretório e valida novamente; exige isfile. |
| Erros/conexão | ForbiddenError para caminho proibido; NotFoundError se ausente/não regular; OSError tratado pelo handler. |
| Quem chama | RequestHandler.handle. |
| Por quê | Decodificar antes de validar captura traversal codificado; índice e symlinks não escapam da raiz estável. |
| Quem chama internamente | `re.search`, `self._inside_root`, `os.path.isdir`, `ForbiddenError`, `unquote`, `any`, `os.path.join`, `os.path.isfile`, `NotFoundError`, `path.startswith`, `path.lstrip` |

### request_handler.py

#### RequestHandler

Guarda resolver e server_name. Não retém request/resposta entre chamadas.

##### `RequestHandler.__init__`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestHandler.__init__(self, resolver: FileResolver, server_name: str) -> None` |
| O que faz | Guarda resolver e identificador do servidor. |
| Como faz | Somente configuração compartilhada para leitura. |
| Erros/conexão | Nenhum I/O de rede; criação pelo servidor. |
| Quem chama | HttpServer.__init__, por RequestHandler(...). |
| Por quê | Handler é compartilhável porque não guarda estado de um pedido. |
| Quem chama internamente |  |

##### `RequestHandler.handle`

| Campo | Descrição |
|---|---|
| Assinatura | `RequestHandler.handle(self, request: HttpRequest) -> HttpResponse` |
| O que faz | Transforma pedido em resposta pronta para envio. |
| Como faz | Outros métodos→405/Allow; GET/HEAD→resolve, open binário, fstat e MIME; arquivo passa à resposta; traduz erros; define flag HEAD e headers comuns. |
| Erros/conexão | Forbidden/Permission→403; ausência/não regular→404; outro OSError→500; arquivo não transferido é fechado em finally. |
| Quem chama | ConnectionHandler.run. |
| Por quê | GET e HEAD seguem o mesmo cálculo de headers, diferindo apenas na produção de corpo. |
| Quem chama internamente | `response.headers.update`, `HttpResponse.error`, `self.resolver.resolve`, `open`, `os.fstat`, `HttpResponse`, `format_http_date`, `file.fileno`, `stat.S_ISREG`, `NotFoundError`, `file.close`, `str`, `guess_content_type` |

### tests/client.py

#### RawClient

Cliente de teste com sock e buffer; fornece context manager com __enter__ e __exit__ definidos diretamente e interpreta respostas à mão.

##### `RawClient.__init__`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.__init__(self, host: str, port: int, timeout: float=4.0) -> None` |
| O que faz | Abre conexão TCP de teste e buffer vazio. |
| Como faz | create_connection com timeout configurável. |
| Erros/conexão | OSError se servidor indisponível; falha no teste. |
| Quem chama | Testes e exchange, por RawClient(...). |
| Por quê | Cliente independente não compartilha parser HTTP com servidor. |
| Quem chama internamente | `socket.create_connection` |

##### `RawClient.send`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.send(self, data: bytes) -> None` |
| O que faz | Envia bytes fornecidos integralmente. |
| Como faz | sendall no socket. |
| Erros/conexão | OSError falha no teste; with garante fechamento. |
| Quem chama | Testes de conformidade/stream/concorrência. |
| Por quê | Permite criar pedidos malformados que bibliotecas HTTP recusariam. |
| Quem chama internamente | `self.sock.sendall` |

##### `RawClient.read_response`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.read_response(self, head_only: bool=False) -> tuple` |
| O que faz | Lê uma resposta por Content-Length e preserva excedente. |
| Como faz | Acumula head, valida versão e headers únicos; para HEAD lê zero bytes; devolve status, headers e corpo. |
| Erros/conexão | AssertionError em EOF/versão/duplicação; ValueError em formato; OSError de rede. |
| Quem chama | Scripts de teste. |
| Por quê | Leitor separado revela erros de framing no servidor. |
| Quem chama internamente | `self.buffer.split`, `head.decode('iso-8859-1').split`, `lines[0].split`, `self._receive`, `AssertionError`, `line.split`, `value.strip`, `int`, `len`, `head.decode`, `name.lower` |

##### `RawClient._receive`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient._receive(self) -> None` |
| O que faz | Recebe e acumula bytes da resposta. |
| Como faz | recv(65536); EOF prematuro falha. |
| Erros/conexão | AssertionError em EOF ou OSError de rede. |
| Quem chama | RawClient.read_response. |
| Por quê | Centraliza verificação de truncamento. |
| Quem chama internamente | `self.sock.recv`, `AssertionError` |

##### `RawClient.close`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.close(self) -> None` |
| O que faz | Libera socket do teste. |
| Como faz | close no socket. |
| Erros/conexão | OSError eventual de recurso. |
| Quem chama | __exit__ e chamadores diretos. |
| Por quê | Evita conexões sobrando ao fim dos testes. |
| Quem chama internamente | `self.sock.close` |

##### `RawClient.__enter__`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.__enter__(self) -> 'RawClient'` |
| O que faz | Entrega o cliente ao bloco with. |
| Como faz | Retorna self. |
| Erros/conexão | Não altera rede. |
| Quem chama | Protocolo __enter__ do Python. |
| Por quê | Permite cleanup automático. |
| Quem chama internamente |  |

##### `RawClient.__exit__`

| Campo | Descrição |
|---|---|
| Assinatura | `RawClient.__exit__(self, *args) -> None` |
| O que faz | Fecha o cliente ao sair de with. |
| Como faz | Chama close; não suprime exceções. |
| Erros/conexão | Falha original do teste permanece visível. |
| Quem chama | Protocolo __exit__ do Python. |
| Por quê | Libera recursos mesmo quando uma asserção falha. |
| Quem chama internamente | `self.close` |

##### `request`

| Campo | Descrição |
|---|---|
| Assinatura | `request(path: str='/test.txt', method: str='GET', connection: str='keep-alive', version: str='HTTP/1.1') -> bytes` |
| O que faz | Monta pedido HTTP de teste em bytes ASCII. |
| Como faz | Interpola método/caminho/versão e Host/Connection com CRLF. |
| Erros/conexão | UnicodeEncodeError se uso fora do subconjunto ASCII de teste. |
| Quem chama | Testes e cliente de concorrência. |
| Por quê | Mantém fixtures fáceis de ler e modificar. |
| Quem chama internamente | `f'{method} {path} {version}\r\nHost: laboratorio\r\nConnection: {connection}\r\n\r\n'.encode` |

##### `exchange`

| Campo | Descrição |
|---|---|
| Assinatura | `exchange(data: bytes, head_only: bool=False) -> tuple` |
| O que faz | Executa um único pedido e lê sua resposta. |
| Como faz | Abre RawClient em with, envia bytes e lê com opção HEAD. |
| Erros/conexão | Propaga falhas de rede/framing para unittest. |
| Quem chama | HttpTests. |
| Por quê | Reduz repetição sem reutilizar implementação do servidor. |
| Quem chama internamente | `RawClient`, `client.send`, `client.read_response` |

##### `run_suite`

| Campo | Descrição |
|---|---|
| Assinatura | `run_suite(suite: unittest.TestSuite) -> bool` |
| O que faz | Executa TestSuite e imprime PASS/FAIL. |
| Como faz | TextTestRunner verbosity 2; consulta resultado; devolve bool. |
| Erros/conexão | Falhas/erros ficam no resultado, não são escondidos. |
| Quem chama | remote_main e run_all.py. |
| Por quê | Exit code final pode indicar sucesso real a scripts. |
| Quem chama internamente | `unittest.TextTestRunner(verbosity=2).run`, `print`, `result.wasSuccessful`, `unittest.TextTestRunner`, `len` |

##### `remote_main`

| Campo | Descrição |
|---|---|
| Assinatura | `remote_main(case: type) -> None` |
| O que faz | Lê host/porta e executa a classe de testes remotos. |
| Como faz | Atualiza HOST/PORT; loader padrão reconhece test_...; carrega e executa classe. |
| Erros/conexão | SystemExit 0 se passou, 1 se falhou; argparse 2 se uso inválido. |
| Quem chama | Blocos principais de test_http.py e test_stream.py. |
| Por quê | Permite mesmo teste contra máquina local ou remota. |
| Quem chama internamente | `argparse.ArgumentParser`, `parser.add_argument`, `parser.parse_args`, `SystemExit`, `run_suite`, `unittest.defaultTestLoader.loadTestsFromTestCase` |

### tests/test_http.py

#### HttpTests

TestCase de conformidade remota; utiliza www entregue e os helpers independentes de client.py.

##### `HttpTests.test_get_and_required_headers`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.test_get_and_required_headers(self) -> None` |
| O que faz | Confere GET 200, corpo literal, tamanho em bytes, MIME, Date, Server e close. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `exchange`, `self.assertEqual`, `self.assertTrue`, `self.assertRegex`, `request`, `'Arquivo de teste do Trabalho 1.\n'.encode`, `int`, `len` |

##### `HttpTests.test_head_same_headers_and_no_body`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.test_head_same_headers_and_no_body(self) -> None` |
| O que faz | Compara GET e HEAD em 200/403/404; ignora apenas Date; confirma EOF sem corpo. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self.subTest`, `exchange`, `request`, `RawClient`, `connection.send`, `connection.read_response`, `self.assertEqual`, `get_headers.pop`, `headers.pop`, `connection.sock.recv`, `int`, `len` |

##### `HttpTests.test_bad_requests_close`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.test_bad_requests_close(self) -> None` |
| O que faz | Envia request line/header/Host/framing inválidos e headers excessivos; espera 400 e EOF. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self.subTest`, `RawClient`, `connection.send`, `connection.read_response`, `self.assertEqual`, `int`, `len`, `connection.sock.recv` |

##### `HttpTests.test_traversal_vectors`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.test_traversal_vectors(self) -> None` |
| O que faz | Verifica oito vetores, incluindo os cinco exigidos, NUL, drive e prefixo www-secret; espera 403. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self.subTest`, `self.assertEqual`, `exchange`, `request` |

##### `HttpTests.test_not_found_and_directory_index`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.test_not_found_and_directory_index(self) -> None` |
| O que faz | Confere 404 ausente e subdiretório sem index, 200 na raiz com index e na página explícita. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self.assertEqual`, `exchange`, `request` |

##### `HttpTests.test_method_not_allowed`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.test_method_not_allowed(self) -> None` |
| O que faz | Confere DELETE→405 e Allow GET, HEAD. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `exchange`, `self.assertEqual`, `request` |

##### `HttpTests.test_query_percent_encoding_and_header_case`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.test_query_percent_encoding_and_header_case(self) -> None` |
| O que faz | Confere percent-decoding, query ignorada, header sem espaço e nomes de headers com caixa mista. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self.assertEqual`, `exchange` |

##### `HttpTests.test_http_10_and_close_token`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.test_http_10_and_close_token(self) -> None` |
| O que faz | Confere fechamento HTTP/1.0 padrão, keep-alive explícito e prioridade de CLOSE em lista. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self.assertEqual`, `request`, `exchange` |

##### `HttpTests.test_binary_mime_and_version`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.test_binary_mime_and_version(self) -> None` |
| O que faz | Confere MIME de SVG e 505 para HTTP/2.0 textual; não negocia HTTP/2. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `exchange`, `self.assertEqual`, `request` |

##### `HttpTests.test_expect_rejected_without_waiting_for_body`

| Campo | Descrição |
|---|---|
| Assinatura | `HttpTests.test_expect_rejected_without_waiting_for_body(self) -> None` |
| O que faz | Envia Expect com Content-Length mas sem corpo; espera 417 imediato. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self.assertEqual`, `exchange` |

### tests/test_stream.py

#### StreamTests

TestCase de fragmentação, pipeline, corpo e sequência persistente.

##### `StreamTests.test_fragmented_byte_by_byte`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.test_fragmented_byte_by_byte(self) -> None` |
| O que faz | Escreve um byte por vez com pequeno intervalo e recebe 200 ao completar. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `RawClient`, `request`, `self.assertEqual`, `connection.send`, `time.sleep`, `bytes`, `connection.read_response` |

##### `StreamTests.test_three_pipelined_requests`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.test_three_pipelined_requests(self) -> None` |
| O que faz | Envia três pedidos em uma send; confirma três status na ordem 200,404,200 e EOF. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `RawClient`, `self.assertEqual`, `request`, `connection.sock.send`, `len`, `connection.sock.recv`, `connection.read_response`, `range` |

##### `StreamTests.test_complete_plus_half_next_request`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.test_complete_plus_half_next_request(self) -> None` |
| O que faz | Envia pedido completo e metade do seguinte; lê primeiro, completa segundo e verifica 200. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `request`, `len`, `RawClient`, `connection.send`, `self.assertEqual`, `connection.read_response` |

##### `StreamTests.test_body_consumed_before_next_request`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.test_body_consumed_before_next_request(self) -> None` |
| O que faz | POST com cinco bytes seguido de GET produz 405 e 200 sem perder fronteira. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `RawClient`, `connection.send`, `self.assertEqual`, `request`, `connection.read_response` |

##### `StreamTests.test_head_then_get`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.test_head_then_get(self) -> None` |
| O que faz | Pipeline HEAD/GET confirma que HEAD não injeta corpo na próxima resposta. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `RawClient`, `connection.send`, `self.assertEqual`, `request`, `connection.read_response` |

##### `StreamTests.test_sequential_persistent_connection`

| Campo | Descrição |
|---|---|
| Assinatura | `StreamTests.test_sequential_persistent_connection(self) -> None` |
| O que faz | Dez pedidos sequenciais no mesmo socket retornam 200 e keep-alive. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `RawClient`, `range`, `connection.send`, `self.assertEqual`, `request`, `connection.read_response` |

### tests/concurrency_test.py

##### `fetch`

| Campo | Descrição |
|---|---|
| Assinatura | `fetch(host: str, port: int) -> int` |
| O que faz | Faz um GET concorrente e devolve bytes do corpo. |
| Como faz | Abre cliente, envia Connection close, exige 200 e retorna len. |
| Erros/conexão | AssertionError se não 200; OSError em falha de rede. |
| Quem chama | Workers do ThreadPoolExecutor em run. |
| Por quê | Cada cliente tem conexão real independente. |
| Quem chama internamente | `RawClient`, `connection.send`, `connection.read_response`, `len`, `request`, `AssertionError` |

##### `run`

| Campo | Descrição |
|---|---|
| Assinatura | `run(host: str, port: int, clients: int=10) -> None` |
| O que faz | Prova atendimento enquanto outro pedido está incompleto. |
| Como faz | Envia metade de header; executa N clientes paralelos; só depois completa lento e exige 200; imprime tempo/bytes. |
| Erros/conexão | Asserção ou erro de rede interrompe; with fecha os sockets. |
| Quem chama | main e teste local de concorrência. |
| Por quê | Confirma sobreposição sem depender somente de logs ou sleeps longos. |
| Quem chama internamente | `time.perf_counter`, `print`, `RawClient`, `slow.send`, `ThreadPoolExecutor`, `list`, `AssertionError`, `pool.map`, `slow.read_response`, `sum`, `range`, `fetch` |

##### `main`

| Campo | Descrição |
|---|---|
| Assinatura | `main() -> None` |
| O que faz | Configura teste concorrente pela CLI. |
| Como faz | Lê host/porta/--clients, exige clients positivo e executa run. |
| Erros/conexão | Argparse 2 para parâmetros; erro/asserção produz FAIL e saída 1. |
| Quem chama | Bloco principal do script. |
| Por quê | Teste repetível com carga escolhida pelo grupo. |
| Quem chama internamente | `argparse.ArgumentParser`, `parser.add_argument`, `parser.parse_args`, `parser.error`, `run`, `parser.exit` |

### tests/benchmark.py

##### `read_response`

| Campo | Descrição |
|---|---|
| Assinatura | `read_response(sock: socket.socket, buffer: bytes) -> tuple` |
| O que faz | Consome uma resposta 200 e devolve buffer residual/tamanho do corpo. |
| Como faz | Delimita head, valida status e Content-Length, rejeita Transfer-Encoding; descarta corpo em blocos. |
| Erros/conexão | ValueError em EOF, tamanho inválido ou resposta incompatível; OSError de rede. |
| Quem chama | benchmark.run. |
| Por quê | A medição deve esperar o corpo inteiro sem guardar arquivo grande. |
| Quem chama internamente | `buffer.split`, `head.decode('iso-8859-1').split`, `dict`, `int`, `sock.recv`, `ValueError`, `min`, `len`, `head.decode`, `lines[0].split`, `name.lower`, `value.strip`, `line.split` |

##### `run`

| Campo | Descrição |
|---|---|
| Assinatura | `run(host: str, port: int, path: str='/test.txt', requests: int=10, mode: str='c1') -> dict` |
| O que faz | Executa N pedidos sequenciais no modo escolhido. |
| Como faz | C1 abre/fecha por pedido; C2 mantém socket e fecha no último; lê cada corpo antes do próximo; mede perf_counter e devolve métricas. |
| Erros/conexão | Erros propagam após close no finally; pressupõe argumentos validados por main. |
| Quem chama | benchmark.main e suíte integrada. |
| Por quê | Isola a diferença de número de conexões mantendo caminho e quantidade. |
| Quem chama internamente | `time.perf_counter`, `print`, `range`, `f'GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: {connection}\r\n\r\n'.encode`, `sock.sendall`, `read_response`, `sock.close`, `socket.create_connection`, `mode.upper`, `sock.recv`, `ValueError` |

##### `main`

| Campo | Descrição |
|---|---|
| Assinatura | `main() -> None` |
| O que faz | Lê CLI do benchmark e valida parâmetros. |
| Como faz | Exige host/porta/mode, requests positivo e path ASCII seguro; executa run. |
| Erros/conexão | Argparse 2 no uso inválido; ValueError/OSError gera saída 1. |
| Quem chama | Bloco principal do benchmark. |
| Por quê | Evita medir silenciosamente respostas de erro ou caminho incorreto. |
| Quem chama internamente | `argparse.ArgumentParser`, `parser.add_argument`, `parser.parse_args`, `parser.error`, `any`, `run`, `args.path.startswith`, `parser.exit`, `ord` |

### tests/run_all.py

O bloco principal cria diretório temporário, copia www, adiciona large.bin, inicia HttpServer em thread com bind 0.0.0.0/porta 0 e timeout 0,7 s. Aguarda inicialização, executa HttpTests/StreamTests/LocalTests e, no finally, encerra servidor e aguarda thread. Verifica que nenhum worker sobrou e retorna exit code 0/1. Não é uma função separada.

#### LocalTests

TestCase adicional com fixtures criadas por run_all.py; executado junto dos testes remotos contra servidor temporário.

##### `LocalTests.test_symlinks_and_prefix`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.test_symlinks_and_prefix(self) -> None` |
| O que faz | Cria root e diretório irmão temporários; verifica symlink externo de pasta/index e prefixo semelhante. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `tempfile.TemporaryDirectory`, `root.mkdir`, `outside.mkdir`, `(outside / 'secret.txt').write_text`, `FileResolver`, `Path`, `(root / 'link').symlink_to`, `(root / 'index.html').symlink_to`, `str`, `self.skipTest`, `self.subTest`, `self.assertRaises`, `resolver.resolve` |

##### `LocalTests.test_idle_and_incomplete_timeout`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.test_idle_and_incomplete_timeout(self) -> None` |
| O que faz | Testa silêncio, cabeçalho parcial e corpo parcial; espera EOF pelo timeout de 0,7 s. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `client.RawClient`, `conn.send`, `self.assertEqual`, `conn.sock.recv` |

##### `LocalTests.test_large_file`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.test_large_file(self) -> None` |
| O que faz | Compara todos os bytes de binário de 2 MiB e MIME genérico após streaming. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `bytes`, `client.RawClient`, `conn.send`, `conn.read_response`, `self.assertEqual`, `range`, `client.request` |

##### `LocalTests.test_all_mime_types`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.test_all_mime_types(self) -> None` |
| O que faz | Verifica as 12 extensões da tabela pelo MIME esperado. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `self.assertTrue`, `guess_content_type('x.' + ext).startswith`, `guess_content_type` |

##### `LocalTests.test_head_malformed_no_body`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.test_head_malformed_no_body(self) -> None` |
| O que faz | HEAD com header sem dois-pontos produz 400, sem corpo e com EOF. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `client.RawClient`, `conn.send`, `self.assertEqual`, `conn.sock.recv`, `conn.read_response` |

##### `LocalTests.test_head_oversized_no_body`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.test_head_oversized_no_body(self) -> None` |
| O que faz | HEAD com header acima de 16 KiB retorna 400 e tamanho hipotético positivo, mas nenhum byte de corpo. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `client.RawClient`, `conn.send`, `conn.read_response`, `self.assertEqual`, `self.assertGreater`, `int`, `conn.sock.recv` |

##### `LocalTests.test_concurrent_slow_client`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.test_concurrent_slow_client(self) -> None` |
| O que faz | Executa 12 clientes enquanto outro está incompleto e depois conclui o lento. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `concurrency` |

##### `LocalTests.test_benchmarks`

| Campo | Descrição |
|---|---|
| Assinatura | `LocalTests.test_benchmarks(self) -> None` |
| O que faz | Executa C1 e C2 com dez pedidos; compara conexões 10/1 e bytes HTTP iguais. |
| Como faz | Envia/verifica casos pelo cliente de sockets ou fixtures locais; valores esperados são independentes do servidor. |
| Erros/conexão | AssertionError indica falha; OSError indica erro de ambiente/rede. No teste de symlink, skip se o SO negar criação. |
| Quem chama | unittest via run_suite; loader padrão reconhece os métodos test_.... |
| Por quê | Detecta regressão no comportamento externo especificado, não só na estrutura do código. |
| Quem chama internamente | `benchmark`, `self.assertEqual` |

**Inventário:** 72 funções/métodos escritos no projeto descritos acima; nenhum omitido. Os métodos especiais e os construtores gerados por dataclass estão descritos junto às respectivas classes.


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
`read_request` retira somente A; depois retira B e C nas próximas voltas do loop.
As respostas são serializadas na ordem dos pedidos da mesma conexão.

**Inteira mais parte da próxima:** um recv traz `[A completo][GET /B HT]`.
O parser entrega A e guarda `GET /B HT`. Depois junta novos bytes até completar B.

```python
end = self.buffer.find(b'\r\n\r\n')
(head, self.buffer) = (
    self.buffer[:end], self.buffer[end + 4:]
)
```

Com Content-Length, `read_body(n)` tira exatamente n bytes antes de devolver a
requisição. Por exemplo, POST com cinco bytes seguido de GET não confunde `abcde`
com uma nova request line. O servidor responde 405 ao POST e pode processar o GET.
O limite de headers se aplica à mensagem atual, não à soma de pedidos completos no buffer.
`recv(4096)` não garante receber 4096 bytes, e `sendall` não garante uma trama por chamada.

## 7. Segurança

`FileResolver.resolve` executa, nesta ordem:

1. Verifica sequências `%XX` e decodifica uma vez como UTF-8, de forma estrita.
2. Rejeita NUL, barra invertida e `:`; exige caminho iniciado por `/`.
3. Remove barras iniciais para juntar o caminho à raiz, sem trocar o drive.
4. Usa `realpath` para normalizar componentes e resolver links simbólicos.
5. Usa `commonpath` para confirmar a raiz inteira; prefixos de texto não bastam.
6. Se for diretório, junta `index.html` e repete a verificação de contenção.
7. Só permite arquivo regular existente; o handler abre e verifica novamente o tipo por fstat.

```python
resolved = os.path.realpath(path)
inside = os.path.commonpath([self.root, resolved]) == self.root
if not inside:
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

`_keep_alive` interpreta Connection como lista de tokens sem distinguir maiúsculas.
Close tem prioridade. HTTP/1.1 persiste por padrão; HTTP/1.0 exige keep-alive.
O timeout é entre novos bytes, inclusive durante uma mensagem. Um cliente que envia
um byte antes de cada timeout pode continuar conectado; não existe deadline total
de requisição nem limite global de threads. Isso é uma limitação de escala do laboratório.

```python
self.sock.shutdown(socket.SHUT_WR)
deadline = time.monotonic() + 0.2
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

1. **Por que recv não entrega uma requisição pronta?** TCP é fluxo; `RequestReader.read_request` acumula e delimita por CRLF CRLF.
2. **Onde fica o começo do próximo pedido?** Em `buffer`, preservado por `read_request` e `read_body`.
3. **Como HEAD evita corpo?** `RequestHandler.handle` marca `head_only`; `HttpResponse.body_bytes` retorna sem produzir bytes.
4. **Por que o tamanho de HEAD não é zero?** Content-Length descreve o corpo que GET enviaria; é calculado por fstat ou pelo erro HTML.
5. **Por que Host é necessário?** Identifica a autoridade HTTP/1.1; `_parse_head` rejeita ausência e `_parse_headers` rejeita duplicação.
6. **Por que commonpath e não startswith?** `FileResolver._inside_root` compara componentes e não confunde www com www-secret.
7. **Por que decodificar primeiro?** `%2e%2e` precisa virar `..` antes de validar o destino em `resolve`.
8. **Como symlinks são tratados?** realpath revela o destino, inclusive do index, e commonpath verifica a raiz.
9. **O que acontece com POST com corpo?** `read_body` consome Content-Length e `handle` retorna 405 com Allow.
10. **Por que fechar depois de 400?** Framing pode ser inválido; `ConnectionHandler.run` não reutiliza o fluxo ambíguo.
11. **Como a conexão permanece aberta?** `run` volta ao mesmo reader enquanto `_keep_alive` permitir.
12. **Close e keep-alive juntos: quem vence?** Close, conforme `_keep_alive`.
13. **Por que uma thread por conexão?** `_accept_loop` continua aceitando enquanto outra thread espera I/O; é simples para o laboratório.
14. **O GIL impede esse teste?** A espera por I/O permite outras threads progredirem; a carga é majoritariamente rede/arquivo.
15. **O timeout mede duração total?** Não; `settimeout` limita cada espera sem bytes. `_recv_more` converte a exceção em IdleTimeout.
16. **Como um arquivo grande não ocupa toda a RAM?** `body_bytes` lê blocos de até 65536 bytes e `send` envia cada bloco.
17. **Por que shutdown antes de close?** `close` sinaliza fim do envio e drena dados pendentes por tempo limitado.
18. **Date depende do idioma do Windows?** Não; `format_http_date` usa email.utils com UTC e usegmt=True.
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
