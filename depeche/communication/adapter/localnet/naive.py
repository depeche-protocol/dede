"""
This is a tcp/udp adapter for use in connecting depeche clients
across local networks, either by wire or wirelessly. Please
note the following:

* This adapter should not be used to constantly make UDP broadcasts,
  answering any calls unless _explicitly_ set to. In any hostile
  environment, that might spell trouble. A whitelist of networks
  might be an acceptable compromise, but still iffy if unsecured
  as the name is easily spoofed.
"""
import uuid
import threading
import socket
import json
import time

from queue import Queue

import socketserver
from socketserver import TCPServer
from socketserver import BaseRequestHandler

from depeche.crypto.provider_nacl import ProviderNaCl
from depeche.communication.protocol.structures import RendezvousInfo
from depeche.communication.protocol.structures import MessageContainer
from depeche.communication.protocol.structures import NoMoreData
from depeche.communication.protocol.structures import StopSending
from depeche.communication.adapter.localnet import bytebundle

import logging
logger = logging.getLogger(__name__)


DEFAULT_UDP_BROADCAST_PORT = 27272
DEFAULT_TCP_EXCHANGE_SERVER_PORT = 27272
DEFAULT_TCP_RENDEZVOUS_SERVER_PORT = 27273
DEFAULT_BUF_SIZE = 8192

