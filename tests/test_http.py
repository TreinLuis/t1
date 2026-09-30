"""Conformidade observável no fio; execute contra a raiz www entregue."""
import unittest as unittest_a
import client as client_a
from client import RawClient, i_exchange as i_exchange, i_request as i_request

class HttpTests(unittest_a.TestCase):

    def i_test_get_and_required_headers(self_a) -> None:
        (status_a, headers_a, body_a) = i_exchange(i_request(connection_a='close'))
        self_a.assertEqual(status_a, 200)
        self_a.assertEqual(body_a, 'Arquivo de teste do Trabalho 1.\n'.encode())
        self_a.assertEqual(int(headers_a['content-length']), len(body_a))
        self_a.assertEqual(headers_a['content-type'], 'text/plain; charset=utf-8')
        self_a.assertTrue(headers_a['server'])
        self_a.assertEqual(headers_a['connection'], 'close')
        self_a.assertRegex(headers_a['date'], '^[A-Z][a-z]{2}, \\d{2} [A-Z][a-z]{2} \\d{4} \\d{2}:\\d{2}:\\d{2} GMT$')

    def i_test_head_same_headers_and_no_body(self_a) -> None:
        for path_a in ('/test.txt', '/inexistente', '/../../secret.txt'):
            with self_a.subTest(path=path_a):
                (get_status_a, get_headers_a, body_a) = i_exchange(i_request(path_a, connection_a='close'))
                with RawClient(client_a.HOST_a, client_a.PORT_a) as connection_a:
                    connection_a.i_send(i_request(path_a, 'HEAD', 'close'))
                    (status_a, headers_a, head_body_a) = connection_a.i_read_response(True)
                    self_a.assertEqual(status_a, get_status_a)
                    self_a.assertEqual(head_body_a, b'')
                    self_a.assertEqual(connection_a.buffer_a, b'')
                    self_a.assertEqual(connection_a.sock_a.recv(1), b'')
                    get_headers_a.pop('date')
                    headers_a.pop('date')
                    self_a.assertEqual(headers_a, get_headers_a)
                    self_a.assertEqual(int(headers_a['content-length']), len(body_a))

    def i_test_bad_requests_close(self_a) -> None:
        cases_a = [b'GET /\r\nHost: x\r\n\r\n', b'GET / HTTP/1.1\r\nInvalido\r\nHost: x\r\n\r\n', b'GET / HTTP/1.1\r\n\r\n', b'GET / HTTP/1.x\r\nHost: x\r\n\r\n', b'GET / HTTP/1.1\r\nHost: x\r\nHost: y\r\n\r\n', b'GET / HTTP/1.1\r\nHost : x\r\n\r\n', b'GET / HTTP/1.1\r\nHost: \r\n\r\n', b'GET / HTTP/1.1\r\nHost: x\r\nContent-Length: -1\r\n\r\n', b'GET / HTTP/1.1\r\nHost: x\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n', b'GET / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\nContent-Length: 0\r\n\r\n', b'GET / HTTP/1.1\r\nHost: x\r\nX: ' + b'a' * 17000 + b'\r\n\r\n']
        for data_a in cases_a:
            with self_a.subTest(data=data_a[:80]):
                with RawClient(client_a.HOST_a, client_a.PORT_a) as connection_a:
                    connection_a.i_send(data_a)
                    (status_a, headers_a, body_a) = connection_a.i_read_response()
                    self_a.assertEqual(status_a, 400)
                    self_a.assertEqual(headers_a['connection'], 'close')
                    self_a.assertEqual(int(headers_a['content-length']), len(body_a))
                    self_a.assertEqual(connection_a.sock_a.recv(1), b'')

    def i_test_traversal_vectors(self_a) -> None:
        for path_a in ('/../../Windows/System32/drivers/etc/hosts', '/%2e%2e/%2e%2e/secret.txt', '/assets/../../../secret.txt', '/%2e%2e%2f%2e%2e%2fsecret.txt', '/..%5c..%5csecret.txt', '/../www-secret/secret.txt', '/%00', '/C:/Windows/win.ini'):
            with self_a.subTest(path=path_a):
                self_a.assertEqual(i_exchange(i_request(path_a))[0], 403)

    def i_test_not_found_and_directory_index(self_a) -> None:
        self_a.assertEqual(i_exchange(i_request('/inexistente'))[0], 404)
        self_a.assertEqual(i_exchange(i_request('/sub/'))[0], 404)
        self_a.assertEqual(i_exchange(i_request('/'))[0], 200)
        self_a.assertEqual(i_exchange(i_request('/sub/pagina.html'))[0], 200)

    def i_test_method_not_allowed(self_a) -> None:
        (status_a, headers_a, body_a) = i_exchange(i_request(method_a='DELETE'))
        self_a.assertEqual(status_a, 405)
        self_a.assertEqual(headers_a['allow'], 'GET, HEAD')

    def i_test_query_percent_encoding_and_header_case(self_a) -> None:
        data_a = b'GET /test%2etxt?ignorado=sim HTTP/1.1\r\nhOsT:lab\r\ncOnNeCtIoN:close\r\n\r\n'
        self_a.assertEqual(i_exchange(data_a)[0], 200)

    def i_test_http_10_and_close_token(self_a) -> None:
        for data_a in (b'GET /test.txt HTTP/1.0\r\n\r\n', i_request(connection_a='keep-alive, CLOSE')):
            self_a.assertEqual(i_exchange(data_a)[1]['connection'], 'close')
        self_a.assertEqual(i_exchange(i_request(version_a='HTTP/1.0'))[1]['connection'], 'keep-alive')

    def i_test_binary_mime_and_version(self_a) -> None:
        (status_a, headers_a, body_a) = i_exchange(i_request('/imagem.svg'))
        self_a.assertEqual(status_a, 200)
        self_a.assertEqual(headers_a['content-type'], 'image/svg+xml; charset=utf-8')
        self_a.assertEqual(i_exchange(i_request(version_a='HTTP/2.0'))[0], 505)

    def i_test_expect_rejected_without_waiting_for_body(self_a) -> None:
        data_a = b'POST / HTTP/1.1\r\nHost: x\r\nExpect: 100-continue\r\nContent-Length: 9\r\n\r\n'
        self_a.assertEqual(i_exchange(data_a)[0], 417)
if __name__ == '__main__':
    client_a.i_remote_main(HttpTests)
