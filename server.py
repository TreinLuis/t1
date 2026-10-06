"""Servidor didático HTTP/1.1 diretamente sobre TCP, sem dependências externas."""
import argparse
import ipaddress
import logging
import math
import socket
import threading
from connection import ConnectionConfig, ConnectionHandler
from file_resolver import FileResolver
from request_handler import RequestHandler

class HttpServer:

    def __init__(self, host: str, port: int, root: str, idle_timeout: float=5.0, server_name: str='Grupo-Redes-T1') -> None:
        if ipaddress.ip_address(socket.gethostbyname(host)).is_loopback:
            raise ValueError('Use 0.0.0.0 ou o IP da interface de rede para o bind')
        if not math.isfinite(idle_timeout) or idle_timeout <= 0:
            raise ValueError('O timeout deve ser finito e positivo')
        if not server_name or any((ord(char) < 32 or ord(char) > 126 for char in server_name)):
            raise ValueError('O identificador do grupo deve conter apenas ASCII imprimível')
        self.host = host
        self.port = port
        self.config = ConnectionConfig(RequestHandler(FileResolver(root), server_name), idle_timeout, server_name)
        self.sock = None
        self.stopping = threading.Event()
        self.lock = threading.Lock()
        self.connections = set()
        self.workers = set()

    def start(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # bind escolhe interface/porta; listen habilita a espera por conexões.
            self.sock.bind((self.host, self.port))
            self.port = self.sock.getsockname()[1]
            self.sock.listen(128)
            self.sock.settimeout(0.25)
            logging.info('Servidor em %s:%s; raiz=%s', self.host, self.port, self.config.handler.resolver.root)
            self._accept_loop()
        finally:
            self.shutdown()

    def _accept_loop(self) -> None:
        while not self.stopping.is_set():
            try:
                (sock, addr) = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                if self.stopping.is_set():
                    break
                raise
            # Uma thread por conexão: um cliente lento não bloqueia os demais.
            worker = threading.Thread(target=self._serve_connection, args=(sock, addr), daemon=True)
            with self.lock:
                if self.stopping.is_set():
                    sock.close()
                    break
                self.connections.add(sock)
                self.workers.add(worker)
                worker.start()

    def _serve_connection(self, sock: socket.socket, addr: tuple) -> None:
        try:
            ConnectionHandler(sock, addr, self.config).run()
        finally:
            with self.lock:
                self.connections.discard(sock)
                self.workers.discard(threading.current_thread())

    def shutdown(self) -> None:
        self.stopping.set()
        if self.sock is not None:
            self.sock.close()
        with self.lock:
            (connections, workers) = (list(self.connections), list(self.workers))
        # Acorda recv() bloqueado; cada thread fecha seu socket no finally.
        for sock in connections:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=1.0)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True, help='porta TCP entre 1025 e 65535')
    parser.add_argument('--root', required=True, help='diretório raiz dos arquivos')
    parser.add_argument('--host', default='0.0.0.0', help='endereço de bind (padrão: 0.0.0.0)')
    parser.add_argument('--idle-timeout', type=float, default=5.0, help='timeout sem novos bytes em segundos')
    parser.add_argument('--server-name', default='Grupo-Redes-T1', help='identificador ASCII do grupo')
    parser.add_argument('--verbose', action='store_true', help='habilita detalhes de conexão e parsing')
    args = parser.parse_args()
    if not 1024 < args.port <= 65535:
        parser.error('--port deve estar entre 1025 e 65535')
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format='%(asctime)s %(levelname)s [%(threadName)s] %(message)s')
    try:
        server = HttpServer(args.host, args.port, args.root, args.idle_timeout, args.server_name)
        server.start()
    except KeyboardInterrupt:
        logging.info('Servidor encerrado pelo usuário')
    except (OSError, ValueError) as error:
        parser.exit(1, f'Não foi possível iniciar o servidor: {error}\n')
if __name__ == '__main__':
    main()
