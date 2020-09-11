"""
This is a collection of functions, classes and methods usable across different
UI implementations. The contents hereof should be stateless.
"""
import uuid
import datetime
import logging

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

import depeche.contacts.contact as contact

from depeche.crypto.provider_nacl import ProviderNaCl
from depeche.messages.sqlite_storage import SqliteStorage
from depeche.messages.stored_message import StoredMessage
from depeche.communication.protocol.structures import RendezvousInfo
from depeche.communication.protocol.structures import UserMessage
from depeche.communication.adapter.localnet.naive import TcpUdpAdapter

import depeche.communication.protocol.node_intercom as NodeIntercom


def rendezvous_produce_info(db: SqliteStorage,
                            crypto_provider: ProviderNaCl,
                            alias: str) -> (bool, str, RendezvousInfo):
    """
    This is a helper commad used to produce a rendezvous info object for sending
    to a foreign node.
    Return value is the ID of the key used to produce the rendezvous info as
    well as the info object itself.
    """
    # Retrieve a suitable public key to send
    (key_id, public_key) = generate_new_key(db, crypto_provider)

    # Produce address pad - We start with a block of 10 addresses
    address_pad = []
    for _ in range(10):
        adr = "ADR-" + str(uuid.uuid4())
        address_pad.append(adr)
        rendezvous_info = RendezvousInfo(alias=alias, address_pad=address_pad,
                                         public_key=public_key)

    return (True, key_id, rendezvous_info)


def rendezvous_save_info(db: SqliteStorage,
                         key_id: str,
                         own_info: RendezvousInfo,
                         foreign_info: RendezvousInfo) -> bool:
    """
    This helper function will save rendezvous info on success - Returns a success
    report: True if successful, False otherwise.
    """
    # Only one key is to be imported at the moment. Not ideal, but
    # makes key usage a bit lower, saving some electrons for future generations
    contact_id = db.store_contact(foreign_info.alias, own_info.alias)
    contact_key_id = db.store_contact_nacl_key(foreign_info.public_key)

    for adr in foreign_info.address_pad:
        db.store_contact_address(contact_id, adr, contact_key_id)

        # Save the addresses that was sent to counterpart for future use
        for adr in own_info.address_pad:
            db.store_own_address(adr, contact_id, key_id)

        return True


def generate_new_key(db: SqliteStorage, crypto: ProviderNaCl) -> (str, str):
    secret_key, public_key = crypto.generate_key()
    key_id = db.store_own_nacl_key(secret_key, public_key)
    return (key_id, public_key)


def enqueue_user_message(db: SqliteStorage, crypto: ProviderNaCl,
                         destination: contact.Contact, text_data: str,
                         is_sending_address_pad_req: bool = False,
                         is_sending_address_pad: bool = False):
    """
    This function will attempt enqueue a simple message containing a mime-formatted
    text message.
    """
    # By default, we don't append a request for more adresses
    protocol_parts = []

    # Grab first available address for contact
    address_data = db.get_address_pad_nacl(destination.contact_id)[0]

    if is_sending_address_pad_req:
        # We ask for 20 keys, but if our counterpart is running this code,
        # we'll only ever get 10
        protocol_parts.append(NodeIntercom.generate_address_pad_request(20))
    if is_sending_address_pad:
        # Currently, we blatantly disregard the number of addresses requested
        # in any pad request
        protocol_parts.append(_generate_own_address_pad(db, crypto, destination, 10))

    msg = _construct_top_level_mime_message(destination.nickname, destination.alias,
                                            text_data, protocol_parts)

    # Last step: Encrypt and plonk on the "out" tray
    _enqueue_generic_message(db, crypto, address_data, msg)


def exchange_messages_start(db: SqliteStorage, adapter: TcpUdpAdapter,
                            on_exchange_completed: callable = None):
    """
    This command will try a generic exchange sequence consisting of a "dual
    attempt" with both passive and active message exchange methods. It'll
    run in active mode for 30 seconds after which it will stop.
    Concurrently, it'll start listening to other servers, which will continue
    until user interruption (typically by calling exhange_messages_stop).
    """
    cb_handler = _ExchangeCallbackHandler(db, adapter, on_exchange_completed)

    # Announce our presence and be prepared to respond to connection attempts
    adapter.start_message_exchange_server(cb_handler.get_messages_to_send,
                                          cb_handler.on_message_received,
                                          cb_handler.on_exchange_completed)

    # Passively listen
    adapter.start_register_announcements(cb_handler.on_server_announcement)


def exchange_messages_stop(adapter: TcpUdpAdapter):
    """
    This function will stop any server and listener processes currently
    active, meaning the application will be offline after this call has
    terminated.
    """
    adapter.stop_register_announcements()
    adapter.stop_message_exchange_server()


def parse_message(db: SqliteStorage, crypto: ProviderNaCl, message: StoredMessage):
    """
    This function will take a message and return the cleartext contents
    of the message as well as any protocol attachments contained in the
    message: Address pads and requests for pads
    """
    key_id, private_key = db.get_own_address_nacl_key(message.header_address)
    if not private_key:
        # We are trying to parse a message for which we have no key.
        # This is never going to work out well, better to exit early.
        return (None, None, None)

    cleartext = crypto.decrypt(message.contents, private_key)

    # Cleartext is supposed to be a MIME formatted message
    msg = BytesParser(policy=policy.default).parsebytes(cleartext)
    content = []
    address_pad = None
    address_pad_req = None

    for part in msg.walk():
        # Account for stuff we know will turn up - Specifically wrappers and protocol
        # control messages.
        # Please note that we do not currently support multiple address pads / requests in the
        # same message.
        if part.get_content_type() == 'application/json':
            if part['Content-Description'] == NodeIntercom.address_pad_request_description:
                address_pad_req = NodeIntercom.AddressPadRequest.deserialize(part.get_content())
            if part['Content-Description'] == NodeIntercom.address_pad_description:
                address_pad = NodeIntercom.AddressPad.deserialize(part.get_content())
        elif (part.get_content_maintype() == 'multipart' or
              part.get_content_maintype() == 'application'):
            continue
        else:
            content.append(part.get_content())

    msg_string = "From: {0}\nTo: {1}\n\n{2}".format(msg['from'], msg['to'], "\n".join(content))
    return (msg_string, address_pad_req, address_pad)


