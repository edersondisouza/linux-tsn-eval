# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import struct

StartByte = b'\x01'  # SOH character
HeaderFormat = '!cI'  # StartByte + 4 bytes of msg length not including header


class CommunicationError(Exception):
    pass


class MPPSocket:
    def __init__(self, socket):
        self.socket = socket
        self.header_size = struct.calcsize(HeaderFormat)
        self.recv_fifo = bytearray()

    # Add a start byte and a 4 byte length to the start of the message
    def send(self, message):
        header = struct.pack(HeaderFormat, StartByte, len(message))
        bytes_sent = self.socket.sendmsg([header, message])
        return bytes_sent - len(header)

    # keep appending incoming data to the recv_fifo until a full message is
    # received. Once a full message is received, it is pulled off. Any other
    # messages are left in the fifo.
    def getmsg(self):
        if len(self.recv_fifo) < self.header_size:
            self.recv_fifo.extend(self.socket.recv(1024))

        # decode the first few bytes of the FIFO as a message header
        (start_symbol, expected_message_len) = struct.unpack(
            HeaderFormat, self.recv_fifo[0:self.header_size])

        if start_symbol != StartByte:
            raise CommunicationError(f'Got invalid byte {self.recv_fifo[0]}.\n'
                                     f' Full buffer is {repr(self.recv_fifo)}')

        full_message_length = expected_message_len + self.header_size
        # if we're waiting on more data still
        while len(self.recv_fifo) < full_message_length:
            self.recv_fifo.extend(self.socket.recv(1024))

        # pop message from the head of the fifo
        message = self.recv_fifo[self.header_size:full_message_length]
        del self.recv_fifo[0:full_message_length]

        return message

    def close(self):
        self.socket.close()
