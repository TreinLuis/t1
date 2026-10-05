"""Parsing HTTP manual: fronteiras de mensagens não são fronteiras de recv()."""
from dataclasses import dataclass, field
import re
import socket
TOKEN = re.compile("^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
MAX_BODY_BYTES = 1024 * 1024

@dataclass
class HttpRequest:
    method: str
    target: str
    path: str
    query: str
    version: str
    headers: dict = field(default_factory=dict)
    body: bytes = b''

    def header(self, name: str) -> str:
        return self.headers.get(name.lower(), '')

class HttpParseError(Exception):

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.head_only = False

class IdleTimeout(Exception):
    """Nenhum dado novo chegou dentro do timeout do socket."""

class ConnectionClosedByPeer(Exception):
    """recv() retornou EOF; pode haver uma requisição incompleta."""

class RequestReader:

    def __init__(self, sock: socket.socket, max_header_bytes: int=16384) -> None:
        self.sock = sock
        self.max_header_bytes = max_header_bytes
        self.buffer = b''

    def read_request(self) -> HttpRequest:
        while True:
            end = self.buffer.find(b'\r\n\r\n')
            if ((end >= 0 and end + 4 > self.max_header_bytes)
                    or (end < 0 and len(self.buffer) >= self.max_header_bytes)):
                error = HttpParseError(400, 'Cabeçalhos excedem o limite')
                error.head_only = self.buffer.startswith(b'HEAD ')
                raise error
            if end >= 0:
                # O excedente pode conter o corpo ou a próxima requisição, nunca descartá-lo.
                (head, self.buffer) = (self.buffer[:end], self.buffer[end + 4:])
                request = self._parse_head(head)
                request.body = self.read_body(int(request.header('content-length') or '0'))
                return request
            self._recv_more()

    def read_body(self, n: int) -> bytes:
        if not 0 <= n <= MAX_BODY_BYTES:
            raise HttpParseError(400, 'Corpo excede o limite de 1 MiB')
        while len(self.buffer) < n:
            self._recv_more()
        (body, self.buffer) = (self.buffer[:n], self.buffer[n:])
        return body

    def _recv_more(self) -> None:
        try:
            data = self.sock.recv(4096)
        except socket.timeout as error:
            raise IdleTimeout() from error
        if not data:
            raise ConnectionClosedByPeer()
        self.buffer += data

    def _parse_head(self, data: bytes) -> HttpRequest:
        lines = data.decode('iso-8859-1').split('\r\n')
        try:
            (method, target, version) = self._parse_request_line(lines[0])
            headers = self._parse_headers(lines[1:])
            if version != 'HTTP/1.0' and (not headers.get('host')):
                raise HttpParseError(400, 'HTTP/1.1 exige Host')
            # Sem dois enquadramentos concorrentes: corpo não pode virar outra request line.
            if 'transfer-encoding' in headers:
                raise HttpParseError(400, 'Transfer-Encoding não é suportado')
            length = headers.get('content-length', '0')
            if not re.fullmatch('[0-9]+', length) or len(length) > 10:
                raise HttpParseError(400, 'Content-Length inválido')
            if int(length) > MAX_BODY_BYTES:
                raise HttpParseError(400, 'Corpo excede o limite de 1 MiB')
            if 'expect' in headers:
                raise HttpParseError(417, 'Expect não é suportado')
            (path, separator, query) = target.partition('?')
            return HttpRequest(method, target, path, query, version, headers)
        except HttpParseError as error:
            error.head_only = lines[0].startswith('HEAD ')
            raise

    def _parse_request_line(self, line: str) -> tuple:
        parts = line.split(' ')
        if len(parts) != 3 or not all(parts):
            raise HttpParseError(400, 'Linha de requisição inválida')
        (method, target, version) = parts
        if not TOKEN.fullmatch(method):
            raise HttpParseError(400, 'Método inválido')
        if any((ord(char) <= 32 or ord(char) >= 127 for char in target)) or '#' in target:
            raise HttpParseError(400, 'Request-target inválido; utilize percent-encoding')
        if not re.fullmatch('HTTP/[0-9]\\.[0-9]', version):
            raise HttpParseError(400, 'Versão HTTP malformada')
        if version[5] != '1':
            raise HttpParseError(505, 'Versão principal HTTP não suportada')
        if method in ('GET', 'HEAD') and (not target.startswith('/')):
            raise HttpParseError(400, 'Esperado caminho iniciado por /')
        return (method, target, version)

    def _parse_headers(self, lines: list) -> dict:
        headers = {}
        for line in lines:
            if ':' not in line:
                raise HttpParseError(400, 'Cabeçalho sem dois-pontos')
            (name, value) = line.split(':', 1)
            if not TOKEN.fullmatch(name):
                raise HttpParseError(400, 'Nome de cabeçalho inválido')
            name = name.lower()
            value = value.strip(' \t')
            if any((ord(char) < 32 and char != '\t' or ord(char) == 127 for char in value)):
                raise HttpParseError(400, 'Controle inválido no cabeçalho')
            if name in headers:
                if name in ('host', 'content-length', 'transfer-encoding'):
                    raise HttpParseError(400, 'Cabeçalho de enquadramento repetido')
                value = headers[name] + ', ' + value
            if name == 'host' and (not value or any((char in value for char in ' ,/\\\t'))):
                raise HttpParseError(400, 'Host inválido')
            headers[name] = value
        return headers
