# -*- coding: utf-8 -*-
"""
This is a provider for crypto functions - It wraps nacl in a
a uniform set of functions that other encryption modules might also
support.
"""
import nacl

from os.path import expanduser
from nacl import secret, public, utils, hash, encoding

class ProviderNaCl:

    def __init__(self):
        pass

    def encrypt_symmetric(self, data: str, shared_secret: str) -> str:
        """
        Encrypts the data string sent in and returns a BASE64 encoded string suitable
        for network transfer or storage
        """
        key = nacl.hash.blake2b(shared_secret.encode('utf-8'),
                            digest_size=secret.SecretBox.KEY_SIZE,
                            encoder=encoding.RawEncoder)

        box = nacl.secret.SecretBox(key)
        encrypted_bytes = box.encrypt(data.encode('utf-8'), encoder=nacl.encoding.Base64Encoder)

        return encrypted_bytes.decode('ascii')


    def decrypt_symmetric(self, data: str, shared_secret: str) -> str:
        """Decrypts a block of encrypted data with the shared secret as key"""
        key = nacl.hash.blake2b(shared_secret.encode('utf-8'),
                                digest_size=secret.SecretBox.KEY_SIZE,
                                encoder=encoding.RawEncoder)

        box = nacl.secret.SecretBox(key)
        encrypted_bytes = data.encode('ascii')

        decrypted_data = box.decrypt(encrypted_bytes, encoder=encoding.Base64Encoder)
        return decrypted_data.decode('utf-8')


    def encrypt_to_str(self, data: str, public_key: str) -> str:
        """
        Will encrypt a chunk of textual data using the public key given. Generally,
        the public key will belong to a foreign node and the message can thus NOT be
        decrypted by this node and the contents are un-recoverable.
        """
        binary_data = data.encode('utf-8')
        return self.encrypt(binary_data, public_key)


    def encrypt(self, data: bytes, public_key: str) -> str:
        """
        Will encrypt a chunk of textual data using the public key given. Generally,
        the public key will belong to a foreign node and the message can thus NOT be
        decrypted by this node and the contents are un-recoverable.
        """
        binary_key = ProviderNaCl._deserialize_public_key(public_key)

        box = nacl.public.SealedBox(binary_key)
        encrypted_bytes = box.encrypt(data, encoder=nacl.encoding.Base64Encoder)
        return encrypted_bytes.decode('ascii')


    def decrypt_to_str(self, data, private_key: str) -> str:
        """
        Will decrypt a message with the given private key - Success only if the key
        given was actually used to encrypt the message.
        """
        return self.decrypt(data, private_key).decode('utf-8')


    def decrypt(self, data, private_key: str) -> bytes:
        """
        Will decrypt a message with the given private key - Success only if the key
        given was actually used to encrypt the message.
        """
        binary_key = ProviderNaCl._deserialize_private_key(private_key)

        box = nacl.public.SealedBox(binary_key)
        decrypted_bytes = box.decrypt(data.encode('ascii'), encoder=nacl.encoding.Base64Encoder)
        return decrypted_bytes


    def generate_key(self) -> (str, str):
        """
        Will generate a key using default, recommended, values for the
        given alias. This will serve as part of generating an "pseudonym",
        a virtual identity. Other steps include, for example, generating
        an address pad for the pseudonym.
        Returns a tuple, containing a ([secret key], [public key]) pair
        """
        key = nacl.public.PrivateKey.generate()
        return (ProviderNaCl._serialize_private_key(key),
                    ProviderNaCl._serialize_private_key(key.public_key))


    ## Private utility functions

    def _serialize_private_key(key: public.PrivateKey) -> str:
        str_key = key.encode(encoder=nacl.encoding.HexEncoder).decode('ascii')
        return str_key

    def _deserialize_private_key(str_key: str) -> public.PrivateKey:
        key = nacl.public.PrivateKey(str_key.encode('ascii'), encoder=nacl.encoding.HexEncoder)
        return key

    def _serialize_public_key(key: public.PublicKey) -> str:
        str_key = key.encode(encoder=nacl.encoding.HexEncoder).decode('ascii')
        return str_key

    def _deserialize_public_key(str_key: str) -> public.PublicKey:
        key = nacl.public.PublicKey(str_key.encode('ascii'), encoder=nacl.encoding.HexEncoder)
        return key
