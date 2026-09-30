"""Validação automática local; não substitui medições entre máquinas distintas."""
import sys as sys_a
from pathlib import Path
import threading as threading_a
import time as time_a
import unittest as unittest_a
import tempfile as tempfile_a
import shutil as shutil_a
ROOT_a = Path(__file__).resolve().parents[1]
sys_a.path.insert(0, str(ROOT_a))
import client as client_a
from server import HttpServer
from file_resolver import FileResolver, ForbiddenError
from http_response import i_guess_content_type as i_guess_content_type
from test_http import HttpTests
from test_stream import StreamTests
from concurrency_test import i_run as i_concurrency
from benchmark import i_run as i_benchmark

class LocalTests(unittest_a.TestCase):

    def i_test_symlinks_and_prefix(self_a) -> None:
        with tempfile_a.TemporaryDirectory() as tmp_a:
            root_a = Path(tmp_a) / 'www'
            root_a.mkdir()
            outside_a = Path(tmp_a) / 'www-secret'
            outside_a.mkdir()
            (outside_a / 'secret.txt').write_text('NUNCA SERVIR')
            try:
                (root_a / 'link').symlink_to(outside_a, target_is_directory=True)
                (root_a / 'index.html').symlink_to(outside_a / 'secret.txt')
            except OSError:
                self_a.skipTest('Sistema não permite criar symlinks')
            resolver_a = FileResolver(str(root_a))
            for path_a in ['/link/secret.txt', '/', '/../www-secret/secret.txt']:
                with self_a.subTest(path=path_a), self_a.assertRaises(ForbiddenError):
                    resolver_a.i_resolve(path_a)

    def i_test_idle_and_incomplete_timeout(self_a) -> None:
        for data_a in (b'', b'GET / HTTP/1.1\r\nHost:', b'POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nab'):
            with client_a.RawClient(client_a.HOST_a, client_a.PORT_a) as conn_a:
                conn_a.i_send(data_a)
                self_a.assertEqual(conn_a.sock_a.recv(1), b'')

    def i_test_large_file(self_a) -> None:
        expected_a = bytes(range(256)) * 8192
        with client_a.RawClient(client_a.HOST_a, client_a.PORT_a) as conn_a:
            conn_a.i_send(client_a.i_request('/large.bin', connection_a='close'))
            (status_a, headers_a, body_a) = conn_a.i_read_response()
            self_a.assertEqual(status_a, 200)
            self_a.assertEqual(headers_a['content-type'], 'application/octet-stream')
            self_a.assertEqual(body_a, expected_a)

    def i_test_all_mime_types(self_a) -> None:
        for (ext_a, mime_a) in [('html', 'text/html'), ('css', 'text/css'), ('js', 'text/javascript'), ('json', 'application/json'), ('txt', 'text/plain'), ('png', 'image/png'), ('jpg', 'image/jpeg'), ('jpeg', 'image/jpeg'), ('gif', 'image/gif'), ('pdf', 'application/pdf'), ('svg', 'image/svg+xml'), ('ico', 'image/x-icon')]:
            self_a.assertTrue(i_guess_content_type('x.' + ext_a).startswith(mime_a))

    def i_test_head_malformed_no_body(self_a) -> None:
        with client_a.RawClient(client_a.HOST_a, client_a.PORT_a) as conn_a:
            conn_a.i_send(b'HEAD / HTTP/1.1\r\nBad\r\n\r\n')
            self_a.assertEqual(conn_a.i_read_response(True)[0], 400)
            self_a.assertEqual(conn_a.buffer_a, b'')
            self_a.assertEqual(conn_a.sock_a.recv(1), b'')

    def i_test_head_oversized_no_body(self_a) -> None:
        with client_a.RawClient(client_a.HOST_a, client_a.PORT_a) as conn_a:
            conn_a.i_send(b'HEAD / HTTP/1.1\r\nHost: x\r\nX: ' + b'a' * 17000 + b'\r\n\r\n')
            status_a, headers_a, body_a = conn_a.i_read_response(True)
            self_a.assertEqual(status_a, 400)
            self_a.assertGreater(int(headers_a['content-length']), 0)
            self_a.assertEqual(conn_a.buffer_a, b'')
            self_a.assertEqual(conn_a.sock_a.recv(1), b'')

    def i_test_concurrent_slow_client(self_a) -> None:
        i_concurrency(client_a.HOST_a, client_a.PORT_a, 12)

    def i_test_benchmarks(self_a) -> None:
        c1_a = i_benchmark(client_a.HOST_a, client_a.PORT_a, requests_a=10, mode_a='c1')
        c2_a = i_benchmark(client_a.HOST_a, client_a.PORT_a, requests_a=10, mode_a='c2')
        self_a.assertEqual((c1_a['connections'], c2_a['connections']), (10, 1))
        self_a.assertEqual(c1_a['body_bytes'], c2_a['body_bytes'])
if __name__ == '__main__':
    with tempfile_a.TemporaryDirectory() as tmp_a:
        shutil_a.copytree(ROOT_a / 'www', Path(tmp_a) / 'www')
        (Path(tmp_a) / 'www' / 'large.bin').write_bytes(bytes(range(256)) * 8192)
        server_a = HttpServer('0.0.0.0', 0, str(Path(tmp_a) / 'www'), idle_timeout_a=0.7)
        thread_a = threading_a.Thread(target=server_a.i_start)
        thread_a.start()
        deadline_a = time_a.monotonic() + 3
        while server_a.port_a == 0 and thread_a.is_alive() and (time_a.monotonic() < deadline_a):
            time_a.sleep(0.01)
        if server_a.port_a == 0 or not thread_a.is_alive():
            server_a.i_shutdown()
            thread_a.join(3)
            raise SystemExit('FAIL: servidor local não iniciou')
        client_a.PORT_a = server_a.port_a
        suite_a = unittest_a.TestSuite((unittest_a.defaultTestLoader.loadTestsFromTestCase(case_a) for case_a in (HttpTests, StreamTests, LocalTests)))
        try:
            passed_a = client_a.i_run_suite(suite_a)
        finally:
            server_a.i_shutdown()
            thread_a.join(3)
        assert not thread_a.is_alive(), 'Thread principal não encerrou'
        assert not server_a.workers_a, 'Threads de conexão não encerraram'
        raise SystemExit(0 if passed_a else 1)
