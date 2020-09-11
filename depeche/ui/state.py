"""
This is a generalized state-keeping class for generalized usage across GUI
implementations. It should contain stuff that needs to keep state - non-stateful
stuff should go into the easier-to-understand common.py
"""
import logging

from configparser import ConfigParser
from configparser import NoSectionError
from configparser import NoOptionError

from depeche.crypto.provider_nacl import ProviderNaCl
from depeche.messages.sqlite_storage import SqliteStorage
from depeche.communication.adapter.localnet.naive import TcpUdpAdapter


class DedeStateKeeper():

    def __init__(self, conf: ConfigParser):
        self._logger = logging.getLogger(__name__)

        # Set up persistence
        try:
            db_file_path = conf.get("persistence", "db_file_path")
            self._db = SqliteStorage(db_file_path)
        except (NoSectionError, NoOptionError):
            self._logger.info("No configuration found for db file. "
                              "Using default.")
            self._db = SqliteStorage()
        self._db.connect_thread()

        # Set up encryption
        self._crypto_provider = ProviderNaCl()

        # Set up networking
        self._adapter = TcpUdpAdapter(self._crypto_provider)

    @property
    def adapter(self):
        return self._adapter

    @property
    def db(self) -> SqliteStorage:
        return self._db

    @property
    def crypto(self):
        return self._crypto_provider
