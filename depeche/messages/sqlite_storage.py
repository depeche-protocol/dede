"""
This module is an storage implementation using sqlite. It has sqlite
as a requirement (d'uh) - For other platforms than linux, sqlite
might be included as a redistributable.
"""

import sqlite3
import os
import hashlib
import uuid
import logging
import threading

import depeche.communication.protocol.structures as structures
import depeche.messages.stored_message as stored_message
import depeche.contacts.contact as contact

DB_VERSION = "0.2"
DB_FILE_NAME = os.path.expanduser("~") + "/.depeche/depeche.db"


def _connect_db(fname = DB_FILE_NAME) -> sqlite3.Connection:
    """Creates a connection to the database"""
    conn = sqlite3.connect(fname, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;') # Always, use FK:s. Always.
    return conn


def _create_db(fname = DB_FILE_NAME):
    """If no db file is present, this method is used to create and initialize a new one"""
    logging.info("Creating new ddep database in file.")

    db_file = open(fname, 'w')
    db_file.close()

    conn = _connect_db(fname)
    _create_tables(conn)


def _create_tables(conn: sqlite3.Connection):
    """Creates a fresh database with requisite schema"""
    # Metainformation table
    conn.execute("create table db_info("
                 "version      TEXT, "
                 "created_at   TEXT)")
    conn.execute("INSERT INTO db_info VALUES( '" + DB_VERSION + "', datetime('now'))")

    # Contact table
    conn.execute("create table contact( "
                 "id           TEXT PRIMARY KEY, "   # Internal ID. Just a random UUID.
                 "nickname     TEXT, "               # Nickname, as set by owner of this node
                 "alias        TEXT, "               # Alias, the name the contact knows us by
                 "created_at   TEXT, "               # Creation date
                 "modified_at  TEXT) ")              # Modification date

    # Key table
    conn.execute("create table nacl_key( "
                 "id           TEXT PRIMARY KEY, "   # Internal ID. Just a random UUID.
                 "is_own       INTEGER, "            # True if the key belongs to this node
                 "private_key  TEXT, "               # Private part of the key - Should be present for own keys
                 "public_key   TEXT) ")              # Public part of the key - Should be present for non-own keys

    # Foreign address table
    conn.execute("create table foreign_address( "
                 "id           TEXT PRIMARY KEY, "   # The actual address string. Unique.
                 "contact_id   TEXT, "               # Foreign key. Denotes whom this address leads to
                 "key_id       TEXT, "               # Foreign key. Gives what key should be used to encrypt messages to this address
                 "is_used      INTEGER, "            # True if a message has been sent to this address already
                 "FOREIGN KEY(contact_id) REFERENCES contact(id), "
                 "FOREIGN KEY(key_id) REFERENCES nacl_key(id))")

    # Own address table
    conn.execute("create table own_address( "
                 "id           TEXT PRIMARY KEY, "   # The actual address string. Unique.
                 "given_to     TEXT, "               # Foreign key. Points to a contact in the table that has been sent this address for use. NULL if the address is available for use.
                 "key_id       TEXT, "               # Foreign key. Points to the key that should be used by a foreign node using this address for a message
                 "is_used      INTEGER, "            # True if a message has been received to this address.
                 "FOREIGN KEY(given_to) REFERENCES contact(id), "
                 "FOREIGN KEY(key_id) REFERENCES nacl_key(id))")

    # Message table
    conn.execute("create table message("
                 "id             TEXT PRIMARY KEY, " # ID (in fact hash(contents)) of the message
                 "meta_received_at     TIMESTAMP, "  # When it was first received
                 "meta_last_seen_at    TIMESTAMP, "  # When it was last received
                 "meta_forward_count   INTEGER, "    # A count of how many times this node has forwarded this message
                 "header_address       TEXT, "       # "address" header
                 "header_sent_at       TIMESTAMP, "  # "sent_at" header
                 "body_contents        TEXT)")       # Encrypted contents of the message

    conn.commit()


def _detect_db(fname = DB_FILE_NAME) -> bool:
    """Detects presence of message/contact database file"""
    return os.path.exists(fname)


def _verify_db(conn: sqlite3.Connection) -> bool:
    """
    Verifies that the DB found is consistent with current version
    Please note that this method currently does not verify schema, only version
    number. To be improved upon if time allows.
    """
    curs = conn.cursor()

    try:
        curs.execute("SELECT version FROM db_info LIMIT 1")
        for row in curs:
            if row[0] != DB_VERSION:
                print(row[0] + "\n")
                return False
        return True
    except sqlite3.OperationalError:
        return False


def row_to_message(row) -> stored_message.StoredMessage:
    """
    Extracts a Stored message from a row of the message table.
    """
    result = stored_message.StoredMessage()
    result.id = row["id"]
    result.last_seen_at = row["meta_last_seen_at"]
    result.received_at = row["meta_received_at"]
    result.forward_count = row["meta_forward_count"]
    result.header_address = row["header_address"]
    result.header_sent_at = row["header_sent_at"]
    result.contents = row["body_contents"]
    return result


def row_to_user_message(row) -> structures.UserMessage:
    """
    Extracts a user message from a row of the message table.
    """
    result = structures.UserMessage(
        row["header_address"],
        row["header_sent_at"],
        row["body_contents"])
    return result


class SqliteStorage:
    """
    This class keeps DB state and connection. Please note that it is not curently thread safe
    """

    def __init__(self, fname=DB_FILE_NAME):
        self._logger = logging.getLogger(__name__)

        if not _detect_db(fname):
            _create_db(fname)

        self._db_file_name = fname

        self._connections = dict()

        self.connect_thread()

        if not _verify_db(self._get_conn()):
            self.disconnect_thread()
            raise RuntimeError("Message database of wrong version detected.")


    def connect_thread(self):
        self._connections[threading.get_ident()] = _connect_db(self._db_file_name)
        self._logger.info("DB connection for thread created: {}".format(threading.get_ident()))


    def disconnect_thread(self):
        self._get_conn().close()
        self._connections[threading.get_ident()] = None


    def _get_conn(self) -> sqlite3.Connection:
        result = self._connections[threading.get_ident()]
        assert(result)
        return result


    def store_message(self, message: structures.UserMessage) -> str:
        """Stores a message for future forwarding to other nodes"""
        message_id = hashlib.sha256(message.contents.encode()).hexdigest()
        try:
            self._get_conn().execute("INSERT INTO message VALUES(?,datetime('now'),datetime('now'),0,?,?,?)",
                                     (message_id,
                                      message.to_address,
                                      message.send_time,
                                      message.contents))
            self._get_conn().commit()
        except sqlite3.IntegrityError:
            self._logger.info("Message already exists in DB: {0}".format(message_id))
        return message_id


    def clean_out_received_message(self, message_id: str) -> None:
        """
        Removes the address that the given message was sent to. This is needed to truly
        remove the message, as it would otherwise appear again whenever we recieve
        a copy during message exchange. Also, removing the actual message might leak
        information to nodes we subsequently exchange messages with.
        Additionally, the method will remove the key associated with the address if there
        are no other addresses that refer to that key.
        """
        msg = self.read_message(message_id)
        key_id, _ = self.get_own_address_nacl_key(msg.header_address)

        if key_id == None:
            # Apparently we are trying to clean out a message that need no cleaning out.
            # Possibly grounds for throwing an exception, since user seems confused.
            self._logger.info(
                "Clean out called on message ID not bound to a key: {0}".format(message_id))
            return

        self.remove_own_address(msg.header_address)

        # Ok, now we are rid of the address - The message cannot easily be associated with us.
        # Evidence might remain in the form of a key that works for decrypting it. Time to
        # clean up that loose end.

        try:
            self.remove_own_nacl_key(key_id)
        except sqlite3.IntegrityError:
            pass # The nacl key is still in use with some address - This is expected
        pass


    def remove_message(self, message_id: str) -> None:
        """
        Removes a message identified by the message_id above (which happens to be the
        sha1 of the message content). To be used for targeted deletes.
        """
        self._get_conn().execute("DELETE FROM message WHERE id = ?", (message_id,))


    def read_message(self, message_id: str) -> stored_message.StoredMessage:
        """
        Returns a message identified by the message_id. As expected, return value
        is a StoredMessage.
        The method also returns various meta-information about the message, such
        as when it was first received, when it last received, whether it reuses an
        address etc.
        """
        curs = self._get_conn().cursor()
        curs.execute("SELECT * FROM message WHERE id = ? LIMIT 1", (message_id,))

        result = None
        for row in curs:
            result = row_to_message(row)
        return result


    def get_messages_to_forward(self, forward_count_cutoff: int=3) -> list:
        """
        Retrieves messages ripe for forwarding. Selector logic might
        be interesting in the future, but for now, just grab'em all
        as long as we have not forwarded them too many times.
        If there are no messages to forward, an empty list is returned.
        Notice that the list returned contains UserMessage objects,
        suitable for line transfer
        """
        curs = self._get_conn().cursor()
        curs.execute("SELECT * FROM message WHERE meta_forward_count < ?",
                     (forward_count_cutoff,))

        result = []
        for row in curs:
            result.append(row_to_message(row))
        return result


    def get_recieved_messages(self) -> list:
        """
        Retrieves a list of messages adressed to this node - As determined by the fact
        that they match internally generated adresses.
        """
        curs = self._get_conn().cursor()
        curs.execute(
            """
            SELECT * FROM message
            JOIN own_address ON own_address.id = message.header_address
            WHERE own_address.given_to IS NOT NULL
            ORDER BY message.meta_received_at DESC
            """, ())

        result = []
        for row in curs:
            result.append(row_to_message(row))
        return result


    def get_own_address_nacl_key(self, address_id: str) -> (str, str):
        """
        Retrieves the key ID and the private part of the key that is registered
        for the given address. If no such key is found, None is returned.
        """
        curs = self._get_conn().cursor()
        curs.execute(
            """
            SELECT * FROM nacl_key
            JOIN own_address ON nacl_key.id = own_address.key_id
            WHERE nacl_key.is_own = 1
            AND own_address.id = ?
            """, (address_id,))

        result = (None, None)
        for row in curs:
            result = row["id"], row["private_key"]
        return result


    def store_own_nacl_key(self, private_key: str, public_key: str) -> str:
        """
        Stores a key generated by this node. Please note that in this
        implementation, the actual key is serialised and stored here -
        In the previous GPG implementation, this used to be externally
        persisted.
        """
        key_id = str(uuid.uuid4())
        self._get_conn().execute("INSERT INTO nacl_key VALUES(?,?,?,?)",
                                 (key_id, True, private_key, public_key))
        self._get_conn().commit()
        return key_id


    def remove_own_nacl_key(self, key_id: str) -> None:
        """
        Removes one of our own keys. Please note that if the key is in use (there are still
        addresses that refer to it) this will generate an exception
        """
        self._get_conn().execute("DELETE FROM nacl_key WHERE id = ? AND is_own = ?",
                                 (key_id, True))
        self._get_conn().commit()


    def get_least_used_own_nacl_key(self) -> (str, str):
        """
        Retrieves the least used key in the sense that it has the least
        addresses tied to it. This is intended to reduce key usage as much
        as possible.
        OBSERVE: This is not the optimal key usage strategy - A better solution
                 should be made in a "real life" implementation
        """
        curs = self._get_conn().cursor()
        curs.execute(
            """
            SELECT nacl_key.id AS id, nacl_key.public_key AS public_key, COUNT(own_address.id) AS usage
            FROM nacl_key
            LEFT JOIN own_address ON nacl_key.id = own_address.key_id
            WHERE nacl_key.is_own = 1
            ORDER BY usage ASC
            LIMIT 1
            """, ())
        result = None
        for row in curs:
            result = row["id"], row["public_key"]
        return result


    def store_own_address(self, address: str, contact_id: str, key_id: str) -> None:
        """
        Registers a new address and binds it to a key that will encrypt
        all messages sent to it. Not reusing a key too many times is
        important in order to limit the possibilities of traffic analysis.
        Please note that the usage pattern is to record an address only when
        it has been sent to a foreign node, and to generate new addresses
        on demand (ergo, NOT to pre-generate blocks of addresses)

        Please note: A single key MAY be used for several addresses, but this is
        discouraged. The only legitimate case for this is in when processor power
        is highly scarce (mobile battery running out perhaps?)
        """
        self._get_conn().execute("INSERT INTO own_address VALUES(?,?,?,?)",
                                 (address,
                                  contact_id,
                                  key_id,
                                  False))
        self._get_conn().commit()


    def mark_own_address(self, address: str) -> None:
        """
        Marks this address as having been used in a message we have received.
        This means that the client should no long honor any messages sent to this
        address.
        """
        self._get_conn().execute("UPDATE own_address SET is_used = ? WHERE id = ?",
                                 (True, address))
        self._get_conn().commit()


    def remove_own_address(self, address) -> None:
        """
        Removes an address that could be used for foreign nodes to send a message to this
        node. This is generally fo usage with "remove_message_address" where the purpose
        is in fact message deletion.
        """
        self._get_conn().execute("DELETE FROM own_address WHERE id = ?",
                                 (address,))
        self._get_conn().commit()


    def store_contact_nacl_key(self, public_key: str) -> str:
        """
        Stores a key generated by a foreign node. This key may be used
        when sending messages to addresses that are bound to the key,
        all (presumably) belong to that same generating foreign node.
        """
        key_id = str(uuid.uuid4())
        self._get_conn().execute("INSERT INTO nacl_key VALUES(?,?,?,?)",
                                 (key_id,
                                  False,
                                  None,
                                  public_key))
        self._get_conn().commit()
        return key_id


    def store_contact_address(self, contact_id: str, address: str, key_id: str):
        """
        Stores an address of a foreign node and binds it to a key that
        should be used to encrypt the message sent to the contact address.
        """
        self._get_conn().execute("REPLACE INTO foreign_address VALUES(?,?,?,?)",
                                 (address,
                                  contact_id,
                                  key_id,
                                  False))
        self._get_conn().commit()


    def mark_contact_address(self, address_id: str) -> None:
        """
        Will mark a contact at used and not to be used again - Old addresses are kept
        for some time, as they might be used in resends of the message.
        """
        self._get_conn().execute("UPDATE foreign_address SET is_used = ? WHERE id = ?",
                                 (True,
                                  address_id))
        self._get_conn().commit()


    def get_address_pad_nacl(self, contact_id: str, size: int=None) -> list:
        """
        Returns a list of unused contact.Address objects pointing to the given contact.
        If there are no unused addresses leading to the contact, an empty list is returned.
        """
        curs = self._get_conn().cursor()
        if size is None:
            curs.execute("SELECT fa.id, fa.key_id, nacl_key.public_key "
                         "FROM foreign_address AS fa "
                         "JOIN nacl_key ON fa.key_id = nacl_key.id "
                         "WHERE fa.contact_id = ? "
                         "AND fa.is_used = ?",
                         (contact_id, False))
        else:
            curs.execute("SELECT fa.id, fa.key_id, nacl_key.public_key "
                         "FROM foreign_address AS fa "
                         "JOIN nacl_key ON fa.key_id = nacl_key.id "
                         "WHERE fa.contact_id = ? "
                         "AND fa.is_used = ? "
                         "LIMIT ?",
                         (contact_id, False, size))
        result = []
        for row in curs:
            result.append(contact.Address(row[0], row[1], public_key=row[2]))
        return result


    def get_unused_address_count(self, contact_id: str) -> list:
        """
        Returns a coint of unused addresses pointing to the given contact..
        """
        curs = self._get_conn().cursor()
        curs.execute("SELECT COUNT(fa.id) "
                     "FROM foreign_address AS fa "
                     "JOIN nacl_key ON fa.key_id = nacl_key.id "
                     "WHERE fa.contact_id = ? "
                     "AND fa.is_used = ?",
                     (contact_id, False))

        result = 0
        for row in curs:
            result = row[0]
        return result


    def store_contact(self, nickname: str, alias: str) -> str:
        """
        Stores an actual contact. This is mainly a foreign key used in
        other tables, but also contains nickname and other information the
        end user might be interested in.
        """
        # TODO: Check for existence of nickname - SHOULD be unique
        contact_id = str(uuid.uuid4())
        self._get_conn().execute("INSERT INTO contact VALUES(?,?,?,datetime('now'),datetime('now'))",
                                 (contact_id, nickname, alias))
        self._get_conn().commit()
        return contact_id


    def remove_contact(self, contact_id: str):
        """
        Removes a contact identified by the message_id above.
        """
        self._get_conn().execute("DELETE FROM contact WHERE id = ?", (contact_id,))
        self._get_conn().commit()


    def read_contact(self, contact_id: str) -> contact.Contact:
        """
        Retrieves a given contact identified by the contact id. Will return a Contact object.
        """
        curs = self._get_conn().cursor()
        curs.execute("SELECT * FROM contact WHERE id = ? LIMIT 1",
                     (contact_id,))

        result = None
        for row in curs:
            result = contact.Contact()
            result.contact_id = row["id"]
            result.nickname = row["nickname"]
            result.alias = row["alias"]
            result.created_at = row["created_at"]
        return result


    def read_contact_from_nickname(self, nickname: str) -> contact.Contact:
        """
        Retrieves a given contact identified by the nickname. Will return a Contact object.
        OBSERVE: This is probably not a "real" method, in that trusting what people send in
        the "from" field is stupid. However, for the purposes of the tech demonstrator, it
        makes life a bit easier.
        """
        curs = self._get_conn().cursor()
        curs.execute("SELECT * FROM contact WHERE nickname = ? LIMIT 1",
                     (nickname,))

        result = None
        for row in curs:
            result = contact.Contact()
            result.contact_id = row["id"]
            result.nickname = row["nickname"]
            result.alias = row["alias"]
            result.created_at = row["created_at"]
        return result


    def get_contacts(self) -> list:
        """
        get_contact returns a list containing Contact objects representing
        all known contacts. Slightly primitive - some kind of filter/paging
        will be used in a real implementation
        """
        curs = self._get_conn().cursor()
        curs.execute("SELECT * FROM contact")

        result = []
        for row in curs:
            c = contact.Contact()
            c.contact_id = row["id"]
            c.nickname = row["nickname"]
            c.alias = row["alias"]
            c.created_at = row["created_at"]
            result.append(c)
        return result


    def is_own_unused_address(self, address) -> bool:
        """
        Returns 'True' iff the address given has been generated by this
        node and has not been used in a message we received already
        """
        curs = self._get_conn().cursor()
        curs.execute("SELECT COUNT(*) FROM own_address WHERE id = ? AND is_used = ?",
                     (address,
                      False))

        for row in curs:
            if row[0] > 0:
                return True
        return False


    # Slightly iffy - Probably good to have around anyway
    def get_my_message_hashes(self) -> list:
        """
        Returns a list of hashes of messages that are addressed to any
        address beloning to this node - "My messages". They may then
        be retreived separately.
        """
        curs = self._get_conn().cursor()
        curs.execute(
            """
            SELECT message.id AS id FROM message
            JOIN own_address ON own_address.id = message.header_address
            WHERE own_address.given_to IS NOT NULL
            """, ())

        result = []
        for row in curs:
            result.append(row["id"])
        return result
