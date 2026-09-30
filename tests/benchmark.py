"""Mede C1/C2 com TCP cru. Execute de outra máquina para o relatório."""
import argparse as argparse_a
import socket as socket_a
import time as time_a

def i_read_response(sock_a: socket_a.socket, buffer_a: bytes) -> tuple:
    while b'\r\n\r\n' not in buffer_a:
        data_a = sock_a.recv(65536)
        if not data_a:
            raise ValueError('EOF antes dos cabeçalhos')
        buffer_a += data_a
        if len(buffer_a) > 131072:
            raise ValueError('Cabeçalho de resposta muito grande')
    (head_a, buffer_a) = buffer_a.split(b'\r\n\r\n', 1)
    lines_a = head_a.decode('iso-8859-1').split('\r\n')
    if lines_a[0].split(' ')[1] != '200':
        raise ValueError(f'Esperado 200, recebido: {lines_a[0]}')
    headers_a = dict(((name_a.lower(), value_a.strip()) for (name_a, value_a) in (line_a.split(':', 1) for line_a in lines_a[1:])))
    if 'transfer-encoding' in headers_a:
        raise ValueError('Benchmark requer Content-Length, sem Transfer-Encoding')
    length_a = int(headers_a['content-length'])
    if length_a < 0:
        raise ValueError('Content-Length negativo')
    # Descartar o corpo em blocos mantém o consumo de memória limitado.
    remaining_a = length_a
    while remaining_a:
        consumed_a = min(remaining_a, len(buffer_a))
        (buffer_a, remaining_a) = (buffer_a[consumed_a:], remaining_a - consumed_a)
        if remaining_a:
            buffer_a = sock_a.recv(65536)
            if not buffer_a:
                raise ValueError('EOF antes do corpo completo')
    return (buffer_a, length_a)

def i_run(host_a: str, port_a: int, path_a: str='/test.txt', requests_a: int=10, mode_a: str='c1') -> dict:
    sock_a = None
    buffer_a = b''
    total_bytes_a = 0
    connections_a = 0
    start_a = time_a.perf_counter()
    try:
        for index_a in range(requests_a):
            if sock_a is None:
                sock_a = socket_a.create_connection((host_a, port_a), timeout=10)
                connections_a += 1
            connection_a = 'close' if mode_a == 'c1' or index_a == requests_a - 1 else 'keep-alive'
            data_a = f'GET {path_a} HTTP/1.1\r\nHost: {host_a}:{port_a}\r\nConnection: {connection_a}\r\n\r\n'.encode('ascii')
            sock_a.sendall(data_a)
            (buffer_a, length_a) = i_read_response(sock_a, buffer_a)
            total_bytes_a += length_a
            if connection_a == 'close':
                if buffer_a or sock_a.recv(1):
                    raise ValueError('Bytes inesperados após o corpo')
                sock_a.close()
                sock_a = None
    finally:
        if sock_a is not None:
            sock_a.close()
    elapsed_a = time_a.perf_counter() - start_a
    result_a = {'mode': mode_a, 'requests': requests_a, 'connections': connections_a, 'body_bytes': total_bytes_a, 'seconds': elapsed_a}
    print(f'Modo: {mode_a.upper()} | requisições: {requests_a} | conexões: {connections_a}')
    print(f'Tempo total: {elapsed_a:.6f} s | por requisição: {elapsed_a / requests_a:.6f} s')
    print(f'Bytes de corpos HTTP: {total_bytes_a} (bytes de rede devem ser extraídos da captura)')
    return result_a

def i_main() -> None:
    parser_a = argparse_a.ArgumentParser(description=__doc__)
    parser_a.add_argument('host')
    parser_a.add_argument('port', type=int)
    parser_a.add_argument('--path', default='/test.txt')
    parser_a.add_argument('--requests', type=int, default=10)
    parser_a.add_argument('--mode', required=True, choices=('c1', 'c2'))
    args_a = parser_a.parse_args()
    if args_a.requests < 1 or not 1024 < args_a.port <= 65535:
        parser_a.error('Use --requests positivo e porta entre 1025 e 65535')
    if not args_a.path.startswith('/') or any((ord(char_a) <= 32 or ord(char_a) >= 127 for char_a in args_a.path)):
        parser_a.error('--path deve começar por / e usar percent-encoding para espaços e acentos')
    try:
        i_run(args_a.host, args_a.port, args_a.path, args_a.requests, args_a.mode)
    except (OSError, ValueError) as error_a:
        parser_a.exit(1, f'Falha na medição: {error_a}\n')
if __name__ == '__main__':
    i_main()
