"""Cliente de teste independente: HTTP delimitado à mão sobre sockets."""
import argparse
import socket
import unittest
HOST = '127.0.0.1'
PORT = 8080

class RawClient:

    def __init__(self, host: str, port: int, timeout: float=4.0) -> None:
        self.sock = socket.create_connection((host, port), timeout)
        self.buffer = b''

    def send(self, data: bytes) -> None:
        self.sock.sendall(data)

    def read_response(self, head_only: bool=False) -> tuple:
        while b'\r\n\r\n' not in self.buffer:
            self._receive()
        (head, self.buffer) = self.buffer.split(b'\r\n\r\n', 1)
        lines = head.decode('iso-8859-1').split('\r\n')
        (version, status, reason) = lines[0].split(' ', 2)
        if version != 'HTTP/1.1':
            raise AssertionError('Versão de resposta inesperada')
        headers = {}
        for line in lines[1:]:
            (name, value) = line.split(':', 1)
            if name.lower() in headers:
                raise AssertionError('Cabeçalho de resposta repetido')
            headers[name.lower()] = value.strip()
        length = 0 if head_only else int(headers['content-length'])
        while len(self.buffer) < length:
            self._receive()
        (body, self.buffer) = (self.buffer[:length], self.buffer[length:])
        return (int(status), headers, body)

    def _receive(self) -> None:
        data = self.sock.recv(65536)
        if not data:
            raise AssertionError('Conexão fechada antes de completar a resposta')
        self.buffer += data

    def close(self) -> None:
        self.sock.close()

    def __enter__(self) -> "RawClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

def request(path: str='/test.txt', method: str='GET', connection: str='keep-alive', version: str='HTTP/1.1') -> bytes:
    return f'{method} {path} {version}\r\nHost: laboratorio\r\nConnection: {connection}\r\n\r\n'.encode('ascii')

def exchange(data: bytes, head_only: bool=False) -> tuple:
    with RawClient(HOST, PORT) as client:
        client.send(data)
        return client.read_response(head_only)

def run_suite(suite: unittest.TestSuite) -> bool:
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"{('PASS' if result.wasSuccessful() else 'FAIL')}: {result.testsRun} testes; falhas={len(result.failures)}, erros={len(result.errors)}")
    return result.wasSuccessful()

def remote_main(case: type) -> None:
    global HOST, PORT
    parser = argparse.ArgumentParser(description='Testes HTTP por sockets crus')
    parser.add_argument('host', nargs='?', default=HOST)
    parser.add_argument('port', nargs='?', type=int, default=PORT)
    args = parser.parse_args()
    (HOST, PORT) = (args.host, args.port)
    raise SystemExit(0 if run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(case)) else 1)
