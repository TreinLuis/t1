"""Uma thread executa este ciclo para cada conexão TCP aceita."""
from dataclasses import dataclass
import logging
import socket
import time
from http_parser import ConnectionClosedByPeer, HttpParseError, HttpRequest, IdleTimeout, RequestReader
from http_response import HttpResponse, format_http_date
from request_handler import RequestHandler

@dataclass(frozen=True)
class ConnectionConfig:
    handler: RequestHandler
    idle_timeout: float
    server_name: str

class ConnectionHandler:

    def __init__(self, sock: socket.socket, addr: tuple, config: ConnectionConfig) -> None:
        self.sock = sock
        self.addr = addr
        self.config = config
        self.reader = RequestReader(sock, 16384)

    def run(self) -> None:
        try:
            self.sock.settimeout(self.config.idle_timeout)
            while True:
                request = None
                try:
                    request = self.reader.read_request()
                    response = self.config.handler.handle(request)
                    keep_alive = self._keep_alive(request)
                except HttpParseError as error:
                    response = HttpResponse.error(error.status)
                    response.head_only = error.head_only
                    keep_alive = False
                    logging.debug('Requisição rejeitada de %s:%s: %s', *self.addr, error)
                except (IdleTimeout, ConnectionClosedByPeer):
                    break
                response.headers.update({'Date': format_http_date(), 'Server': self.config.server_name, 'Connection': 'keep-alive' if keep_alive else 'close'})
                sent = self.send(response)
                logging.info('cliente=%s:%s método=%s caminho=%r status=%s bytes=%s', *self.addr, request.method if request else '-', request.path if request else '-', response.status, sent)
                if not keep_alive:
                    break
        except OSError as error:
            logging.debug('Conexão interrompida %s:%s: %s', *self.addr, error)
        finally:
            self.close()

    def _keep_alive(self, request: HttpRequest) -> bool:
        tokens = {token.strip().lower() for token in request.header('connection').split(',')}
        if 'close' in tokens:
            return False
        return request.version != 'HTTP/1.0' or 'keep-alive' in tokens

    def send(self, response: HttpResponse) -> int:
        sent = 0
        try:
            head = response.to_head_bytes()
            self.sock.sendall(head)
            sent += len(head)
            for chunk in response.body_bytes():
                self.sock.sendall(chunk)
                sent += len(chunk)
            return sent
        finally:
            response.close()

    def close(self) -> None:
        try:
            # Primeiro envia FIN; drenar evita descartar a resposta com um RST prematuro.
            self.sock.shutdown(socket.SHUT_WR)
            # Limite total: o cliente não consegue prolongar a drenagem indefinidamente.
            deadline = time.monotonic() + 0.2
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.sock.settimeout(remaining)
                if not self.sock.recv(4096):
                    break
        except OSError:
            pass
        finally:
            self.sock.close()
