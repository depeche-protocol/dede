import unittest
import depeche.communication.protocol.node_intercom as ni

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser, Parser

class TestNodeIntercom(unittest.TestCase):
    """Test cases for the node intercom package of structures and methods"""


    def test_email_generation(self):
        file_contents = "A super secret string that needs to be secret!"

        msg = EmailMessage()
        msg.make_mixed()
        msg['To'] = "Toperson"
        msg['From'] = "Fromperson"
        msg.add_attachment(file_contents)
        msg.attach(ni.generate_address_pad_request(20))

        ## DEBUG
        print(msg.as_string())


    def test_address_pad_request_serialization(self):
        apr = ni.AddressPadRequest()
        json_str = apr.serialize()

        apr2 = ni.AddressPadRequest.deserialize(json_str)


    def test_address_pad_serialization(self):
        ap = ni.AddressPad("myself")

        adr_set_1 = []
        adr_set_1.append("someaddress1-1")
        adr_set_1.append("someaddress1-2")
        mapping_1 = ni.KeyMapping("somekey1", adr_set_1)
        ap.add_key_mapping(mapping_1)

        adr_set_2 = []
        adr_set_2.append("someaddress2-1")
        adr_set_2.append("someaddress2-2")
        mapping_2 = ni.KeyMapping("somekey2", adr_set_2)
        ap.add_key_mapping(mapping_2)

        json_str = ap.serialize()
        #print(json_str)

        ap2 = ni.AddressPad.deserialize(json_str)
        self.assertEqual(len(ap.key_mappings), len(ap2.key_mappings))

        for i in range(len(ap.key_mappings)):
            self.assertEqual(ap.key_mappings[i].key, ap2.key_mappings[i].key)


    def test_address_pad_request_message(self):
        email = ni.generate_address_pad_request(20)
        #print(email.as_string())

        self.assertEqual('application/json', email.get('Content-Type'))


    def test_address_pad__message(self):
        mappings = []

        km1 = ni.KeyMapping("key1", ["adr1-1", "adr1-2", "adr1-3"])
        mappings.append(km1)
        km2 = ni.KeyMapping("key2", ["adr2-1", "adr2-2", "adr2-3"])
        mappings.append(km2)

        email = ni.generate_address_pad("myself", mappings)
        #print(email.as_string())

        self.assertEqual('application/json', email.get('Content-Type'))