def _send_udp_broadcast(contents,
                        port=DEFAULT_UDP_BROADCAST_PORT):
    """
    This method will send a udp broadcast message with the
    contents specified baked in. If the contents exceed the MTU
    of a UDP package (65,507 bytes), they WILL BE TRUNCATED.
    Generally, this suffices for any set-up/rendezvous message
    in this application.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as my_socket:
        my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        my_socket.sendto(contents.encode("utf-8"), (socket.gethostname(), port))


def _send_server_announcment(server_type: str, port: int,
                             callsign: str=None):
    contents = json.dumps({
        "protocol": "depeche_ipadapter",
        "version": 0,
        "operation": "server_announcement",
        "content": {
            "server_type": server_type,
            "server_port": port,
            "callsign": callsign,
            },
        }, ensure_ascii=False)

    logger.debug("Sending announcement (UDP broadcast): " + contents)
    _send_udp_broadcast(contents)


def _read_announcement_from_socket(sock, server_type="rendezvous"):
    """
    This function will read a server announcement and return the IP
    number and port of the announcing server as a tuple. A proper
    timeout should be set before this is nvoled, lest the thread hang
    forever.
    Only announcements of the correct type will trigger this method
    to finish - Other types will be ignored.
    """
    data, address = sock.recvfrom(DEFAULT_BUF_SIZE)
    broadcast_str, address = (data.decode("utf-8"), address[0])

    logger.debug("Announcement received! " + broadcast_str)
    if _validate_announcement(broadcast_str, server_type):
        # This checks out! Let's give it a shot!
        broadcast = json.loads(broadcast_str)
        server_port = broadcast["content"]["server_port"]
        callsign = broadcast["content"]["callsign"]
        return address, server_port, callsign
    else:
        logger.info("Broadcast data does not conform to expectations -> " +
                    str(broadcast) + " <- Continuing listening.")
        raise ValueError("Broadcast does not conform to expectations")


def _validate_announcement(broadcast_str: str, server_type: str="rendezvous") -> bool:
    """
    Will validate wether an announcement heard over the local net.
    If it is a valid (and interesting) announcement True is returned,
    otherwise False
    """
    broadcast = json.loads(broadcast_str)

    # Check for validity and protocol+version
    if broadcast["protocol"] == "depeche_ipadapter" and \
      broadcast["version"] == 0 and \
      broadcast["operation"] == "server_announcement" and \
      broadcast["content"]["server_type"] == server_type and \
      broadcast["content"]["server_port"] > 0:
        return True
    else:
        return False

def _create_socket_server(handler: BaseRequestHandler, base_port: int, max_port_offset: int=10) -> TCPServer:
    """
    Convenience method for starting a TCP socket server, selecting an open
    port based on the initial port given. If no open socket can be found on which to
    host the server, an exception is thrown.
    """
    tries = 0
    while tries < max_port_offset:
        port = base_port + tries
        try:
            logger.debug("Opening 'server' port: {}".format(port))
            server = TCPServer((socket.gethostname(), port), handler)
            return server
        except:
            logger.debug("Problems opening port, trying another")
            tries = tries + 1

            # When we have exhausted the range of ports, we go here
            if tries >= max_port_offset:
                raise

    # Another one of those "this should not happen" scenarios that are bound to happen
    raise AppError("Reached faulty state when trying to start socket server")


def _message_exchange_loop(sock, messages_array,
                           on_message_received, start_sending=False):
    """
    This method describes how to exchange messages once a socket
    has been opened between two nodes.
    If "start_sending" is set to True, the loop will begin by sending
    messages. If not, it will start by listening for other party to
    start sending. Proper behaviour for the "server" node is to run
    this with start_sending set to False, the connecting node should
    start by sending messages (even if those messages consist only
    of "no_more_data", as the case may be).
    """
    keep_sending = True
    keep_receiving = True

    messages_to_send = iter(messages_array)

    if start_sending:
        keep_sending, keep_receiving = \
          _send_messages(sock, keep_sending, keep_receiving, messages_to_send)

    while keep_sending or keep_receiving:

        keep_sending, keep_receiving = \
          _receive_messages(sock, keep_sending, keep_receiving, on_message_received)

        keep_sending, keep_receiving = \
          _send_messages(sock, keep_sending, keep_receiving, messages_to_send)


def _receive_messages(sock, keep_sending, keep_receiving,
                      on_message_received):
    logger.debug("Starting receive message sequence...")

    data = bytebundle.read(sock)
    payload = data.decode("utf-8")

    received_data = MessageContainer.deserialize(payload)
    for message in received_data:
        if message.type == StopSending.message_type:
            logger.debug("Remote node will not heed any more data")
            keep_sending = False
        elif message.type == NoMoreData.message_type:
            logger.debug("Remote node has no more data")
            keep_receiving = False
        else:
            # Not a control message. signal user
            # message to main program
            logger.debug("Message received: " + str(message))
            on_message_received(message)
    # Return status flags - possibly modified by receiving flow control
    # messages
    return keep_sending, keep_receiving


def _send_messages(sock, keep_sending, keep_receiving, messages_to_send):
    # Current implementation is a bit chatty -
    # consider exchanging chunks of messages. Maybe
    # size limited to make sure we don't get too
    # long send/receive times and too large buffer
    # sizes.
    logger.debug("Starting send message sequence...")

    if keep_sending:
        outgoing_message = next(messages_to_send, None)
        if not outgoing_message is None:
            logger.debug("Sending message: " + str(outgoing_message))
            outgoing_container = MessageContainer([outgoing_message])
        else:
            keep_sending = False

    if not keep_sending:
        # We have nothing to exchange. Just send a
        # "ready_to_receive" message in return
        logger.debug("No more messages to send: Sedning 'NoMoreData'")
        outgoing_container = MessageContainer([NoMoreData()])

    outgoing_data = outgoing_container.serialize().encode("utf-8")
    bytebundle.send(outgoing_data, sock)

    return keep_sending, keep_receiving


class TcpUdpAdapter:
    """Implements adapter functions for ethernet (UDP and TCP/IP)"""

    info = {
        "ergonomic_name": "Naïve local network adapter",
        "elaboration": "TCP/UDP adapter for low-threat networks. "
                       "Only supports rendezvous and message exchange "
                       "with peers on the same network segment. "
                       "Should NOT be used in high-threat scenarios "
                       "as it will expose your MAC as using the "
                       "depeche protocol."
    }


    def __init__(self, crypto_provider: ProviderNaCl,
                 rendezvous_server_port=DEFAULT_TCP_RENDEZVOUS_SERVER_PORT):
        self.provider = crypto_provider
        self.rendezvous_server_port = rendezvous_server_port
        self.exchange_server_thread = None
        self.exchange_listener_thread = None
        self._callsign = str(uuid.uuid4())


    def start_register_announcements(self, on_announcement: callable,
                                     port: int=DEFAULT_UDP_BROADCAST_PORT,
                                     timeout: int=None):
        """
        Will cause the adapter to listen for other "active" peers.
        Every time a new peer announcement is received, the
        on_node_found function will be called with the server
        information.
        """
        self.exchange_listener_thread = \
          self._ExchangeAnnouncementListener(on_announcement, port, timeout)

        self.exchange_listener_thread.start()


    class _ExchangeAnnouncementListener(threading.Thread):
        """
        This thread will listen for message exchange server announcements.
        If one is received, the given on_announcement callback will
        be invoked with the announcement as argument. This will allow
        the layer above the adapter to determine wether a connection
        to the announced server should be made.
        """
        def __init__(self, on_announcement: callable, port=DEFAULT_UDP_BROADCAST_PORT,
                     timeout: int=None, own_callsign: str=None):
            self.on_announcement = on_announcement
            self.port = port
            self.done = False
            self.timeout = timeout
            self.own_callsign = own_callsign

            threading.Thread.__init__(self)


        def run(self):
            self.listen()


        def listen(self):
            """Listens for server broadcasts and calls callback"""
            logger.debug("Listening for exchange server "
                         "announcements on UDP port: {}".format(self.port))

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as my_socket:
                my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                my_socket.bind((socket.gethostname(), self.port))
                my_socket.settimeout(0.2)

                start = time.time()
                while not self.done:
                    try:
                        ip_number, port, callsign =_read_announcement_from_socket(my_socket, "exchange")
                        if callsign == self.own_callsign:
                            logger.debug("Picked up my own announcement. Disregarding it.")
                        else:
                            self.on_announcement(ip_number, port)
                    except (ValueError, socket.timeout):
                        # Normal case - No message received within socket read timeout
                        now = time.time()
                        if (self.timeout != None) and (now - start > self.timeout):
                            self.done = True
                            logger.debug("Announcement listening timeout. Giving up.")
                    except ConnectionRefusedError as err:
                        logger.error("Problem occurred setting up TCP "
                                     "connection: {}. "
                                     "Continuing listening.".format(err))
                logger.debug("Announcement listener stopped")


    def stop_register_announcements(self):
        """
        Will cause cessation of listening to announcements from peer
        nodes running servers.
        """
        if not self.exchange_listener_thread is None:
            self.exchange_listener_thread.done = True
            self.exchange_listener_thread.join()


    def start_message_exchange_server(self,
                                      get_messages_to_send: callable,
                                      on_message_received: callable,
                                      port: int=DEFAULT_TCP_EXCHANGE_SERVER_PORT,
                                      run_once_and_stop: bool=True,
                                      timeout: int=30):
        """
        This is the "active" way to find peers - It sets up a server
        and announces its presence on the local network. As such it
        will potentially expose the node owner to malicious actors on
        the network.
        This method is asynchronous. The callbacks will be invoked on a
        separate thread - The caller should ensure thread safety in the callback.
        If "run_once_and_stop" is specified (the default value),
        there will only announce presence once and allow any interested
        peers a short window of opportunity to initiate message
        exchange after which stop_exchange_server is automatically
        invoked.
        """
        server_status_queue = Queue()

        self.exchange_server_thread = \
          self._MessageExchangeServer(server_status_queue,
                                      get_messages_to_send,
                                      on_message_received,
                                      port)

        self.exchange_server_thread.start()

        try:
            status = server_status_queue.get(timeout = 30) # Make sure that the port is open before
                                                           # announcing it

            # Due to dynamoc port selection, we need to keep tabs of what was actually selected
            (_, selected_port) = self.exchange_server_thread.server.server_address

            if status != "RUNNING":
                logger.error("Unexpected status while starting message exchange server")
                return
        except:
            logger.error("Error whilst starting message exchange server")
            return


        _send_server_announcment("exchange", selected_port, self._callsign)
        if run_once_and_stop:
            self.exchange_server_timer = threading.Timer(timeout, self.stop_message_exchange_server)
            self.exchange_server_timer.start()


    class _MessageExchangeServer(threading.Thread):
        """
        This thread sets up a "server" to allow peer nodes that are
        willing to exchange messages to connect to.
        """
        def __init__(self,
                     queue: Queue,
                     get_messages_callback: callable,
                     on_message_received: callable,
                     port=DEFAULT_TCP_EXCHANGE_SERVER_PORT):
            self.queue = queue
            self.done = False
            self.get_messages_callback = get_messages_callback
            self.on_message_received = on_message_received
            self.port = port
            self.server = None

            threading.Thread.__init__(self)


        def run(self):
            """
            This starts an exchange "server" that listens to a port for
            message exchanges from clients.
            The thread should be set to DONE if this node decides to
            be the "contacting" party instead.
            """
            self.server = _create_socket_server(self._ExchangeHandler, self.port)

            # Set up data needed by the handler
            self.server.timeout = 0.2
            self.server.get_messages_callback = self.get_messages_callback
            self.server.on_message_received = self.on_message_received

            # Signal that we are now handlng requests
            self.queue.put("RUNNING")

            while not self.done:
                self.server.handle_request()

            self.server.socket.close()

            # Signal that we are done and no longer handling requests
            self.queue.put("STOPPED")
            logger.debug("Message exchange server shut down on request.")


        class _ExchangeHandler(BaseRequestHandler):
            def handle(self):
                # self.request is the TCP socket connected to the client
                sock = self.request
                logger.debug("Client connected to message exchange server")

                # Currently, fetch all messages we want to send in one
                # big chunk. This might not be practical if we want
                # to send a great many messages.
                messages_to_send = self.server.get_messages_callback()
                _message_exchange_loop(sock,
                                       messages_to_send,
                                       self.server.on_message_received)
    #END _MessageExchangeServer


    def stop_message_exchange_server(self):
        """
        This method will close any running message exchange server
        running a the moment. Please notice that it will NOT interrupt
        any current message exchange, only remove the possibility of
        new peers connecting to the server.
        """
        if not self.exchange_server_thread is None:
            self.exchange_server_timer.cancel()
            self.exchange_server_thread.done = True
            self.exchange_server_thread.join()


    def exchange_messages_with_server(self, destination: (str, int),
                                      messages, on_message_received):
        """
        Will attempt to connect to the message exchange server
        running at the destination peer.
        If the peer is not running a server, nothing will happen.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(destination)
        _message_exchange_loop(sock, messages, on_message_received, True)
        sock.close()


    def rendezvous(self, shared_secret, rendezvous_info,
                   timeout: int=30):
        """
        This will initiate a rendezvous with the a peer broadcasting
        under a given callsign.
        It will return rendezvous result: Success or failure and
        (if success) the node information of the peer.
        """
        # 1. Start listening for rendezvous announcements
        # 2. Open TCP port for rendezvous - Set up a server
        # 3. Send out announcement that other party may pick up
        # 4. If an announcment is picked up, kill server thread and
        #    initate rendezvous protocol by sending message (R1)
        #    to the announcing server.

        # Rendezvous goes like this:
        # R1. A sends data encrypted with AES256 under the shared
        #     secret to B
        # R2. B sends data encrypted with AES256 under the shared
        #     secret to A
        rendezvous_done = threading.Event()
        queue = Queue()

        def callback():
            """Called by another thread to signal completion."""
            rendezvous_done.set()

        port_listener_thread = \
          self._RendezvousServer(queue,
                                 shared_secret,
                                 rendezvous_info,
                                 self.provider,
                                 callback,
                                 self.rendezvous_server_port,
                                 timeout)

        port_listener_thread.start()

        status = queue.get() # Make sure that the port listener is up before announcing it
        if status == "FAIL":
            logger.error("Rendezvous server could not be started")
            return (False, None)

        # Once we know that we can handle any resultant calls we issue the
        # announcement
        _send_server_announcment("rendezvous", port_listener_thread.port, self._callsign)

        announcement_listener_thread = \
          self._RendezvousAnnouncementListener(shared_secret,
                                               rendezvous_info,
                                               self.provider,
                                               callback,
                                               timeout)

        announcement_listener_thread.start()

        rendezvous_done.wait()

        result = (False, None)
        if announcement_listener_thread.done:
            # The announcement listener succeeded. Shut down the port listener
            port_listener_thread.done = True
            result = announcement_listener_thread.result
        elif port_listener_thread.done:
            # The post listener succeeded. Shut down the announcement listener
            announcement_listener_thread.done = True
            result = port_listener_thread.result
        else:
            # Timeout
            port_listener_thread.done = True
            announcement_listener_thread.done = True
        return result


    class _RendezvousAnnouncementListener(threading.Thread):
        """
        This thread will listen for rendezvous server announcements.
        if one is received, the listener will open a connection to
        it and deposit rendezvous info there, also it'll listen for
        the servers reply and invoke the callback with any information
        that validates.
        """
        def __init__(self,
                     shared_secret: str,
                     own_info: RendezvousInfo,
                     crypto_provider: ProviderNaCl,
                     callback,
                     timeout: int=None):
            self.shared_secret = shared_secret
            self.own_rendezvous_info = own_info
            self.provider = crypto_provider
            self.on_rendezvous_complete = callback
            self.timeout = timeout
            self.done = False
            self.result = (False, None)

            threading.Thread.__init__(self)


        def run(self):
            self.listen()


        def listen(self):
            """Listens for server broadcasts and initiates rendezvous"""
            logger.debug("Listening for announcements on "
                         "UDP port: {}".format(DEFAULT_UDP_BROADCAST_PORT))

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as my_socket:
                my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                my_socket.bind((socket.gethostname(), DEFAULT_UDP_BROADCAST_PORT))
                my_socket.settimeout(0.2)

                start = time.time()
                while not self.done:
                    try:
                        ip_number, port, callsign = _read_announcement_from_socket(my_socket)
                        if callsign == self.own_rendezvous_info.alias:
                            logger.debug("Picked up my own announcement. Disregarding it.")
                        else:
                            self.initiate_rendezvous(ip_number, port)
                    except (ValueError, socket.timeout):
                        # Normal case when no announcement has been picked up
                        now = time.time()
                        if (self.timeout != None) and (now - start > self.timeout):
                            self.done = True
                            logger.debug("Announcement listening timeout. Giving up.")
                    except ConnectionRefusedError as err:
                        logger.error("Problem occurred setting up TCP "
                                     "connection: {}. "
                                     "Continuing listening.".format(err))
                self.on_rendezvous_complete()


        def initiate_rendezvous(self, address, port):
            """Initates rendezvous and invokes callback on success"""
            logger.debug("Initiating rendezvous with {}:{}".format(address, port))

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((address, port))

            info_str = self.own_rendezvous_info.serialize()
            crypted_str = self.provider.encrypt_symmetric(info_str, self.shared_secret)
            bytebundle.send(crypted_str.encode("utf-8"), sock)

            reply = bytebundle.read(sock).decode("utf-8")
            decrypted_reply = self.provider.decrypt_symmetric(reply, self.shared_secret)
            other_rendezvous_info = RendezvousInfo.deserialize(decrypted_reply)

            sock.close()

            self.done = True
            self.result = (True, other_rendezvous_info)
    #END _AnnouncementListener


    class _RendezvousServer(threading.Thread):
        """
        This thread sets up a "server" to listen for the rendezvous
        on a TCP port. The other peer may connect to the port in order
        to exchange rendezvous info.
        Making stuff clearer - This is the TCP server that the counterpart
        will connect to once it has received the UDP broadcast announcement.
        """

        def __init__(self,
                     queue: Queue,
                     shared_secret: str,
                     own_info: RendezvousInfo,
                     crypto_provider: ProviderNaCl,
                     callback,
                     port=DEFAULT_TCP_RENDEZVOUS_SERVER_PORT,
                     timeout: int=None):

            self.queue = queue
            self.shared_secret = shared_secret
            self.own_rendezvous_info = own_info
            self.provider = crypto_provider
            self.done = False
            self.result = (False, None)
            self.callback = callback
            self.port = port
            self.timeout = timeout

            threading.Thread.__init__(self)


        def run(self):
            """
            This starts a rendezvous "server" that listens to a port for
            messages from a given client. It will handle the rendezvous
            protocol based on being the "contacted" party.
            The thread should be set to DONE if this node decides to
            be the "contacting" party instead.
            """
            success = False
            tries = 0
            server = None

            while not success and tries < 10:
                self.port = self.port + tries
                try:
                    logger.debug("Opening 'server' port: {}".format(self.port))
                    server = TCPServer((socket.gethostname(), self.port),
                                        self._RendezvousHandler)
                    success = True
                except:
                    logger.debug("Problems opening port")
                    tries = tries + 1

            if not success:
                logger.error("Could not open port for rendezvous server. Failure.")
                self.done = True
                self.result = (False, None)
                self.queue.put("FAIL")
                self.callback()
                return

            # Set up data needed by the handler
            server.timeout = self.timeout
            server.shared_secret = self.shared_secret
            server.own_rendezvous_info = self.own_rendezvous_info
            server.provider = self.provider
            server.timeout = 0.5
            server.done = False
            server.result = (False, None)

            # Signal to parent that we are now up and running
            self.queue.put("RUNNING")

            start = time.time()
            while not server.done and not self.done:
                server.handle_request()
                now = time.time()
                if now - start > self.timeout:
                    self.done = True

            # If the server is done, we are done as well.
            if server.done:
                server.socket.close()
                self.done = True
                self.result = server.result
            else:
                server.socket.close()
                self.done = True

            self.queue.put("STOPPED")
            self.callback()


        class _RendezvousHandler(BaseRequestHandler):
            def handle(self):
                # self.request is the TCP socket connected to the client
                sock = self.request
                data = bytebundle.read(sock)
                payload = data.decode("utf-8")
                decrypted_payload = \
                  self.server.provider.decrypt_symmetric(payload, self.server.shared_secret)

                rendezvous_info = RendezvousInfo.deserialize(decrypted_payload)

                info_str = self.server.own_rendezvous_info.serialize()
                encrypted_info_str = \
                  self.server.provider.encrypt_symmetric(info_str, self.server.shared_secret)

                bytebundle.send(encrypted_info_str.encode("utf-8"), sock)

                self.server.done = True
                self.server.result = (True, rendezvous_info)
            #END _RendezvousHandler
        #END _RendezvousServer
