"""Conformidade observável no fio; execute contra a raiz www entregue."""
import unittest
import client
from client import RawClient, exchange, request

class HttpTests(unittest.TestCase):

    def test_get_and_required_headers(self) -> None:
        (status, headers, body) = exchange(request(connection='close'))
        self.assertEqual(status, 200)
        self.assertEqual(body, 'Arquivo de teste do Trabalho 1.\n'.encode())
        self.assertEqual(int(headers['content-length']), len(body))
        self.assertEqual(headers['content-type'], 'text/plain; charset=utf-8')
        self.assertTrue(headers['server'])
        self.assertEqual(headers['connection'], 'close')
        self.assertRegex(headers['date'], '^[A-Z][a-z]{2}, \\d{2} [A-Z][a-z]{2} \\d{4} \\d{2}:\\d{2}:\\d{2} GMT$')

    def test_head_same_headers_and_no_body(self) -> None:
        for path in ('/test.txt', '/inexistente', '/../../secret.txt'):
            with self.subTest(path=path):
                (get_status, get_headers, body) = exchange(request(path, connection='close'))
                with RawClient(client.HOST, client.PORT) as connection:
                    connection.send(request(path, 'HEAD', 'close'))
                    (status, headers, head_body) = connection.read_response(True)
                    self.assertEqual(status, get_status)
                    self.assertEqual(head_body, b'')
                    self.assertEqual(connection.buffer, b'')
                    self.assertEqual(connection.sock.recv(1), b'')
                    get_headers.pop('date')
                    headers.pop('date')
                    self.assertEqual(headers, get_headers)
                    self.assertEqual(int(headers['content-length']), len(body))

    def test_bad_requests_close(self) -> None:
        cases = [b'GET /\r\nHost: x\r\n\r\n', b'GET / HTTP/1.1\r\nInvalido\r\nHost: x\r\n\r\n', b'GET / HTTP/1.1\r\n\r\n', b'GET / HTTP/1.x\r\nHost: x\r\n\r\n', b'GET / HTTP/1.1\r\nHost: x\r\nHost: y\r\n\r\n', b'GET / HTTP/1.1\r\nHost : x\r\n\r\n', b'GET / HTTP/1.1\r\nHost: \r\n\r\n', b'GET / HTTP/1.1\r\nHost: x\r\nContent-Length: -1\r\n\r\n', b'GET / HTTP/1.1\r\nHost: x\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n', b'GET / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\nContent-Length: 0\r\n\r\n', b'GET / HTTP/1.1\r\nHost: x\r\nX: ' + b'a' * 17000 + b'\r\n\r\n']
        for data in cases:
            with self.subTest(data=data[:80]):
                with RawClient(client.HOST, client.PORT) as connection:
                    connection.send(data)
                    (status, headers, body) = connection.read_response()
                    self.assertEqual(status, 400)
                    self.assertEqual(headers['connection'], 'close')
                    self.assertEqual(int(headers['content-length']), len(body))
                    self.assertEqual(connection.sock.recv(1), b'')

    def test_traversal_vectors(self) -> None:
        for path in ('/../../Windows/System32/drivers/etc/hosts', '/%2e%2e/%2e%2e/secret.txt', '/assets/../../../secret.txt', '/%2e%2e%2f%2e%2e%2fsecret.txt', '/..%5c..%5csecret.txt', '/../www-secret/secret.txt', '/%00', '/C:/Windows/win.ini'):
            with self.subTest(path=path):
                self.assertEqual(exchange(request(path))[0], 403)

    def test_not_found_and_directory_index(self) -> None:
        self.assertEqual(exchange(request('/inexistente'))[0], 404)
        self.assertEqual(exchange(request('/sub/'))[0], 404)
        self.assertEqual(exchange(request('/'))[0], 200)
        self.assertEqual(exchange(request('/sub/pagina.html'))[0], 200)

    def test_method_not_allowed(self) -> None:
        (status, headers, body) = exchange(request(method='DELETE'))
        self.assertEqual(status, 405)
        self.assertEqual(headers['allow'], 'GET, HEAD')

    def test_query_percent_encoding_and_header_case(self) -> None:
        data = b'GET /test%2etxt?ignorado=sim HTTP/1.1\r\nhOsT:lab\r\ncOnNeCtIoN:close\r\n\r\n'
        self.assertEqual(exchange(data)[0], 200)

    def test_http_10_and_close_token(self) -> None:
        for data in (b'GET /test.txt HTTP/1.0\r\n\r\n', request(connection='keep-alive, CLOSE')):
            self.assertEqual(exchange(data)[1]['connection'], 'close')
        self.assertEqual(exchange(request(version='HTTP/1.0'))[1]['connection'], 'keep-alive')

    def test_binary_mime_and_version(self) -> None:
        (status, headers, body) = exchange(request('/imagem.svg'))
        self.assertEqual(status, 200)
        self.assertEqual(headers['content-type'], 'image/svg+xml; charset=utf-8')
        self.assertEqual(exchange(request(version='HTTP/2.0'))[0], 505)

    def test_expect_rejected_without_waiting_for_body(self) -> None:
        data = b'POST / HTTP/1.1\r\nHost: x\r\nExpect: 100-continue\r\nContent-Length: 9\r\n\r\n'
        self.assertEqual(exchange(data)[0], 417)
if __name__ == '__main__':
    client.remote_main(HttpTests)
