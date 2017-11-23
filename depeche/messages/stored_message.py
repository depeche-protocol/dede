"""
This module contains the class detailing how an internally stored message looks.
Please note that the stored format of a given message differs from the transmitted
(line) format, due to metadata storage needs and other considerations.
"""

import datetime

class StoredMessage:
    """
    This class is meant for messages read from the database/persistent storage. It is a
    superset of the structures.UserMessage, as it contains meta-information about the
    message, such as when the message was received, number of times forwarded etc.
    Instances of this class are produced from DB reads and transformed into "UserMessage"s
    before being exchanged with a foreign node.
    """

    def __init__(self):
        self._message_id = None        # Hash(contents) serving as ID for the message
        self._received_at = None       # DateTime describing when we were first sent this message
        self._last_seen_at = None      # DateTime describing the last time we were sent this message
        self._forward_count = 0        # Count of how many times this message has been forwarded
        self._header_address = None    # destination address header
        self._header_sent_at = None    # sent_at header, stored here as a DateTime
        self._contents = None          # Encrypted contents of the message

    @property
    def id(self) -> str:
        return self._message_id

    @id.setter
    def id(self, to_set: str):
        self._message_id = to_set

    @property
    def received_at(self) -> datetime:
        return self._received_at

    @received_at.setter
    def received_at(self, to_set: datetime):
        self._received_at = to_set

    @property
    def last_seen_at(self) -> datetime:
        return self._last_seen_at

    @last_seen_at.setter
    def last_seen_at(self, to_set: datetime):
        self._last_seen_at = to_set

    @property
    def forward_count(self) -> int:
        return self._forward_count

    @forward_count.setter
    def forward_count(self, to_set: int):
        self._forward_count = to_set

    @property
    def header_address(self) -> str:
        return self._header_address

    @header_address.setter
    def header_address(self, to_set: str):
        self._header_address = to_set

    @property
    def header_sent_at(self) -> datetime:
        return self._header_sent_at

    @header_sent_at.setter
    def header_sent_at(self, to_set: datetime):
        self._header_sent_at = to_set

    @property
    def contents(self) -> str:
        return self._contents

    @contents.setter
    def contents(self, to_set:str):
        self._contents = to_set