def import_address_pad(db: SqliteStorage, address_pad: NodeIntercom.AddressPad,
                       own_alias: str) -> None:
    """
    This method will import foreign keys into our database in order for us to be able to send
    messages to the contact identified by the "owner" nickname in the pad - A "real" version of
    this would offer some kind of selection interaction instead of just using the nickname sent
    in the pad.
    """
    contact = db.read_contact_from_nickname(address_pad.from_alias)

    # If the destination is not a known nickname, we'll just create a new one - A better
    # interaction model would be good, but I want this shit done quick.
    if not contact:
        contact_id = db.store_contact(address_pad.from_alias, own_alias)
    else:
        contact_id = contact.contact_id

    for key_mapping in address_pad.key_mappings:
        contact_key_id = db.store_contact_nacl_key(key_mapping.key)
        for adr in key_mapping.address_list:
            db.store_contact_address(contact_id, adr, contact_key_id)


def delete_message(db: SqliteStorage, message_id):
    db.clean_out_received_message(message_id)


############################################################################################
# Private stuff - Helper methods and classes not called directly from external code
############################################################################################

def _enqueue_generic_message(db: SqliteStorage, crypto: ProviderNaCl,
                             to_address: contact.Address, msg: EmailMessage) -> None:
    encrypted_contents = crypto.encrypt(msg.as_bytes(), to_address.public_key)

    message = UserMessage(
        to_address=to_address.address_id,
        send_time=datetime.datetime.now(),
        contents=encrypted_contents)

    db.store_message(message)
    db.mark_contact_address(to_address.address_id)  # Make sure not to re-use addresses


def _generate_own_address_pad(db, crypto, contact: contact.Contact, size: int) -> EmailMessage:
    """
    This method will generate an address pad MIME message. It takes the message
    recipients contact_id as argument as well as the intended size of the address pad.

    This implementation defaults the alias to send along with the address pad to be the
    same as the one registered for the contact - This is not mandated, but probably a
    reasonable guess at what a normal user would expect.
    """
    # Retrieve a suitable public key to send
    (key_id, public_key) = _generate_new_key(db, crypto)

    # Produce address pad - We start with a block of addresses tied to a single key
    # This should probably be a double iterator to make new keys as we need them
    # (typically a new key per handful of addresses)

    address_list = []
    for _ in range(size):
        adr = "ADR-" + str(uuid.uuid4())
        address_list.append(adr)

    key_mapping = NodeIntercom.KeyMapping(public_key, address_list)

    # Persist the new addresses to the database, making sure we can read the messages
    # sent from the contact to us later.
    for adr in address_list:
        db.store_own_address(adr, contact.contact_id, key_id)

    # Remember: contact.alias is the name by which we are known to the contact
    return NodeIntercom.generate_address_pad(contact.alias, [key_mapping])


def _generate_new_key(db, crypto) -> (str, str):
    secret_key, public_key = crypto.generate_key()
    key_id = db.store_own_nacl_key(secret_key, public_key)
    return (key_id, public_key)


def _construct_top_level_mime_message(to_header: str, from_header: str, body_text: str,
                                      attachments: []) -> EmailMessage:
    """
    This method will construct a "standard" MIME message - A multipart
    message where the body text is the first part and possible protocol
    attachments are added after. Please note that the argument "attachments"
    should contain EmailMessage objects only.
    """
    # Make sure that the file contents are crammed into a MIME container
    msg = EmailMessage()
    msg.make_mixed()
    msg['To'] = to_header        # The nickname for them they have given us
    msg['From'] = from_header    # Alias as we are known to them
    msg.add_attachment(body_text)

    for part in attachments:
        msg.attach(part)
    return msg


class _ExchangeCallbackHandler:
    def __init__(self, db: SqliteStorage, adapter: TcpUdpAdapter,
                 on_exchange_completed: callable = None):
        self._logger = logging.getLogger(__name__)
        self._db = db
        self._adapter = adapter

        # Used to communicate to any UI that there might be new messages
        self.on_exchange_completed = on_exchange_completed

    def get_messages_to_send(self):
        self._db.connect_thread()
        stored_messages = self._db.get_messages_to_forward()
        user_messages = [UserMessage(m.header_address, m.header_sent_at, m.contents)
                         for m in
                         stored_messages]
        self._db.disconnect_thread()
        return user_messages

    def on_message_received(self, *args):
        # We really expect only one "user message" to be returned per call. Anything else
        # is an error. Some strong typing would be in order. Python 3.4 says no.
        message = args[0]
        self._logger.info("Message received: {}".format(message))
        self._db.connect_thread()
        self._db.store_message(message)
        self._db.disconnect_thread()
        self._logger.info("Message stored.")

    def on_server_announcement(self, *args):
        """
        Callback when a server announcement is picked up we'll try to exchange messages
        with it. If we find any, we'll signal the UI that there might be new stuff to display
        to the user.
        """
        host, port = args
        user_messages = self.get_messages_to_send()

        self._logger.debug("Messages slated for exchange: " + str(user_messages))

        self._adapter.exchange_messages_with_server(
            (host, port),
            user_messages,
            self.on_message_received)

        if self.on_exchange_completed is not None:
            self.on_exchange_completed()
