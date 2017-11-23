# -*- coding: utf-8 -*-
"""
Test cases for the NaCl crypto provider class
"""

import time
import unittest
import logging
logging.basicConfig(level=logging.DEBUG)

from nacl import public
from depeche.crypto.provider_nacl import ProviderNaCl

class TestProviderNaCl(unittest.TestCase):
    "Test case extension for NaCl provider"

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_asymmetric_encryption_and_decryption(self):
        # Test case specific setUp
        provider = ProviderNaCl()
        private_key_str = provider.generate_key()

        ## Trixy bit - Normally we have a serialized public key available (saved after
        ## rendezvoux) but here we have to retrieve one
        private_key = ProviderNaCl._deserialize_private_key(private_key_str)
        public_key = private_key.public_key
        public_key_str = ProviderNaCl._serialize_public_key(public_key)

        test_string = """\
        an example string to encrypt
        including line breaks, etc

        also: exotic characters!
        åäö
        ㅏ매아내ㅐ
        """

#        print("String before encryption")
#        print(test_string)

        encrypted_string = provider.encrypt(test_string, public_key_str)

#        print("String after encryption")
#        print(encrypted_string)
        decrypted_string = provider.decrypt(encrypted_string, private_key_str)
#        print("String after decryption")
#        print(decrypted_string)

        self.assertEqual(test_string, decrypted_string)


    def test_symmetric_encryption_and_decryption(self):
        provider = ProviderNaCl()

        test_string = """\
        an example string to encrypt
        including line breaks, etc

        also: exotic characters!
        åäö
        ㅏ매아내ㅐ
        """

        shared_secret = "a-secret-well-kept"

#        print("String before encryption")
#        print(test_string)

        encrypted_string = provider.encrypt_symmetric(test_string,
                                                      shared_secret)
#        print("String after encryption")
#        print(encrypted_string)

        decrypted_string = provider.decrypt_symmetric(encrypted_string,
                                                      shared_secret)
#        print("String after decryption")
#        print(decrypted_string)

        self.assertEqual(test_string, decrypted_string)


    def test_key_searialization(self):
        provider = ProviderNaCl()
        key = public.PrivateKey.generate()

        str_key = ProviderNaCl._serialize_private_key(key)
#        print("Stringified key is:", str_key)

        reconstituted_key = ProviderNaCl._deserialize_private_key(str_key)

        self.assertEqual(key, reconstituted_key)
