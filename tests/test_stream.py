"""Testes de fronteiras de mensagens, independentes das fronteiras do TCP."""
import time
import unittest
import client
from client import RawClient, request

class StreamTests(unittest.TestCase):

    def test_fragmented_byte_by_byte(self) -> None:
        with RawClient(client.HOST, client.PORT) as connection:
            for byte in request():
                connection.send(bytes([byte]))
                time.sleep(0.001)
            self.assertEqual(connection.read_response()[0], 200)

    def test_three_pipelined_requests(self) -> None:
        with RawClient(client.HOST, client.PORT) as connection:
            packet = request() + request('/ausente') + request('/', connection='close')
            self.assertEqual(connection.sock.send(packet), len(packet))
            self.assertEqual([connection.read_response()[0] for _ in range(3)], [200, 404, 200])
            self.assertEqual(connection.sock.recv(1), b'')

    def test_complete_plus_half_next_request(self) -> None:
        second = request('/sub/pagina.html', connection='close')
        middle = len(second) // 2
        with RawClient(client.HOST, client.PORT) as connection:
            connection.send(request() + second[:middle])
            self.assertEqual(connection.read_response()[0], 200)
            connection.send(second[middle:])
            self.assertEqual(connection.read_response()[0], 200)

    def test_body_consumed_before_next_request(self) -> None:
        first = b'POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nabcde'
        with RawClient(client.HOST, client.PORT) as connection:
            connection.send(first + request(connection='close'))
            self.assertEqual(connection.read_response()[0], 405)
            self.assertEqual(connection.read_response()[0], 200)

    def test_head_then_get(self) -> None:
        with RawClient(client.HOST, client.PORT) as connection:
            connection.send(request(method='HEAD') + request(connection='close'))
            self.assertEqual(connection.read_response(True)[0], 200)
            self.assertEqual(connection.read_response()[0], 200)

    def test_sequential_persistent_connection(self) -> None:
        with RawClient(client.HOST, client.PORT) as connection:
            for _ in range(10):
                connection.send(request())
                self.assertEqual(connection.read_response()[1]['connection'], 'keep-alive')
if __name__ == '__main__':
    client.remote_main(StreamTests)
