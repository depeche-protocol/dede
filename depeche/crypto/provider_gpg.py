# -*- coding: utf-8 -*-
"""
This is a provider for crypto functions - It merely wraps gpg in a
thin layer of python. In point of fact, it cheats and uses the
python-gpg module, exposing a uniform set of functions that other
encryption modules might also support.
"""

from os.path import expanduser
from depeche.crypto.python_gpg import gnupg

DEFAULT_SYMMETRIC_CIPHER = "AES256"
DEFAULT_KEYRING_LOCATION = expanduser("~") + "/.depeche/depeche.gpg"

class ProviderGpg:

    def __init__(self, keyring_location=DEFAULT_KEYRING_LOCATION):
        self._gpg = gnupg.GPG(keyring=keyring_location)
        self._gpg.encoding = 'utf-8'

    def encrypt_symmetric(self, data: str, shared_secret: str,
                          cipher=DEFAULT_SYMMETRIC_CIPHER) -> str:
        ascii_encrypted_data = self._gpg.encrypt(
            data,
            [],
            symmetric=cipher,
            passphrase=shared_secret)
        return str(ascii_encrypted_data)


    def decrypt_symmetric(self, data: str, shared_secret: str,
                          cipher=DEFAULT_SYMMETRIC_CIPHER) -> str:
        """Decrypts a block of encrypted data with the shared secret as key"""
        decrypted_data = self._gpg.decrypt(data, passphrase=shared_secret)
        return str(decrypted_data)


    def encrypt(self, data, key_id) -> str:
        """Will encrypt a chunk of textual data"""
        ascii_encrypted_data = self._gpg.encrypt(data, key_id, hidden_recipient=True)
        return str(ascii_encrypted_data)


    def decrypt(self, data) -> str:
        """Will decrypt an ascii armored pgp message"""
        decrypted_data = self._gpg.decrypt(data)
        return str(decrypted_data)


    def generate_key(self, alias):
        """
        Will generate a key using default, recommended, values for the
        given alias. This will serve as part of generating an "pseudonym",
        a virtual identity. Other steps include, for example, generating
        an address pad for the pseudonym.
        """
        input_data = self._gpg.gen_key_input(
            key_type="RSA",
            key_length=1024,
            name_email=alias,
            name_comment="",
            expire_date="60d")
        key = self._gpg.gen_key(input_data)
        return key.fingerprint


    def import_key(self, key_data):
        """
        Will import a given keys. The 'key_string' argument is an ascii
        armoured string, as per the OpenPGP specification.
        """
        result = self._gpg.import_keys(key_data)
        return result.fingerprints


    def export_key(self, key_id):
        """
        Will export the public part of a known key. This is used both for
        rendezvous and for forwarding known contact data.
        """
        return self._gpg.export_keys(key_id)


    def deprecate_key(self, key_id):
        """
        Will cause a key to be removed from use. This does not imply
        actual deletion - If there are any messages held that use this
        key, the key will be retained for future decryption of those
        messages.
        """
        pass


    def delete_key(self, key_id):
        """
        Will cause an actual deletion of a key from the key database.
        This _might_ render a pseudonym defunct, as messages sent from/to
        will be unrecoverable - Pseudonym database might also desync from
        key database. Use with care.
        """
        self._gpg.delete_keys(key_id, True)
