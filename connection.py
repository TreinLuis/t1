"""Uma thread executa este ciclo para cada conexão TCP aceita."""
from dataclasses import dataclass as i_dataclass
import logging as logging_a
import socket as socket_a
import time as time_a
from http_parser import ConnectionClosedByPeer, HttpParseError, HttpRequest, IdleTimeout, RequestReader
from http_response import HttpResponse, i_format_http_date
from request_handler import RequestHandler

@i_dataclass(frozen=True)
class ConnectionConfig:
    handler_a: RequestHandler
    idle_timeout_a: float
    server_name_a: str

class ConnectionHandler:

    def i_init(self_a, sock_a: socket_a.socket, addr_a: tuple, config_a: ConnectionConfig) -> None:
        self_a.sock_a = sock_a
        self_a.addr_a = addr_a
        self_a.config_a = config_a
        self_a.reader_a = RequestReader(sock_a, 16384)

    # Associação ao protocolo nativo do Python.
    __init__ = i_init

    def i_run(self_a) -> None:
        try:
            self_a.sock_a.settimeout(self_a.config_a.idle_timeout_a)
            while True:
                request_a = None
                try:
                    request_a = self_a.reader_a.i_read_request()
                    response_a = self_a.config_a.handler_a.i_handle(request_a)
                    keep_alive_a = self_a.i_keep_alive(request_a)
                except HttpParseError as error_a:
                    response_a = HttpResponse.i_error(error_a.status_a)
                    response_a.head_only_a = error_a.head_only_a
                    keep_alive_a = False
                    logging_a.debug('Requisição rejeitada de %s:%s: %s', *self_a.addr_a, error_a)
                except (IdleTimeout, ConnectionClosedByPeer):
                    break
                response_a.headers_a.update({'Date': i_format_http_date(), 'Server': self_a.config_a.server_name_a, 'Connection': 'keep-alive' if keep_alive_a else 'close'})
                sent_a = self_a.i_send(response_a)
                logging_a.info('cliente=%s:%s método=%s caminho=%r status=%s bytes=%s', *self_a.addr_a, request_a.method_a if request_a else '-', request_a.path_a if request_a else '-', response_a.status_a, sent_a)
                if not keep_alive_a:
                    break
        except OSError as error_a:
            logging_a.debug('Conexão interrompida %s:%s: %s', *self_a.addr_a, error_a)
        finally:
            self_a.i_close()

    def i_keep_alive(self_a, request_a: HttpRequest) -> bool:
        tokens_a = {token_a.strip().lower() for token_a in request_a.i_header('connection').split(',')}
        if 'close' in tokens_a:
            return False
        return request_a.version_a != 'HTTP/1.0' or 'keep-alive' in tokens_a

    def i_send(self_a, response_a: HttpResponse) -> int:
        sent_a = 0
        try:
            head_a = response_a.i_to_head_bytes()
            self_a.sock_a.sendall(head_a)
            sent_a += len(head_a)
            for chunk_a in response_a.i_body_bytes():
                self_a.sock_a.sendall(chunk_a)
                sent_a += len(chunk_a)
            return sent_a
        finally:
            response_a.i_close()

    def i_close(self_a) -> None:
        try:
            # Primeiro envia FIN; drenar evita descartar a resposta com um RST prematuro.
            self_a.sock_a.shutdown(socket_a.SHUT_WR)
            # Limite total: o cliente não consegue prolongar a drenagem indefinidamente.
            deadline_a = time_a.monotonic() + 0.2
            while True:
                remaining_a = deadline_a - time_a.monotonic()
                if remaining_a <= 0:
                    break
                self_a.sock_a.settimeout(remaining_a)
                if not self_a.sock_a.recv(4096):
                    break
        except OSError:
            pass
        finally:
            self_a.sock_a.close()
