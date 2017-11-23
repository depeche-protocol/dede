"""
This file contains methods and data structures concerning node-to-node intercommunication.
Examples of which: Requests for more addresses and resulting outbound address pads, voice server
requests and replies, third-party introductions, self-introductions.
"""

import uuid
import json

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser, Parser


## Some strings that need to be the same all over the place
address_pad_request_description = 'depeche/address_pad_request'
address_pad_description = 'depeche/address_pad'


def generate_address_pad_request(requested_size: int) -> EmailMessage:
    """
    This function will generate a MIME-formatted message containing an address pad request.
    In general, this will be a part of a multipart message, where the enclosing email
    will give the recipient inforation about who claims to have sent it and possibly other
    parts containing an address pad and a user-readable message.
    """
    # Everything is an email message!
    msg = EmailMessage()
    msg.set_content(AddressPadRequest(requested_size).serialize())
    msg.replace_header('Content-Type', 'application/json')
    msg.add_header('Content-Description', address_pad_request_description)
    return msg


def generate_address_pad(owner: str, key_mappings: []) -> EmailMessage:
    """
    This function will generate a MIME-formatted message containing an address pad. The addresses
    should originate from the node operator known by the nickname in the "owner" argument.
    Please note the it is a common use-case to introduce a user (A) to another user (B) by sending
    some of user A's addresses along so that user B can establish contact themselves.
    """
    pad = AddressPad(owner)
    for mapping in key_mappings:
        pad.add_key_mapping(mapping)

    msg = EmailMessage()
    msg.set_content(pad.serialize())
    msg.replace_header('Content-Type', 'application/json')
    msg.add_header('Content-Description', address_pad_description)
    return msg


class AddressPadRequest:
    """Data container for requesting a new address pad from a contact"""

    def __init__(self, pad_size: int=10):
        self._pad_size = pad_size


    @property
    def pad_size(self) -> int:
        """Getter for requested pad size"""
        return self._pad_size


    def serialize(self) -> str:
        contents = json.dumps({
            "type": "address_pad_request",      # Will also be in the MIME header, but hey!
            "requested_size": self.pad_size,    # You may REQUEST any size, but you get what you get
            }, ensure_ascii=False)
        return contents


    @staticmethod
    def deserialize(serialized_form):
        obj = json.loads(serialized_form)

        if not (obj["type"] == "address_pad_request") or \
            obj["requested_size"] is None:
            raise RuntimeError("String cannot be deserialied into a valid AddressPadRequest")

        return AddressPadRequest(pad_size=obj["requested_size"])


class KeyMapping:
    """
    This data container is intended as a holder of the key->address relationship. It enables
    multiple addresses for a given key, but even if such a thing is possible a minimum of
    key reuse is recommended.
    """
    def __init__(self, key: str, addresses: []=[]):
        self._key = key
        self._addresses = addresses


    @property
    def key(self) -> str:
        return self._key


    @property
    def address_list(self) -> []:
        return self._addresses


    def add_address(self, to_add: str) -> None:
        self._addresses.append(to_add)


    def get_generic_form(self) -> {}:
        return {
            "key": self._key,
            "addresses": self.get_generic_address_list(),
            }


    def get_generic_address_list(self):
        generic_list = []
        for adr in self._addresses:
            generic_list.append(adr)
        return generic_list


    @staticmethod
    def from_generic_form(obj: {}):
        adr_set = []
        for adr in obj["addresses"]:
            adr_set.append(adr)
        result = KeyMapping(obj["key"], adr_set)
        return result


class AddressPad:
    """
    Data container for transporting an address pad to to a foreign node or, conversely for
    receiving and possibly importing foreign addresses.
    This is a slightly better version of the address pad sent in the rendezvous info.
    """
    def __init__(self, from_alias: str):
        self._from_alias = from_alias
        self._key_mappings = []


    @property
    def key_mappings(self) -> []:
        return self._key_mappings


    @property
    def from_alias(self) -> str:
        return self._from_alias


    def add_key_mapping(self, key_mapping: KeyMapping) -> None:
        self._key_mappings.append(key_mapping)


    def serialize(self) -> str:
        contents = json.dumps(self.get_generic_form(), ensure_ascii=False)
        return contents


    def get_generic_form(self):
        return {
            "type": "address_pad",
            "owner": self._from_alias,
            "mappings": self.get_generic_key_list(),
            }


    def get_generic_key_list(self):
        generic_list = []
        for kal in self._key_mappings:
            generic_list.append(kal.get_generic_form())
        return generic_list


    def from_generic_form(obj: {}):
        result = AddressPad(obj["owner"])
        for m in obj["mappings"]:
            result.add_key_mapping(KeyMapping.from_generic_form(m))
        return result


    @staticmethod
    def deserialize(serialized_form):
        """JSON parser does the dirty work plus some safety checks"""
        obj = json.loads(serialized_form)

        if not (obj["type"] == "address_pad"):
            raise RuntimeError("String cannot be deserialied into a valid AddressPad")

        result = AddressPad.from_generic_form(obj)
        return result
