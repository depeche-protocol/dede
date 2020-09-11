"""
This is the class containing the functionality for a "contact" in
the depeche system. It handles address pads (both own and external)
as well as interfaces with the gpg DB for key retrieval etc.
"""


class Contact:
    """Collector for funtionality concerning known contacts"""

    def __init__(self):
        self._nickname = None
        self._alias = None
        self._contact_id = None
        self._created_at = None

    @property
    def contact_id(self):
        return self._contact_id

    @contact_id.setter
    def contact_id(self, to_set: str):
        self._contact_id = to_set

    @property
    def nickname(self):
        return self._nickname

    @nickname.setter
    def nickname(self, to_set: str):
        self._nickname = to_set

    @property
    def alias(self):
        return self._alias

    @alias.setter
    def alias(self, to_set: str):
        self._alias = to_set

    @property
    def created_at(self):
        return self._created_at

    @created_at.setter
    def created_at(self, to_set: str):
        self._created_at = to_set

    @property
    def address_pad(self) -> list:
        """The address pad returned is a list of Address objects"""
        pass

    @property
    def key_fingerprint(self):
        pass


class Address:
    """Container for address information"""

    def __init__(self, address_id: str, key_id: str, private_key: str=None, public_key: str=None):
        self._address_id = address_id
        self._key_id = key_id
        self._private_key = private_key
        self._public_key = public_key

    @property
    def address(self) -> str:
        return self._address_id

    @property
    def address_id(self) -> str:
        return self._address_id

    @property
    def key_id(self) -> str:
        """
        This returns the internal ID of the key - This ID is useless for any other nodes/clients,
        and only intended for use here. Do not expose this ID through any network interactions
        """
        return self._key_id

    @property
    def public_key(self) -> str:
        """
        This returns a serialization of the public key - For usage when encrypting messages to the
        address. As an address should obly be bound to a single key, no matter of it is "own" or
        ""foreign"
        """
        return self._public_key

    @property
    def private_key(self) -> str:
        """
        This returns a serialization of the public key - For usage when encrypting messages to the
        address. As an address should obly be bound to a single key, no matter of it is "own" or
        ""foreign"
        """
        return self._private_key
