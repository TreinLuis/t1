"""Testes de fronteiras de mensagens, independentes das fronteiras do TCP."""
import time as time_a
import unittest as unittest_a
import client as client_a
from client import RawClient, i_request as i_request

class StreamTests(unittest_a.TestCase):

    def i_test_fragmented_byte_by_byte(self_a) -> None:
        with RawClient(client_a.HOST_a, client_a.PORT_a) as connection_a:
            for byte_a in i_request():
                connection_a.i_send(bytes([byte_a]))
                time_a.sleep(0.001)
            self_a.assertEqual(connection_a.i_read_response()[0], 200)

    def i_test_three_pipelined_requests(self_a) -> None:
        with RawClient(client_a.HOST_a, client_a.PORT_a) as connection_a:
            packet_a = i_request() + i_request('/ausente') + i_request('/', connection_a='close')
            self_a.assertEqual(connection_a.sock_a.send(packet_a), len(packet_a))
            self_a.assertEqual([connection_a.i_read_response()[0] for __a in range(3)], [200, 404, 200])
            self_a.assertEqual(connection_a.sock_a.recv(1), b'')

    def i_test_complete_plus_half_next_request(self_a) -> None:
        second_a = i_request('/sub/pagina.html', connection_a='close')
        middle_a = len(second_a) // 2
        with RawClient(client_a.HOST_a, client_a.PORT_a) as connection_a:
            connection_a.i_send(i_request() + second_a[:middle_a])
            self_a.assertEqual(connection_a.i_read_response()[0], 200)
            connection_a.i_send(second_a[middle_a:])
            self_a.assertEqual(connection_a.i_read_response()[0], 200)

    def i_test_body_consumed_before_next_request(self_a) -> None:
        first_a = b'POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nabcde'
        with RawClient(client_a.HOST_a, client_a.PORT_a) as connection_a:
            connection_a.i_send(first_a + i_request(connection_a='close'))
            self_a.assertEqual(connection_a.i_read_response()[0], 405)
            self_a.assertEqual(connection_a.i_read_response()[0], 200)

    def i_test_head_then_get(self_a) -> None:
        with RawClient(client_a.HOST_a, client_a.PORT_a) as connection_a:
            connection_a.i_send(i_request(method_a='HEAD') + i_request(connection_a='close'))
            self_a.assertEqual(connection_a.i_read_response(True)[0], 200)
            self_a.assertEqual(connection_a.i_read_response()[0], 200)

    def i_test_sequential_persistent_connection(self_a) -> None:
        with RawClient(client_a.HOST_a, client_a.PORT_a) as connection_a:
            for __a in range(10):
                connection_a.i_send(i_request())
                self_a.assertEqual(connection_a.i_read_response()[1]['connection'], 'keep-alive')
if __name__ == '__main__':
    client_a.i_remote_main(StreamTests)
