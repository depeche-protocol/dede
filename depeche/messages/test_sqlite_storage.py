"""
Test cases for database creation, reads and writes
"""
import os
import unittest
import datetime
import depeche.communication.protocol.structures as structures
import depeche.messages.sqlite_storage as storage

class TestSqliteStorageBasic(unittest.TestCase):
    """Test cases for sqlite storage class - Will test create, schema creation and validation"""

    def test_db_detection_creation(self):
        # Remove any existing DB file
        destroy_db()

        """Tests whether database detection works as well as creation and re-detection"""
        is_present = storage._detect_db()
        self.assertFalse(is_present) # Should not exist at this time

        storage._create_db()

        is_present = storage._detect_db()
        self.assertTrue(is_present) # Now, though, there should be a DB

        conn = storage._connect_db()
        self.assertTrue(storage._verify_db(conn))

        # Now brutally remove the DB file
        destroy_db()

        is_present = storage._detect_db()
        self.assertFalse(is_present) # Should not exist at this time


class TestSqliteStorageRuntime(unittest.TestCase):
    """Test cases for sqlite storage class - Will test create, writes and reads"""

    def setUp(self):
        self._created_db = False
        if not storage._detect_db():
            storage._create_db()
            self._created_db = True
        self._storage = storage.SqliteStorage()


    def tearDown(self):
        # If we made a mess, we get to clean up as well
        if self._created_db:
            destroy_db()


    def test_message_write_read_delete(self):
        """Tests basic write-read-delete seqence for messages"""

        now = datetime.datetime.utcnow()
        toStore = structures.UserMessage("123123", now, "---PGP ENCRYPTED BLOCK --- ALSOEKSIEKSIEK")
        message_id = self._storage.store_message(toStore)
        self.assertIsNotNone(message_id)

        retrieved = self._storage.read_message(message_id)

        self.assertIsNotNone(retrieved)
        self.assertEqual(toStore.to_address, retrieved.header_address)
        self.assertEqual(toStore.send_time, retrieved.header_sent_at)
        self.assertEqual(0, retrieved.forward_count)

        self._storage.remove_message(message_id)
        retrieved = self._storage.read_message(message_id)
        self.assertIsNone(retrieved)


    def test_message_selection(self):
        """Tests selection of messages for forwarding"""
        pass

    def test_contact_read_and_write(self):
        """Tests basic write-read-delete seqence for contacts"""

        nickname = "a_new_contact"
        alias = "my_secret_identity"
        contact_id = self._storage.store_contact(nickname, alias)
        self.assertIsNotNone(contact_id)

        retrieved = self._storage.read_contact(contact_id)

        self.assertIsNotNone(retrieved)
        self.assertEqual(nickname, retrieved.nickname)
        self.assertEqual(alias, retrieved.alias)

        self._storage.remove_contact(contact_id)
        retrieved = self._storage.read_contact(contact_id)
        self.assertIsNone(retrieved)

    def test_message_clean_out(self):
        """
        Tests the cleaning out of messages - In point of fact, the removal of address
        and key data
        """
        address_1 = "address-no-1"
        address_2 = "address-no-2"

        # Set up contact, key and addresses
        contact_id = self._storage.store_contact("a-nickname", "my-alias")
        key_id = self._storage.store_own_nacl_key("a-private-key", "a-public-key")
        self._storage.store_own_address(address_1, contact_id, key_id)
        self._storage.store_own_address(address_2, contact_id, key_id)

        now = datetime.datetime.utcnow()
        toStore = structures.UserMessage(address_1, now, "SOMETOTALLYNOTENCRYPTEDDATA")
        message_id_1 = self._storage.store_message(toStore)
        toStore = structures.UserMessage(address_2, now, "ANOTHERTOTALLYNOTENCRYPTEDDATA")
        message_id_2 = self._storage.store_message(toStore)

        msg_list = self._storage.get_recieved_messages()
        self.assertEqual(2, len(msg_list))

        self._storage.clean_out_received_message(message_id_1)

        # Make sure that the message_1 ID cannot be tied to a key, but others are retained
        address_1_key_id, _ = self._storage.get_own_address_nacl_key(address_1)
        self.assertIsNone(address_1_key_id)
        address_2_key_id, _ = self._storage.get_own_address_nacl_key(address_2)
        self.assertIsNotNone(address_2_key_id)

        self._storage.clean_out_received_message(message_id_2)

        msg_list = self._storage.get_recieved_messages()
        self.assertEqual(0, len(msg_list))


def destroy_db(fname = storage.DB_FILE_NAME):
    """Destroys the DB file - Not for use with the ACTUAL db file!"""
    if os.path.isfile(fname):
        os.remove(fname)
