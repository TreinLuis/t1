"""Cliente de teste independente: HTTP delimitado à mão sobre sockets."""
import argparse as argparse_a
import socket as socket_a
import unittest as unittest_a
unittest_a.defaultTestLoader.testMethodPrefix = 'i_test_'
HOST_a = '127.0.0.1'
PORT_a = 8080

class RawClient:

    def i_init(self_a, host_a: str, port_a: int, timeout_a: float=4.0) -> None:
        self_a.sock_a = socket_a.create_connection((host_a, port_a), timeout_a)
        self_a.buffer_a = b''

    # Associação ao protocolo nativo do Python.
    __init__ = i_init

    def i_send(self_a, data_a: bytes) -> None:
        self_a.sock_a.sendall(data_a)

    def i_read_response(self_a, head_only_a: bool=False) -> tuple:
        while b'\r\n\r\n' not in self_a.buffer_a:
            self_a.i_receive()
        (head_a, self_a.buffer_a) = self_a.buffer_a.split(b'\r\n\r\n', 1)
        lines_a = head_a.decode('iso-8859-1').split('\r\n')
        (version_a, status_a, reason_a) = lines_a[0].split(' ', 2)
        if version_a != 'HTTP/1.1':
            raise AssertionError('Versão de resposta inesperada')
        headers_a = {}
        for line_a in lines_a[1:]:
            (name_a, value_a) = line_a.split(':', 1)
            if name_a.lower() in headers_a:
                raise AssertionError('Cabeçalho de resposta repetido')
            headers_a[name_a.lower()] = value_a.strip()
        length_a = 0 if head_only_a else int(headers_a['content-length'])
        while len(self_a.buffer_a) < length_a:
            self_a.i_receive()
        (body_a, self_a.buffer_a) = (self_a.buffer_a[:length_a], self_a.buffer_a[length_a:])
        return (int(status_a), headers_a, body_a)

    def i_receive(self_a) -> None:
        data_a = self_a.sock_a.recv(65536)
        if not data_a:
            raise AssertionError('Conexão fechada antes de completar a resposta')
        self_a.buffer_a += data_a

    def i_close(self_a) -> None:
        self_a.sock_a.close()

    def i_enter(self_a) -> "RawClient":
        return self_a

    # Associação ao protocolo nativo do Python.
    __enter__ = i_enter

    def i_exit(self_a, *args_a) -> None:
        self_a.i_close()

    # Associação ao protocolo nativo do Python.
    __exit__ = i_exit

def i_request(path_a: str='/test.txt', method_a: str='GET', connection_a: str='keep-alive', version_a: str='HTTP/1.1') -> bytes:
    return f'{method_a} {path_a} {version_a}\r\nHost: laboratorio\r\nConnection: {connection_a}\r\n\r\n'.encode('ascii')

def i_exchange(data_a: bytes, head_only_a: bool=False) -> tuple:
    with RawClient(HOST_a, PORT_a) as client_a:
        client_a.i_send(data_a)
        return client_a.i_read_response(head_only_a)

def i_run_suite(suite_a: unittest_a.TestSuite) -> bool:
    result_a = unittest_a.TextTestRunner(verbosity=2).run(suite_a)
    print(f"{('PASS' if result_a.wasSuccessful() else 'FAIL')}: {result_a.testsRun} testes; falhas={len(result_a.failures)}, erros={len(result_a.errors)}")
    return result_a.wasSuccessful()

def i_remote_main(case_a: type) -> None:
    global HOST_a, PORT_a
    parser_a = argparse_a.ArgumentParser(description='Testes HTTP por sockets crus')
    parser_a.add_argument('host', nargs='?', default=HOST_a)
    parser_a.add_argument('port', nargs='?', type=int, default=PORT_a)
    args_a = parser_a.parse_args()
    (HOST_a, PORT_a) = (args_a.host, args_a.port)
    raise SystemExit(0 if i_run_suite(unittest_a.defaultTestLoader.loadTestsFromTestCase(case_a)) else 1)
