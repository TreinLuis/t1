"""Mantém um cliente incompleto enquanto N clientes fazem GET."""
import argparse as argparse_a
from concurrent.futures import ThreadPoolExecutor
import time as time_a
from client import RawClient, i_request as i_request

def i_fetch(host_a: str, port_a: int) -> int:
    with RawClient(host_a, port_a) as connection_a:
        connection_a.i_send(i_request(connection_a='close'))
        (status_a, headers_a, body_a) = connection_a.i_read_response()
        if status_a != 200:
            raise AssertionError(f'GET simultâneo retornou {status_a}')
        return len(body_a)

def i_run(host_a: str, port_a: int, clients_a: int=10) -> None:
    start_a = time_a.perf_counter()
    with RawClient(host_a, port_a) as slow_a:
        slow_a.i_send(b'GET /test.txt HTTP/1.1\r\nHost:')
        with ThreadPoolExecutor(max_workers=clients_a) as pool_a:
            results_a = list(pool_a.map(lambda __a: i_fetch(host_a, port_a), range(clients_a)))
        slow_a.i_send(b' laboratorio\r\nConnection: close\r\n\r\n')
        if slow_a.i_read_response()[0] != 200:
            raise AssertionError('Cliente lento não pôde completar a requisição')
    print(f'PASS: {clients_a} clientes atendidos com outro incompleto; {sum(results_a)} bytes; {time_a.perf_counter() - start_a:.4f} s')

def i_main() -> None:
    parser_a = argparse_a.ArgumentParser(description=__doc__)
    parser_a.add_argument('host', nargs='?', default='127.0.0.1')
    parser_a.add_argument('port', nargs='?', type=int, default=8080)
    parser_a.add_argument('--clients', type=int, default=10)
    args_a = parser_a.parse_args()
    if args_a.clients < 1:
        parser_a.error('--clients deve ser positivo')
    try:
        i_run(args_a.host, args_a.port, args_a.clients)
    except (OSError, AssertionError) as error_a:
        parser_a.exit(1, f'FAIL: {error_a}\n')
if __name__ == '__main__':
    i_main()
