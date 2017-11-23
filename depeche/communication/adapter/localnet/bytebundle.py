"""
This module deals with a lightweight messaging protocol on top of
TCP/IP.
Please note - This byte bundle is distinct from a "message" in depeche
terms. This module is merely a convenience for adapters using TCP/IP
to communicate.

A message segment formatted like this:
4 bytes - Protocol identifier 3725508833 [de0ec0e1] (Not to be
          treated as a delimiter, but will serve to reduce number
          of faulty reads)
2 bytes - Version number of protocol. The current version is 0
4 bytes - Size information - 32 bit unsigned integer indicating
          size of message to read. The value of this is called 'S'
1 byte  - Boolean indicating of this is the last message in a
          sequence of messages. True, indicating end-of-sequence,
          if non-zero.
S bytes - Message contents.

If the segment it not the last in the sequence, the method will
attempt to continue reading until the last segment has been
received.
"""

from ctypes import BigEndianStructure
from ctypes import c_uint8
from ctypes import c_uint32

import logging
logger = logging.getLogger(__name__)

class _MessageHeader(BigEndianStructure):
    """Class defining byte structure of segment header"""
    _fields_ = [("proto_identifier",     c_uint32),
                ("version_number",       c_uint8),
                ("message_size",         c_uint32),
                ("last_segment",         c_uint8)]
    _pack_ = 1 # No fancy word alignment

def read(sock, previous_data=b''):
    """
    Return value is a byte buffer containing the concatenated message
    contents of all message segments. If a timeout should occurr
    during the reading of a segment or between segments an exception
    will be thrown. If a timeout occurs between messages, an empty
    byte buffer will be returned.
    Please note that this method should only be invoked with a socket
    connected to a single peer. If more peers are connected to the
    same socket object, this method will fail badly.
    """

    # Inital data read - We expect a proto and version
    data = sock.recv(10)

    proto = data[:4]
    if proto != b'\xde\x0e\xc0\xe1':
        logger.error("Protocol does not match data received: " + repr(proto))
        raise RuntimeError("Protocol does not match data received: " + repr(proto))
    # Protocol validates

    version = int.from_bytes(data[4:5], byteorder='big', signed=False)
    if version != 0:
        logger.error("Protocol version not supported: " + repr(version))
        raise RuntimeError("Protocol version not supported: " + repr(version))
    # Version is supported

    length = int.from_bytes(data[5:9], byteorder='big', signed=False)
    is_last = bool(data[9:])

    logger.debug("Header validated. Reading {} bytes sized message.".format(length))
    if length > 0:
        parts = []
        remaining_bytes = length
        while remaining_bytes > 0:
            logger.debug("Bytes left to read: " + str(remaining_bytes))

            part = sock.recv(min(remaining_bytes, 2048))
            remaining_bytes = remaining_bytes - len(part)

            logger.debug("Read bytes: " + str(len(part)))
            if part == b'' and remaining_bytes > 0:
                raise RuntimeError("socket connection broken")

            parts.append(part)

        segment_data = b''.join(parts)
        received_data = b''.join([previous_data, segment_data])

        if is_last:
            return received_data
        else:
            return read(sock, received_data)
    else:
        return b''


def send(bytes_to_send, sock):
    """
    For message format, see _read_message.
    TODO: Split very large messages across several segment.
    """
    logger.debug("Sending message with payload size: " + str(len(bytes_to_send)))
    header = _MessageHeader(0xde0ec0e1, 0, len(bytes_to_send), True)
    sock.sendall(b''.join([header, bytes_to_send]))
