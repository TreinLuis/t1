"""Mede C1/C2 com TCP cru. Execute de outra máquina para o relatório."""
import argparse
import socket
import time

def read_response(sock: socket.socket, buffer: bytes) -> tuple:
    while b'\r\n\r\n' not in buffer:
        data = sock.recv(65536)
        if not data:
            raise ValueError('EOF antes dos cabeçalhos')
        buffer += data
        if len(buffer) > 131072:
            raise ValueError('Cabeçalho de resposta muito grande')
    (head, buffer) = buffer.split(b'\r\n\r\n', 1)
    lines = head.decode('iso-8859-1').split('\r\n')
    if lines[0].split(' ')[1] != '200':
        raise ValueError(f'Esperado 200, recebido: {lines[0]}')
    headers = dict(((name.lower(), value.strip()) for (name, value) in (line.split(':', 1) for line in lines[1:])))
    if 'transfer-encoding' in headers:
        raise ValueError('Benchmark requer Content-Length, sem Transfer-Encoding')
    length = int(headers['content-length'])
    if length < 0:
        raise ValueError('Content-Length negativo')
    # Descartar o corpo em blocos mantém o consumo de memória limitado.
    remaining = length
    while remaining:
        consumed = min(remaining, len(buffer))
        (buffer, remaining) = (buffer[consumed:], remaining - consumed)
        if remaining:
            buffer = sock.recv(65536)
            if not buffer:
                raise ValueError('EOF antes do corpo completo')
    return (buffer, length)

def run(host: str, port: int, path: str='/test.txt', requests: int=10, mode: str='c1') -> dict:
    sock = None
    buffer = b''
    total_bytes = 0
    connections = 0
    start = time.perf_counter()
    try:
        for index in range(requests):
            if sock is None:
                sock = socket.create_connection((host, port), timeout=10)
                connections += 1
            connection = 'close' if mode == 'c1' or index == requests - 1 else 'keep-alive'
            data = f'GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: {connection}\r\n\r\n'.encode('ascii')
            sock.sendall(data)
            (buffer, length) = read_response(sock, buffer)
            total_bytes += length
            if connection == 'close':
                if buffer or sock.recv(1):
                    raise ValueError('Bytes inesperados após o corpo')
                sock.close()
                sock = None
    finally:
        if sock is not None:
            sock.close()
    elapsed = time.perf_counter() - start
    result = {'mode': mode, 'requests': requests, 'connections': connections, 'body_bytes': total_bytes, 'seconds': elapsed}
    print(f'Modo: {mode.upper()} | requisições: {requests} | conexões: {connections}')
    print(f'Tempo total: {elapsed:.6f} s | por requisição: {elapsed / requests:.6f} s')
    print(f'Bytes de corpos HTTP: {total_bytes} (bytes de rede devem ser extraídos da captura)')
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('port', type=int)
    parser.add_argument('--path', default='/test.txt')
    parser.add_argument('--requests', type=int, default=10)
    parser.add_argument('--mode', required=True, choices=('c1', 'c2'))
    args = parser.parse_args()
    if args.requests < 1 or not 1024 < args.port <= 65535:
        parser.error('Use --requests positivo e porta entre 1025 e 65535')
    if not args.path.startswith('/') or any((ord(char) <= 32 or ord(char) >= 127 for char in args.path)):
        parser.error('--path deve começar por / e usar percent-encoding para espaços e acentos')
    try:
        run(args.host, args.port, args.path, args.requests, args.mode)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Falha na medição: {error}\n')
if __name__ == '__main__':
    main()
