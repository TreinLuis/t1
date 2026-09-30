"""Servidor didático HTTP/1.1 diretamente sobre TCP, sem dependências externas."""
import argparse as argparse_a
import ipaddress as ipaddress_a
import logging as logging_a
import math as math_a
import socket as socket_a
import threading as threading_a
from connection import ConnectionConfig, ConnectionHandler
from file_resolver import FileResolver
from request_handler import RequestHandler

class HttpServer:

    def i_init(self_a, host_a: str, port_a: int, root_a: str, idle_timeout_a: float=5.0, server_name_a: str='Grupo-Redes-T1') -> None:
        if ipaddress_a.ip_address(socket_a.gethostbyname(host_a)).is_loopback:
            raise ValueError('Use 0.0.0.0 ou o IP da interface de rede para o bind')
        if not math_a.isfinite(idle_timeout_a) or idle_timeout_a <= 0:
            raise ValueError('O timeout deve ser finito e positivo')
        if not server_name_a or any((ord(char_a) < 32 or ord(char_a) > 126 for char_a in server_name_a)):
            raise ValueError('O identificador do grupo deve conter apenas ASCII imprimível')
        self_a.host_a = host_a
        self_a.port_a = port_a
        self_a.config_a = ConnectionConfig(RequestHandler(FileResolver(root_a), server_name_a), idle_timeout_a, server_name_a)
        self_a.sock_a = None
        self_a.stopping_a = threading_a.Event()
        self_a.lock_a = threading_a.Lock()
        self_a.connections_a = set()
        self_a.workers_a = set()

    # Associação ao protocolo nativo do Python.
    __init__ = i_init

    def i_start(self_a) -> None:
        self_a.sock_a = socket_a.socket(socket_a.AF_INET, socket_a.SOCK_STREAM)
        try:
            self_a.sock_a.setsockopt(socket_a.SOL_SOCKET, socket_a.SO_REUSEADDR, 1)
            self_a.sock_a.bind((self_a.host_a, self_a.port_a))
            self_a.port_a = self_a.sock_a.getsockname()[1]
            self_a.sock_a.listen(128)
            self_a.sock_a.settimeout(0.25)
            logging_a.info('Servidor em %s:%s; raiz=%s', self_a.host_a, self_a.port_a, self_a.config_a.handler_a.resolver_a.root_a)
            self_a.i_accept_loop()
        finally:
            self_a.i_shutdown()

    def i_accept_loop(self_a) -> None:
        while not self_a.stopping_a.is_set():
            try:
                (sock_a, addr_a) = self_a.sock_a.accept()
            except socket_a.timeout:
                continue
            except OSError:
                if self_a.stopping_a.is_set():
                    break
                raise
            worker_a = threading_a.Thread(target=self_a.i_serve_connection, args=(sock_a, addr_a), daemon=True)
            with self_a.lock_a:
                if self_a.stopping_a.is_set():
                    sock_a.close()
                    break
                self_a.connections_a.add(sock_a)
                self_a.workers_a.add(worker_a)
                worker_a.start()

    def i_serve_connection(self_a, sock_a: socket_a.socket, addr_a: tuple) -> None:
        try:
            ConnectionHandler(sock_a, addr_a, self_a.config_a).i_run()
        finally:
            with self_a.lock_a:
                self_a.connections_a.discard(sock_a)
                self_a.workers_a.discard(threading_a.current_thread())

    def i_shutdown(self_a) -> None:
        self_a.stopping_a.set()
        if self_a.sock_a is not None:
            self_a.sock_a.close()
        with self_a.lock_a:
            (connections_a, workers_a) = (list(self_a.connections_a), list(self_a.workers_a))
        # Acorda recv() bloqueado; cada thread fecha seu socket no finally.
        for sock_a in connections_a:
            try:
                sock_a.shutdown(socket_a.SHUT_RDWR)
            except OSError:
                pass
        for worker_a in workers_a:
            if worker_a is not threading_a.current_thread():
                worker_a.join(timeout=1.0)

def i_main() -> None:
    parser_a = argparse_a.ArgumentParser(description=__doc__)
    parser_a.add_argument('--port', type=int, required=True, help='porta TCP entre 1025 e 65535')
    parser_a.add_argument('--root', required=True, help='diretório raiz dos arquivos')
    parser_a.add_argument('--host', default='0.0.0.0', help='endereço de bind (padrão: 0.0.0.0)')
    parser_a.add_argument('--idle-timeout', type=float, default=5.0, help='timeout sem novos bytes em segundos')
    parser_a.add_argument('--server-name', default='Grupo-Redes-T1', help='identificador ASCII do grupo')
    parser_a.add_argument('--verbose', action='store_true', help='habilita detalhes de conexão e parsing')
    args_a = parser_a.parse_args()
    if not 1024 < args_a.port <= 65535:
        parser_a.error('--port deve estar entre 1025 e 65535')
    logging_a.basicConfig(level=logging_a.DEBUG if args_a.verbose else logging_a.INFO, format='%(asctime)s %(levelname)s [%(threadName)s] %(message)s')
    try:
        server_a = HttpServer(args_a.host, args_a.port, args_a.root, args_a.idle_timeout, args_a.server_name)
        server_a.i_start()
    except KeyboardInterrupt:
        logging_a.info('Servidor encerrado pelo usuário')
    except (OSError, ValueError) as error_a:
        parser_a.exit(1, f'Não foi possível iniciar o servidor: {error_a}\n')
if __name__ == '__main__':
    i_main()
