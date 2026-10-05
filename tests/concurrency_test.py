"""Mantém um cliente incompleto enquanto N clientes fazem GET."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import time
from client import RawClient, request

def fetch(host: str, port: int) -> int:
    with RawClient(host, port) as connection:
        connection.send(request(connection='close'))
        (status, headers, body) = connection.read_response()
        if status != 200:
            raise AssertionError(f'GET simultâneo retornou {status}')
        return len(body)

def run(host: str, port: int, clients: int=10) -> None:
    start = time.perf_counter()
    with RawClient(host, port) as slow:
        slow.send(b'GET /test.txt HTTP/1.1\r\nHost:')
        with ThreadPoolExecutor(max_workers=clients) as pool:
            results = list(pool.map(lambda _: fetch(host, port), range(clients)))
        slow.send(b' laboratorio\r\nConnection: close\r\n\r\n')
        if slow.read_response()[0] != 200:
            raise AssertionError('Cliente lento não pôde completar a requisição')
    print(f'PASS: {clients} clientes atendidos com outro incompleto; {sum(results)} bytes; {time.perf_counter() - start:.4f} s')

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host', nargs='?', default='127.0.0.1')
    parser.add_argument('port', nargs='?', type=int, default=8080)
    parser.add_argument('--clients', type=int, default=10)
    args = parser.parse_args()
    if args.clients < 1:
        parser.error('--clients deve ser positivo')
    try:
        run(args.host, args.port, args.clients)
    except (OSError, AssertionError) as error:
        parser.exit(1, f'FAIL: {error}\n')
if __name__ == '__main__':
    main()
