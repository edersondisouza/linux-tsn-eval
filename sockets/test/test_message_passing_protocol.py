import unittest
from unittest.mock import MagicMock
from sockets.experiment.util.message_passing_protocol import MPPSocket
from sockets.experiment.util.message_passing_protocol import StartByte, HeaderFormat
from sockets.experiment.util.message_passing_protocol import CommunicationError
import struct


class TestUnderlyingSocketIsUsedCorrectly(unittest.TestCase):
    def setUp(self):
        self.mock_socket = MagicMock()
        self.mpp = MPPSocket(self.mock_socket)

    def check_header_format(self, message):
        header = struct.pack(HeaderFormat, StartByte, len(message))
        self.mock_socket.sendmsg.return_value = len(message) + len(header)
        self.assertEqual(self.mpp.send(message), len(message))
        self.mock_socket.sendmsg.assert_called_with([header, message])

    def test_a_header_is_added_when_sending_a_message(self):
        self.check_header_format(b'')
        self.mock_socket.reset()
        self.check_header_format(b'Hello')

    def test_underlying_socket_is_closed_when_closed(self):
        self.mpp.close()
        self.mock_socket.close.assert_called()

    def test_exception_raised_if_first_byte_is_not_StartByte(self):
        self.mock_socket.recv.return_value = b'abcdefghijklmnop'
        with self.assertRaises(CommunicationError):
            self.mpp.getmsg()


class FakeSocket:
    def __init__(self):
        self.recv_buffer = bytearray()

    def send(self, bytes):
        self.recv_buffer.extend(bytes)
        return len(bytes)

    def recv(self, buflen):
        actual_len = min(buflen, len(self.recv_buffer))
        return_data = bytes(self.recv_buffer[0:actual_len])
        del self.recv_buffer[0:actual_len]
        return return_data

    def sendmsg(self, buflist):
        return self.send(b''.join(buflist))


class TestMessageReception(unittest.TestCase):
    def setUp(self):
        connection = FakeSocket()
        self.talker = MPPSocket(connection)
        self.listener = MPPSocket(connection)

    def test_message_is_received_if_buffer_is_big_enough(self):
        self.talker.send(b'Hello')
        self.assertEqual(self.listener.getmsg(), b'Hello')
        self.talker.send(b'Goodbye')
        self.assertEqual(self.listener.getmsg(), b'Goodbye')
        self.talker.send(b'Hello')
        self.assertEqual(self.listener.getmsg(), b'Hello')

    def test_only_one_message_is_received_if_more_available(self):
        self.talker.send(b'Hello')
        self.talker.send(b'Goodbye')
        self.assertEqual(self.listener.getmsg(), b'Hello')
        self.assertEqual(self.listener.getmsg(), b'Goodbye')
