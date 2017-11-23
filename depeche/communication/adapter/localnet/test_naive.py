"""
Test cases for the "naive" UDP/TCP networking implementation
"""

import uuid
import time
import unittest
import threading

from depeche.crypto.provider_nacl import ProviderNaCl
from depeche.communication.protocol.structures import RendezvousInfo
from depeche.communication.protocol.structures import UserMessage
from depeche.communication.adapter.localnet.naive import TcpUdpAdapter

import sys
import logging

logger = logging.getLogger()
logger.level = logging.DEBUG

class TestRendezvous(unittest.TestCase):

    def setUp(self):
        stream_handler = logging.StreamHandler(sys.stdout)
        logger.addHandler(stream_handler)


    def tearDown(self):
        stream_handler = logging.StreamHandler(sys.stdout)
        logger.removeHandler(stream_handler)


    def test_rendezvous(self):
        client_alpha = self.PeerNodeThread("alpha", 27275)
        client_alpha.start()

        # Actual time slept should not matter, as long as it's short enough to not cause time-outs
        time.sleep(1)

        client_beta = self.PeerNodeThread("beta", 27275)
        client_beta.start()

        client_alpha.join()
        client_beta.join()

        self.assertTrue(client_alpha.success)
        self.assertTrue(client_beta.success)
        # Aaaaand we should be done


    class PeerNodeThread(threading.Thread):
        def __init__(self, alias: str, listen_port: int):
            self._alias = alias
            self._port = listen_port
            self.success = False

            threading.Thread.__init__(self)


        def run(self):
            success, other_info = TestRendezvous.rendezvous_sequence(self._alias, self._port)
            self.success = success


    def rendezvous_sequence(alias: str, port: int):
        """
        Both test "clients" will basically perform the same sequence of events - Timing
        should not matter as various race conditions should be accounted for in the code
        being tested.
        """
        crypto_provider = ProviderNaCl()
        communication_adapter = TcpUdpAdapter(crypto_provider, port)

        # Begin with something really secret!
        secret = "a really secret secret"
        # Produce address pad - this may be any string, but we'll keep it realistic!
        address_pad = []
        for _ in range(10):
            adr = "ADR-" + str(uuid.uuid4())
            address_pad.append(adr)
        # As the public key is not actually going ti be used for anything, we just make some
        # shit up. Both 'sides' using the same should have no adverse effects.
        public_key = "38464abd34f4556aa34"

        rendezvous_info = RendezvousInfo(alias=alias,
                                         address_pad=address_pad,
                                         public_key=public_key)

        # And now for the REAL McCoy
        success, other_info = communication_adapter.rendezvous(secret, rendezvous_info)

        # Then we let the caller sort out how to respond
        return (success, other_info)
