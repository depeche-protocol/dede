"""
Test cases for messaging protocol over TCP/IP
"""

import time
import unittest
import binascii
import threading
import socket

import depeche.communication.adapter.localnet.bytebundle as message

message_str = """abcdefghijklmnopqrstuvxyzåäö나이"""

class TestMessage(unittest.TestCase):
    "Test case extension for messaging"

    def test_header_formatting(self):
        header = message._MessageHeader(0xde0ec0e1, 0, 0x11111111, True)
#        print("Default header looks like this:")
#        print(binascii.hexlify(header))


    def test_single_networking_message(self):
        server = self.ServerThread()
        server.start()

        time.sleep(0.2)

        client = self.ClientThread()
        client.start()

        client.join()
        server.join()

        self.assertEqual(client.sent_message, server.received_message)


    class ClientThread(threading.Thread):
        def __init__(self):
            self.sent_message = message_str
            threading.Thread.__init__(self)

        def run(self):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect(("127.0.0.1", 3338))
                message.send(self.sent_message.encode("utf-8"), sock)


    class ServerThread(threading.Thread):
        def __init__(self):
            self.received_message = None
            threading.Thread.__init__(self)

        def run(self):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 3338))
                sock.listen(5)

                (clientsocket, address) = sock.accept()
                msg_data = message.read(clientsocket)
                self.received_message = msg_data.decode("utf-8")
#                print("Received message: " + self.received_message)
                clientsocket.close()
