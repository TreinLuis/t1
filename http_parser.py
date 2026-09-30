"""Parsing HTTP manual: fronteiras de mensagens não são fronteiras de recv()."""
from dataclasses import dataclass as i_dataclass, field as i_field
import re as re_a
import socket as socket_a
TOKEN_a = re_a.compile("^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
MAX_BODY_BYTES_a = 1024 * 1024

@i_dataclass
class HttpRequest:
    method_a: str
    target_a: str
    path_a: str
    query_a: str
    version_a: str
    headers_a: dict = i_field(default_factory=dict)
    body_a: bytes = b''

    def i_header(self_a, name_a: str) -> str:
        return self_a.headers_a.get(name_a.lower(), '')

class HttpParseError(Exception):

    def i_init(self_a, status_a: int, message_a: str) -> None:
        super().__init__(message_a)
        self_a.status_a = status_a
        self_a.head_only_a = False

    # Associação ao protocolo nativo do Python.
    __init__ = i_init

class IdleTimeout(Exception):
    """Nenhum dado novo chegou dentro do timeout do socket."""

class ConnectionClosedByPeer(Exception):
    """recv() retornou EOF; pode haver uma requisição incompleta."""

class RequestReader:

    def i_init(self_a, sock_a: socket_a.socket, max_header_bytes_a: int=16384) -> None:
        self_a.sock_a = sock_a
        self_a.max_header_bytes_a = max_header_bytes_a
        self_a.buffer_a = b''

    # Associação ao protocolo nativo do Python.
    __init__ = i_init

    def i_read_request(self_a) -> HttpRequest:
        while True:
            end_a = self_a.buffer_a.find(b'\r\n\r\n')
            if ((end_a >= 0 and end_a + 4 > self_a.max_header_bytes_a)
                    or (end_a < 0 and len(self_a.buffer_a) >= self_a.max_header_bytes_a)):
                error_a = HttpParseError(400, 'Cabeçalhos excedem o limite')
                error_a.head_only_a = self_a.buffer_a.startswith(b'HEAD ')
                raise error_a
            if end_a >= 0:
                # O excedente pode conter o corpo ou a próxima requisição, nunca descartá-lo.
                (head_a, self_a.buffer_a) = (self_a.buffer_a[:end_a], self_a.buffer_a[end_a + 4:])
                request_a = self_a.i_parse_head(head_a)
                request_a.body_a = self_a.i_read_body(int(request_a.i_header('content-length') or '0'))
                return request_a
            self_a.i_recv_more()

    def i_read_body(self_a, n_a: int) -> bytes:
        if not 0 <= n_a <= MAX_BODY_BYTES_a:
            raise HttpParseError(400, 'Corpo excede o limite de 1 MiB')
        while len(self_a.buffer_a) < n_a:
            self_a.i_recv_more()
        (body_a, self_a.buffer_a) = (self_a.buffer_a[:n_a], self_a.buffer_a[n_a:])
        return body_a

    def i_recv_more(self_a) -> None:
        try:
            data_a = self_a.sock_a.recv(4096)
        except socket_a.timeout as error_a:
            raise IdleTimeout() from error_a
        if not data_a:
            raise ConnectionClosedByPeer()
        self_a.buffer_a += data_a

    def i_parse_head(self_a, data_a: bytes) -> HttpRequest:
        lines_a = data_a.decode('iso-8859-1').split('\r\n')
        try:
            (method_a, target_a, version_a) = self_a.i_parse_request_line(lines_a[0])
            headers_a = self_a.i_parse_headers(lines_a[1:])
            if version_a != 'HTTP/1.0' and (not headers_a.get('host')):
                raise HttpParseError(400, 'HTTP/1.1 exige Host')
            # Sem dois enquadramentos concorrentes: corpo não pode virar outra request line.
            if 'transfer-encoding' in headers_a:
                raise HttpParseError(400, 'Transfer-Encoding não é suportado')
            length_a = headers_a.get('content-length', '0')
            if not re_a.fullmatch('[0-9]+', length_a) or len(length_a) > 10:
                raise HttpParseError(400, 'Content-Length inválido')
            if int(length_a) > MAX_BODY_BYTES_a:
                raise HttpParseError(400, 'Corpo excede o limite de 1 MiB')
            if 'expect' in headers_a:
                raise HttpParseError(417, 'Expect não é suportado')
            (path_a, separator_a, query_a) = target_a.partition('?')
            return HttpRequest(method_a, target_a, path_a, query_a, version_a, headers_a)
        except HttpParseError as error_a:
            error_a.head_only_a = lines_a[0].startswith('HEAD ')
            raise

    def i_parse_request_line(self_a, line_a: str) -> tuple:
        parts_a = line_a.split(' ')
        if len(parts_a) != 3 or not all(parts_a):
            raise HttpParseError(400, 'Linha de requisição inválida')
        (method_a, target_a, version_a) = parts_a
        if not TOKEN_a.fullmatch(method_a):
            raise HttpParseError(400, 'Método inválido')
        if any((ord(char_a) <= 32 or ord(char_a) >= 127 for char_a in target_a)) or '#' in target_a:
            raise HttpParseError(400, 'Request-target inválido; utilize percent-encoding')
        if not re_a.fullmatch('HTTP/[0-9]\\.[0-9]', version_a):
            raise HttpParseError(400, 'Versão HTTP malformada')
        if version_a[5] != '1':
            raise HttpParseError(505, 'Versão principal HTTP não suportada')
        if method_a in ('GET', 'HEAD') and (not target_a.startswith('/')):
            raise HttpParseError(400, 'Esperado caminho iniciado por /')
        return (method_a, target_a, version_a)

    def i_parse_headers(self_a, lines_a: list) -> dict:
        headers_a = {}
        for line_a in lines_a:
            if ':' not in line_a:
                raise HttpParseError(400, 'Cabeçalho sem dois-pontos')
            (name_a, value_a) = line_a.split(':', 1)
            if not TOKEN_a.fullmatch(name_a):
                raise HttpParseError(400, 'Nome de cabeçalho inválido')
            name_a = name_a.lower()
            value_a = value_a.strip(' \t')
            if any((ord(char_a) < 32 and char_a != '\t' or ord(char_a) == 127 for char_a in value_a)):
                raise HttpParseError(400, 'Controle inválido no cabeçalho')
            if name_a in headers_a:
                if name_a in ('host', 'content-length', 'transfer-encoding'):
                    raise HttpParseError(400, 'Cabeçalho de enquadramento repetido')
                value_a = headers_a[name_a] + ', ' + value_a
            if name_a == 'host' and (not value_a or any((char_a in value_a for char_a in ' ,/\\\t'))):
                raise HttpParseError(400, 'Host inválido')
            headers_a[name_a] = value_a
        return headers_a
