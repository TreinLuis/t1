"""Validação automática local; não substitui medições entre máquinas distintas."""
import sys
from pathlib import Path
import threading
import time
import unittest
import tempfile
import shutil
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import client
from server import HttpServer
from file_resolver import FileResolver, ForbiddenError
from http_response import guess_content_type
from test_http import HttpTests
from test_stream import StreamTests
from concurrency_test import run as concurrency
from benchmark import run as benchmark

class LocalTests(unittest.TestCase):

    def test_symlinks_and_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'www'
            root.mkdir()
            outside = Path(tmp) / 'www-secret'
            outside.mkdir()
            (outside / 'secret.txt').write_text('NUNCA SERVIR')
            try:
                (root / 'link').symlink_to(outside, target_is_directory=True)
                (root / 'index.html').symlink_to(outside / 'secret.txt')
            except OSError:
                self.skipTest('Sistema não permite criar symlinks')
            resolver = FileResolver(str(root))
            for path in ['/link/secret.txt', '/', '/../www-secret/secret.txt']:
                with self.subTest(path=path), self.assertRaises(ForbiddenError):
                    resolver.resolve(path)

    def test_idle_and_incomplete_timeout(self) -> None:
        for data in (b'', b'GET / HTTP/1.1\r\nHost:', b'POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nab'):
            with client.RawClient(client.HOST, client.PORT) as conn:
                conn.send(data)
                self.assertEqual(conn.sock.recv(1), b'')

    def test_large_file(self) -> None:
        expected = bytes(range(256)) * 8192
        with client.RawClient(client.HOST, client.PORT) as conn:
            conn.send(client.request('/large.bin', connection='close'))
            (status, headers, body) = conn.read_response()
            self.assertEqual(status, 200)
            self.assertEqual(headers['content-type'], 'application/octet-stream')
            self.assertEqual(body, expected)

    def test_all_mime_types(self) -> None:
        for (ext, mime) in [('html', 'text/html'), ('css', 'text/css'), ('js', 'text/javascript'), ('json', 'application/json'), ('txt', 'text/plain'), ('png', 'image/png'), ('jpg', 'image/jpeg'), ('jpeg', 'image/jpeg'), ('gif', 'image/gif'), ('pdf', 'application/pdf'), ('svg', 'image/svg+xml'), ('ico', 'image/x-icon')]:
            self.assertTrue(guess_content_type('x.' + ext).startswith(mime))

    def test_head_malformed_no_body(self) -> None:
        with client.RawClient(client.HOST, client.PORT) as conn:
            conn.send(b'HEAD / HTTP/1.1\r\nBad\r\n\r\n')
            self.assertEqual(conn.read_response(True)[0], 400)
            self.assertEqual(conn.buffer, b'')
            self.assertEqual(conn.sock.recv(1), b'')

    def test_head_oversized_no_body(self) -> None:
        with client.RawClient(client.HOST, client.PORT) as conn:
            conn.send(b'HEAD / HTTP/1.1\r\nHost: x\r\nX: ' + b'a' * 17000 + b'\r\n\r\n')
            status, headers, body = conn.read_response(True)
            self.assertEqual(status, 400)
            self.assertGreater(int(headers['content-length']), 0)
            self.assertEqual(conn.buffer, b'')
            self.assertEqual(conn.sock.recv(1), b'')

    def test_concurrent_slow_client(self) -> None:
        concurrency(client.HOST, client.PORT, 12)

    def test_benchmarks(self) -> None:
        c1 = benchmark(client.HOST, client.PORT, requests=10, mode='c1')
        c2 = benchmark(client.HOST, client.PORT, requests=10, mode='c2')
        self.assertEqual((c1['connections'], c2['connections']), (10, 1))
        self.assertEqual(c1['body_bytes'], c2['body_bytes'])
if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(ROOT / 'www', Path(tmp) / 'www')
        (Path(tmp) / 'www' / 'large.bin').write_bytes(bytes(range(256)) * 8192)
        server = HttpServer('0.0.0.0', 0, str(Path(tmp) / 'www'), idle_timeout=0.7)
        thread = threading.Thread(target=server.start)
        thread.start()
        deadline = time.monotonic() + 3
        while server.port == 0 and thread.is_alive() and (time.monotonic() < deadline):
            time.sleep(0.01)
        if server.port == 0 or not thread.is_alive():
            server.shutdown()
            thread.join(3)
            raise SystemExit('FAIL: servidor local não iniciou')
        client.PORT = server.port
        suite = unittest.TestSuite((unittest.defaultTestLoader.loadTestsFromTestCase(case) for case in (HttpTests, StreamTests, LocalTests)))
        try:
            passed = client.run_suite(suite)
        finally:
            server.shutdown()
            thread.join(3)
        assert not thread.is_alive(), 'Thread principal não encerrou'
        assert not server.workers, 'Threads de conexão não encerraram'
        raise SystemExit(0 if passed else 1)
