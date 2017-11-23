"""
This file contains data structures that adapters may use to regulate
their flow of communications. The structures herein should work on
the application level, not the adapter level. Thus, no byte-shuffling
and, for example, NFC-specific stuff - Those things should be owned
by the using adapters.
"""

import uuid
import json
import datetime

class RendezvousInfo:
    """Data container for protocol data involved in rendezvous"""

    def __init__(self, **args):

        alias = args.get('alias', None)
        address_pad = args.get('address_pad', None)
        public_key = args.get('public_key', None)
        serialized_form = args.get('serialized_form', None)

        if not (alias is None or
                address_pad is None or
                public_key is None):
            self._alias = alias
            self._address_pad = address_pad
            self._public_key = public_key
        elif not (serialized_form is None):
            self.deserialize(serialized_form)
        else:
            raise RuntimeError("Faulty arguments passed")


    @property
    def alias(self) -> str:
        """Getter for alias"""
        return self._alias


    @property
    def address_pad(self) -> list:
        """Getter for address pad"""
        return self._address_pad


    @property
    def public_key(self) -> str:
        """Getter for public key"""
        return self._public_key


    def serialize(self) -> str:
        contents = json.dumps({
            "type": "rendezvous_info",
            "alias": self._alias,
            "address_pad": self._address_pad,
            "public_key": self._public_key
            }, ensure_ascii=False)
        return contents


    @staticmethod
    def deserialize(serialized_form):
        """JSON parser does the dirty work plus some safety checks"""
        obj = json.loads(serialized_form)

        if not (obj["type"] == "rendezvous_info") or \
            obj["alias"] is None or \
            obj["address_pad"] is None or \
            obj["public_key"] is None:
            raise RuntimeError("String cannot be deserialied into a valid RendezvousInfo")

        result = RendezvousInfo(alias=obj["alias"],
                                address_pad=obj["address_pad"],
                                public_key=obj["public_key"])
        return result


    def to_string(self) -> str:
        """Basic strinigfication of values"""
        return str(self._alias + "(" + self._public_key[:32] + ")")


class_mapping = {}

class MessageContainer:
    """
    This is simply a container for messages used to encapsulate
    a sequence of messages sent together. depeche does not mandate
    any bundling of messages, but this might be done to save bandwidth.
    The message container is envisaged as a "file" type object
    in depeche. Adapters using files should have message containers
    as top-level transfer units during message exchange.

    Any message sent during message exchange must be wrapped in a
    container (simply a json list) to ensure parser compatibility.

    Order of messages within the container is not important, they
    are all considered to have arrived simultaneously.
    """
    def __init__(self, messages):
        self.messages = messages

    def serialize(self) -> str:
        """Serialization is simply a json list of messages"""
        contents = [x.serialize() for x in self.messages]
        return "[" + ','.join(contents) + "]"

    @staticmethod
    def deserialize(serialized_form: str):
        """
        Just return the deserialization - json module will handle
        parsing problems
        """
        json_array = json.loads(serialized_form)

        message_list = []
        for message_dict in json_array:
            msg_class = class_mapping[message_dict["type"]]
            message_list.append(msg_class.deserialize(json.dumps(message_dict)))

        return message_list


class DepecheMessage:
    """
    This is the base class of all types of messages in the "message
    exchange" sequence of events.
    """
    def __init__(self):
        self.type = None                   # Abstract type
        self.exchange_ref = str(uuid.uuid4())

    def serialize(self, d={}) -> str:
        """Serialization is simply a basic json dictionary"""

        d["type"] = self.type
        d["exchange_ref"] = self.exchange_ref

        contents = json.dumps(d, ensure_ascii=False)
        return contents

    @staticmethod
    def deserialize(serialized_form: str):
        """
        Just return the deserialization - json module will handle
        parsing problems. obj argument is subclass-supplied object
        containing the parse result for lower-level classes.
        """
        json_dict = json.loads(serialized_form)
        obj = DepecheMessage()
        obj.type = json_dict["type"]
        obj.exchange_ref = json_dict["exchange_ref"]
        return obj


class UserMessage(DepecheMessage):
    """
    A user message is a "real" message - This data structure contains
    the actual data we A) want to forward to a foreign node  or B) receive from
    a foreign node.
    """
    def __init__(self, to_address: str, send_time: datetime.datetime, contents: str):
        DepecheMessage.__init__(self)
        self.type = "user_message" # Override type

        self.to_address = to_address
        self.send_time = send_time
        self.contents = contents

    def serialize(self, d={}):
        d["to_address"] = self.to_address
        d["send_time"] = self.send_time.isoformat()
        d["contents"] = self.contents

        return DepecheMessage.serialize(self, d)

    @staticmethod
    def deserialize(serialized_form: str):
        """
        Just return the deserialization - json module will handle
        parsing problems
        """
        json_dict = json.loads(serialized_form)
        send_time = datetime.datetime.strptime(json_dict["send_time"], "%Y-%m-%dT%H:%M:%S.%f")

        obj = UserMessage(json_dict["to_address"],
                          send_time,
                          json_dict["contents"])
        obj.exchange_ref = json_dict["exchange_ref"]

        return obj


class_mapping["user_message"] = UserMessage


################ Flow control for Message Exchange #################

class FlowControlMessage(DepecheMessage):
    """
    This is the superclass of all flow control messages needed to
    regulate the message exchange process. Flow control messages
    should never require persistence, and should only be used
    during the message exchange sequence to regulate flow of
    data/files between the nodes.
    """
    def __init__(self):
        DepecheMessage.__init__(self)
        self.type = None              # Abstract type


    def serialize(self, d={}):
        return DepecheMessage.serialize(self, d)


class StopSending(FlowControlMessage):
    """
    A request to stop sending data - This is a courtesy: The receiving
    node may of course stop saving data and just pipe it to /dev/null.
    This message is wholly meant to save bandwidth/transfer time.
    """
    message_type = "stop_sending"

    def __init__(self):
        FlowControlMessage.__init__(self)
        self.type = StopSending.message_type

class_mapping["stop_sending"] = StopSending


class NoMoreData(FlowControlMessage):
    """
    A "reply" message sent after receiving a transfer unit, when the
    receiving node has no data to send back to the originator
    """
    message_type = "no_more_data"

    def __init__(self):
        FlowControlMessage.__init__(self)
        self.type = NoMoreData.message_type

class_mapping["no_more_data"] = NoMoreData
