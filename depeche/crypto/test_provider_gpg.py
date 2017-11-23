# -*- coding: utf-8 -*-
"""
Test cases for the GPG crypto provider class
"""

import time
import unittest
import logging
logging.basicConfig(level=logging.DEBUG)

from depeche.crypto.provider_gpg import ProviderGpg

class TestProviderGPG(unittest.TestCase):
    "Test case extension for gpg provider"

    def setUp(self):
        pass

    def tearDown(self):
        pass

    @unittest.skip("GPG deprecated - skipping test")
    def test_asymmetric_encryption_and_decryption(self):
        # Test case specific setUp
        provider_gpg = ProviderGpg()

        self.fingerprint = provider_gpg.generate_key("tester")

        test_string = """\
        an example string to encrypt
        including line breaks, etc

        also: exotic characters!
        åäö
        ㅏ매아내ㅐ
        """

        print("String before encryption")
        print(test_string)

        encrypted_string = provider_gpg.encrypt(test_string,
                                                self.fingerprint)

        print("String after encryption")
        print(encrypted_string)
        decrypted_string = provider_gpg.decrypt(encrypted_string)
        print("String after decryption")
        print(decrypted_string)

        self.assertEqual(test_string, decrypted_string)

        # Test case specific tearDown
        provider_gpg.delete_key(self.fingerprint)


    @unittest.skip("GPG deprecated - skipping test")
    def test_symmetric_encryption_and_decryption(self):
        provider_gpg = ProviderGpg()

        test_string = """\
        an example string to encrypt
        including line breaks, etc

        also: exotic characters!
        åäö
        ㅏ매아내ㅐ
        """

        shared_secret = "a-secret-well-kept"

        print("String before encryption")
        print(test_string)

        encrypted_string = provider_gpg.encrypt_symmetric(test_string,
                                                          shared_secret)
        print("String after encryption")
        print(encrypted_string)

        decrypted_string = provider_gpg.decrypt_symmetric(encrypted_string,
                                                          shared_secret)
        print("String after decryption")
        print(decrypted_string)

        self.assertEqual(test_string, decrypted_string)
