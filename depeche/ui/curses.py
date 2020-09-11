"""
This is the main file for the curses terminal interface - It collects the
various commands that can be issued to your depeche client
"""
import uuid
import copy
import curses
import logging
import os.path
import datetime
import threading

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser, Parser

from configparser import ConfigParser
from configparser import NoSectionError
from configparser import NoOptionError

from depeche.crypto.provider_nacl import ProviderNaCl
from depeche.messages.sqlite_storage import SqliteStorage
from depeche.communication.protocol.structures import RendezvousInfo
from depeche.communication.protocol.structures import UserMessage
from depeche.communication.adapter.localnet.naive import TcpUdpAdapter

import depeche.contacts.contact as contact
import depeche.communication.protocol.node_intercom as NodeIntercom


class _Menu:
    """
    Simple data container holding the information needed to dislay and use a menu
    """
    def __init__(self, title: str, items: list):
        self.title = title
        self.items = items


class _MenuItem:
    """
    This class is a simple container for menu item information.
    """
    def __init__(self, key: str, text: str, command: callable):
        self.key = key
        self.text = text
        self.command = command


class _MIME:
    def construct_top_level_mime_message(to_header: str, from_header: str,
                                         body_text: str,
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

        logging.getLogger(__name__).debug(msg.as_string())
        return msg


class CursesInterface:
    """This class encapsulates the different functions that the curses UI exposes"""

    @staticmethod
    def main_screen_turn_on(conf: ConfigParser):
        """
        If we want a a root screen to run on that happens to be the actual
        curses default screen, this is what we call. Naturally, there is only
        one curses root screen so multiple calls of this is a bad idea.
        """
        curses.wrapper(lambda scr: CursesInterface(scr, conf).run())


    def __init__(self, root_window, conf: ConfigParser):
        self._logger = logging.getLogger(__name__)
        self._logger.info("Starting curses CLI")

        # Global state init
        self._quit = False
        self._active_menu = _Menu("Empty menu", [])

        # Persistence
        try:
            db_file_path = conf.get("persistence", "db_file_path")
            self._db = SqliteStorage(db_file_path)
        except (NoSectionError, NoOptionError):
            self._logger.info("No configuration found for db file. Using default.")
            self._db = SqliteStorage()
        self._db.connect_thread()

        # Crypto init
        self._crypto_provider = ProviderNaCl()

        # Communication
        self._adapter = TcpUdpAdapter(self._crypto_provider)
        self._is_listening_passive = False
        self._is_listening_active = False

        # Root window init
        self._stdscr = root_window
        self._stdscr.clear()

        # Status init
        max_y, max_x = self._stdscr.getmaxyx()
        self._statusscr = self._stdscr.derwin(3, 45, 0, max_x - 45)
        self._status = "Inactive"


    def run(self):
        """
        This method will start the CLI (duh). Please notice that the CLI manages
        several threads, depending on what commands have been issued to it.
        """
        menu = self._get_root_menu()
        self._active_menu = menu

        self._redraw()

        while not self._quit:
            choice = self._stdscr.getkey()

            for item in self._active_menu.items:
                if item.key == choice:
                    item.command()

            self._redraw()

        if self._is_listening_passive:
            self._adapter.stop_register_announcements()

        # And if we happen to have any stray threads, they'll pop out here.
        self._logger.debug(str(threading.enumerate()))


    def _redraw(self):
        """
        Will cause the application to redraw itself to show all new state
        """
        self._stdscr.clear()
        self._draw_menu(self._stdscr, self._active_menu)
        self._display_state()
        self._stdscr.refresh()


    def _display_state(self):
        """
        This will refresh the status window, enabling the user to see what is
        going on in the application. Please note that the results will not be visible
        until containing window has been refreshed
        """
        self._statusscr.clear()
        self._statusscr.border()

        self._statusscr.addstr(1, 3, "Status: ")
        self._statusscr.addstr(self._status, curses.A_BOLD)


    def _draw_menu(self, scr, menu: _Menu, line: int=1):
        """
        This function will draw a meny in the given screen/window. If the menu
        is higher than the height of the window, bad stuff will happen.
        The menu will be drawn beginning at (1, 1) and extend one row per menu item
        plus one for the menu heading.
        """
        scr.addstr(line, 1, menu.title, curses.A_BOLD)

        for item in menu.items:
            line = line + 1
            scr.addstr(line, 3, item.key)
            scr.addstr(" - ")
            scr.addstr(item.text)


    def _draw_menu_horizontal(self, scr, menu: _Menu, line: int=1):
        """
        This function will draw a meny in the given screen/window. If the menu
        is wider than the width of the window, bad stuff will happen.
        The menu will be drawn beginning at (line, 1) and extend along that line
        """
        scr.addstr(line, 1, "{0}: ".format(menu.title), curses.A_BOLD)

        for item in menu.items:
            scr.addstr("{0}".format(item.text))
            scr.addstr("[{0}] ".format(item.key), curses.A_BOLD)


    def _show_text_dialog(self, prompt: str) -> str:
        """
        Shows a text input dialog window. Return value is a string that the user typed.
        """
        max_y, max_x = self._stdscr.getmaxyx()
        dialogscr = self._stdscr.derwin(3, 80, int(max_y / 2), int(max_x / 2) - 40)
        dialogscr.clear()
        dialogscr.border()

        dialogscr.addstr(1, 3, prompt)
        dialogscr.addstr(": ")

        dialogscr.refresh()

        curses.echo()
        result = dialogscr.getstr().decode("utf-8")
        curses.noecho()

        return result


    def _show_integer_dialog(self, prompt: str) -> int:
        result = None
        while type(result) is not int:
            text = self._show_text_dialog("{} (must be an integer)".format(prompt))
            try:
                result = int(text)
            except:
                pass

        return result


    def _show_selection_dialog(self, menu: _Menu, vertical: bool = True, text: str = None) -> object:
        """
        Shows a dialog window with a menu selection. Returns an object that the user selected.
        The text argument is shown above the menu - Used for instructions or content on
        which to select an action.

        PLEASE NOTE! The _Menu sent as argument must have commands attached to them that
        return the correct value for that menu item. This will usually mean that the command
        needs to be created over some closure.
        """
        max_y, max_x = self._stdscr.getmaxyx()

        top_padding = 1                       # Initial empty line looks good
        if not text:
            text_lines = []
            text_height = 0
        else:
            text_lines = text.splitlines()
            text_height = 1 + len(text_lines) # Allow for bottom padding of text

        if vertical:
            menu_height = 2 + len(menu.items) # One for title, one per item and one for padding
        else:
            menu_height = 2                   # One for menu, one for padding

        dialogscr_height = top_padding + text_height + menu_height

        dialogscr = self._stdscr.derwin(dialogscr_height, 80, int(max_y / 2), int(max_x / 2) - 40)
        dialogscr.clear()
        dialogscr.border()

        i = 1
        for line in text_lines:
            dialogscr.addstr(i, 3, line)
            i = i + 1

        # If we printed some text, we insert some padding between it and the menu
        if text_height > 0:
            i = i + 1

        if vertical:
            self._draw_menu(dialogscr, menu, i)
        else:
            self._draw_menu_horizontal(dialogscr, menu, i)

        dialogscr.refresh()

        result = None
        while not result:
            choice = self._stdscr.getkey()

            for item in menu.items:
                if item.key == choice:
                    result = item.command()

        return result


    def _show_confirmation_dialog(self, text: str) -> bool:
        """
        This method will present the user with a yes/no choice dialog window. If the
        user selects "yes", True will be returned, if the user selects "no", False will
        be returned.
        """
        max_y, max_x = self._stdscr.getmaxyx()

        text_lines = text.splitlines()
        dialogscr_height = 4 + len(text_lines)

        dialogscr = self._stdscr.derwin(dialogscr_height, 80, int(max_y / 2), int(max_x / 2) - 40)
        dialogscr.clear()
        dialogscr.border()

        i = 1
        for line in text_lines:
            dialogscr.addstr(i, 3, line)
            i = i + 1

        dialogscr.addstr(dialogscr_height - 2, 3, "[Y]es or [N]o")

        dialogscr.refresh()

        choice = None
        result = None
        while not choice:
            choice = self._stdscr.getkey()

            if choice.lower() == "y":
                result = True
            elif choice.lower() == "n":
                result = False
            else:
                choice = None

        return result


    def _show_information_dialog(self, text: str):
        """
        This method will present the user with a yes/no choice an informational dialog window.
        When the user presses any button, the dialog will be done.
        """
        max_y, max_x = self._stdscr.getmaxyx()

        text_lines = text.splitlines()
        dialogscr_height = 4 + len(text_lines)

        self._logger.debug("Text to display is: " + text)

        dialogscr = self._stdscr.derwin(dialogscr_height, 80, int(max_y / 2), int(max_x / 2) - 40)
        dialogscr.clear()
        dialogscr.border()

        i = 1
        for line in text_lines:
            dialogscr.addstr(i, 3, line)
            i = i + 1

        dialogscr.addstr(dialogscr_height - 2, 3, "Press [ANY] key to continue")

        dialogscr.refresh()

        self._stdscr.getkey()
        return


    def _command_failed(self, message):
        self._status = message
        self._active_menu = self._get_root_menu()
        self._redraw()


    ################################################################################
    #
    # Menus - Selection lists available without activating any specific command
    #
    ################################################################################

    def _get_root_menu(self) -> (str, list):
        """
        Returns the root menu for the "default" state of the application
        """
        items = []
        items.append(_MenuItem("1", "Generate new key", self.generate_key))
        items.append(_MenuItem("2", "Perform rendezvous", self.rendezvous))
        items.append(_MenuItem("3", "List contacts", self.list_contacts))
        items.append(_MenuItem("4", "Enqueue message", self.enqueue_message))
        items.append(_MenuItem("5", "Exchange messages", self.exchange_messages))
        items.append(_MenuItem("6", "Received messages", self.received_messages))
        items.append(_MenuItem("q", "Quit application", self.quit))

        return _Menu("Root menu:", items)


    ################################################################################
    #
    # Commands - Internal parts of these should eventually be generalized across
    #            different UI implementations
    #
    ################################################################################

    def reset(self):
        """
        Resets the status and root menu. For use when returning from sub-menus.
        """
        self._status = "Inactive"
        self._active_menu = self._get_root_menu()
        self._redraw()


    def quit(self):
        """
        Called in order to quit the application.
        """
        self._quit = True


    def generate_key(self):
        """
        This command initiates generation of a new private/public key pair for
        receiving messages. Generally speaking, only one key is necessary, but
        in order to avoid certain attacks new keys should be generated fairly often.
        """
        self._status = "Generating key"
        self._active_menu = _Menu("Operation in progress...", [])
        self._redraw()

        self._generate_new_key()

        self._status = "Key saved"
        self._active_menu = self._get_root_menu()
        self._redraw()


    def _generate_new_key(self) -> (str, str):
        secret_key, public_key = self._crypto_provider.generate_key()
        key_id = self._db.store_own_nacl_key(secret_key, public_key)
        return (key_id, public_key)


    def rendezvous(self):
        """
        Issuing this command will prompt for a shared secret - Once this has been
        suplied, the user is again prompted for when to start the rendezvous. When
        the user so indicates (on press of "Enter") the rendezvous sequence will
        start.
        TODO: On successful rendezvous, the user should be prompted for an alias for
        the new contact. Currently, the alias used is always what the foreign node
        gives which might not be what the user wants
        """
        # Set status
        self._status = "Rendezvous setup"
        self._active_menu = _Menu("Operation in progress...", [])
        self._redraw()

        # Get alias to send and secret shared with rendezvous partner
        alias = self._show_text_dialog("Alias to send")
        secret = self._show_text_dialog("Shared secret")

        info_success, key_id, rendezvous_info = self._rendezvous_produce_info(alias)

        # Use naive adapter to initiate rendezvous
        self._status = "Rendezvous started"
        self._redraw()

        success, foreign_info = self._adapter.rendezvous(secret, rendezvous_info)

        if success:
            self._status = "Rendezvous successful"
            self._rendezvous_save_info(key_id, rendezvous_info, foreign_info)
        else:
            self._status = "Rendezvous failed"

        self._active_menu = self._get_root_menu()
        self._redraw()


    def _rendezvous_produce_info(self, alias: str) -> (bool, str, RendezvousInfo):
        """
        This is a helper commad used to produce a rendezvous info object for sending
        to a foreign node.
        Return value is the ID of the key used to produce the rendezvous info as
        well as the info object itself.
        """
        # Retrieve a suitable public key to send
        (key_id, public_key) = self._db.get_least_used_own_nacl_key()

        # Produce address pad - We start with a block of 10 addresses
        address_pad = []
        for _ in range(10):
            adr = "ADR-" + str(uuid.uuid4())
            address_pad.append(adr)
        rendezvous_info = RendezvousInfo(alias=alias, address_pad=address_pad,
                                         public_key=public_key)

        return (True, key_id, rendezvous_info)


    def _rendezvous_save_info(self, key_id: str,
                              own_info: RendezvousInfo,
                              foreign_info: RendezvousInfo) -> bool:
        """
        This helper function will save rendezvous info on success - Returns a success
        report: True if successful, False otherwise.
        """
        # Only one key is to be imported at the moment. Not ideal, but
        # makes key usage a bit lower, saving some electrons for future generations
        contact_id = self._db.store_contact(foreign_info.alias, own_info.alias)
        contact_key_id = self._db.store_contact_nacl_key(foreign_info.public_key)

        for adr in foreign_info.address_pad:
            self._db.store_contact_address(contact_id, adr, contact_key_id)

        # Save the addresses that was sent to counterpart for future use
        for adr in own_info.address_pad:
            self._db.store_own_address(adr, contact_id, key_id)

        return True


    def list_contacts(self):
        """
        This command will list all available contacts under their local nickname.
        """
        self._status = "Listing contacts"
        contacts = self._db.get_contacts()

        menu_items = []
        i = 1
        for contact in contacts:
            menu_items.append(_MenuItem(str(i), contact.nickname,
                                        lambda c=contact: self._show_single_contact(c)))
            i = i + 1
        menu_items.append(_MenuItem("q", "Back to root menu", self.reset))

        self._active_menu = _Menu("Contacts: ", menu_items)
        self._redraw()


    def _show_single_contact(self, to_show: contact.Contact) -> None:
        self._redraw()

        def _no_action():
            return True

        menu_items = []
        menu_items.append(_MenuItem("s", "Send address pad to {}".format(to_show.nickname),
                                    lambda: to_show))
        menu_items.append(_MenuItem("q", "Quit",
                                    lambda: _no_action))
        action_menu = _Menu("Action on {}".format(to_show.nickname), menu_items)

        choice = self._show_selection_dialog(action_menu)
        if choice == True:
            return
        else:
            self._show_address_pad_send_sequence(to_show)


    def _show_address_pad_send_sequence(self, destination: contact.Contact) -> None:
        myself = contact.Contact() # May look odd: This is just a placeholder for the special case
        myself.nickname = "Myself"

        address_owner = self._show_address_owner_selection(myself)
        if address_owner == None:
            return
        if address_owner != myself:
            amount = self._show_address_amount_selection(address_owner)
        else:
            amount = self._show_address_amount_selection()

        # Be nice and let the user confirm or abort
        confirm_choices_message = "Is this ok?\nSend addresses to: {0}\nAddress owner: {1}\n" \
          "Number of addresses: {2}\n" \
          .format(destination.nickname, address_owner.nickname, amount)

        if not self._show_confirmation_dialog(confirm_choices_message):
            self._redraw()
            self._show_information_dialog("Aborting.")
            return
        self._redraw()

        # Special case: If the choice is to send local addresses, we'll need to generate new ones
        if address_owner == myself:
            msg = self._generate_own_address_pad_mime_message(destination, amount)
        # Else we'll need to collect some addresses and mark them as used before wrapping them up
        else:
            msg = self._generate_foreign_address_pad_mime_message(destination, address_owner, amount)

        address_data = self._db.get_address_pad_nacl(destination.contact_id)[0]
        self._enqueue_generic_message(address_data, msg)

        self._show_information_dialog("Message enqueued.")
        self._redraw()


    def _show_address_owner_selection(self, default: contact.Contact) -> contact.Contact:
        self._redraw()

        def _no_action():
            return True

        def _default():
            return default

        menu_items = []
        # Ugly special case. Yuck.
        menu_items.append(_MenuItem("m", "Myself", _default))
        i = 1
        contacts = self._db.get_contacts()
        for contact in contacts:
            menu_items.append(_MenuItem(str(i), contact.nickname, lambda c=contact: c))
            i += 1
        menu_items.append(_MenuItem("q", "Quit", lambda: _no_action))
        action_menu = _Menu("Send addresses belonging to", menu_items)

        choice = self._show_selection_dialog(action_menu)
        if choice == True:
            return None
        else:
            return choice


    def _show_address_amount_selection(self, address_owner: contact.Contact=None) -> int:
        self._redraw()

        if address_owner != None:
            available_addresses = len(self._db.get_address_pad_nacl(address_owner.contact_id))
            max_amount = min(available_addresses, 100)
        else:
            max_amount = 100

        amount = None
        while amount == None or max_amount < amount:
            amount = self._show_integer_dialog( \
                "Select number of addresses to include - Max {}".format(max_amount))
        return amount


    def enqueue_message(self):
        """
        This command will enqueue a message for exchange at the next convenient
        occasion. It will prompt the user for a contact to which to send the
        message and once one such has been chosen the user will be prompted for a
        file to send as message contents.
        In this version, only plain text files will be tested.
        """
        destination = self._select_destination()

        # If no destination is selected (bool value returned), we abort back to the main menu.
        if destination == True:
            return

        file_name = self._show_text_dialog("File to enqueue as a message")
        self._redraw()

        # Check that the file name given is a valid file
        if not os.path.isfile(file_name):
            self._show_information_dialog("File not found: {0}. Aborting.".format(file_name))
            self._redraw()
            return

        # Possibly ask if we should append request for more addresses
        remaining_address_count = self._db.get_unused_address_count(destination.contact_id)

        append_address_pad_message = "Should a request for more addresses be appended?\n" \
          "You currently have {0} unused addresses remaining.".format(remaining_address_count)
        is_sending_address_pad_req = self._show_confirmation_dialog(append_address_pad_message)
        self._redraw()

        # Check if we got everything right
        confirm_send_message = "Is this ok?\nTo: {0}\nFile name: {1}\nRequest address pad: {2}\n" \
          "".format(destination.nickname, file_name, is_sending_address_pad_req)
        self._redraw()

        if not self._show_confirmation_dialog(confirm_send_message):
            self._redraw()
            self._show_information_dialog("Aborting.")
            return
        self._redraw()

        # Finally set to do stuff!
        content_file = open(file_name)

        address_data = self._db.get_address_pad_nacl(destination.contact_id)[0]
        file_contents = content_file.read()

        # Cram stuff into a MIME message
        protocol_parts = []

        if is_sending_address_pad_req:
            protocol_parts.append(NodeIntercom.generate_address_pad_request(20))
        msg = _MIME.construct_top_level_mime_message(destination.nickname, destination.alias,
                                                     file_contents, protocol_parts)

        # Last step: Encrypt and plonk on the "out" tray
        self._enqueue_generic_message(address_data, msg)


    def _enqueue_generic_message(self, to_address: contact.Address, msg: EmailMessage) -> None:
        encrypted_contents = self._crypto_provider.encrypt(msg.as_bytes(), to_address.public_key)

        message = UserMessage(
            to_address=to_address.address_id,
            send_time=datetime.datetime.now(),
            contents=encrypted_contents)

        self._db.store_message(message)
        self._db.mark_contact_address(to_address.address_id) # Make sure not to re-use addresses



    def _select_destination(self):
        """
        Returns a contact of the users selection OR None if the user elects to skip this
        stage.
        """
        def _no_action():
            return True

        menu_items = []
        i = 1
        for contact in self._db.get_contacts():
            menu_items.append(_MenuItem(str(i), contact.nickname, lambda: contact))
            i = i + 1
        menu_items.append(_MenuItem("q", "Quit and go back to main menu", _no_action))

        destination_menu = _Menu("Select destination: ", menu_items)
        result = self._show_selection_dialog(destination_menu)
        self._redraw()

        return result


    def export_message(self):
        """
        This command will export the contents of a given message to a file. It will
        prompt the user for a message ID - Or at least the six initial characters of the
        message ID. If they are unique, the identified message will be decrypted
        and displayed.
        In this version, only plain text files will be tested.
        """
        pass


    def exchange_messages(self):
        """
        This command will try a generic exchange sequence consisting of a "dual
        attempt" with both passive and active message exchange methods. It'll
        run in active mode for 30 seconds after which it will stop.
        Concurrently, it'll start listening to other servers, which will continue
        until user interruption.
        """

        # Announce our presence and be prepared to respond to connection attempts
        self._status = "Exchanging messages"
        self._active_menu = _Menu("Operation in progress...", [])
        self._redraw()
        self._adapter.start_message_exchange_server(self._get_messages_to_send,
                                                    self._on_message_received)
        self._is_listening_active = True

        # Passively listen
        self._status = "Exchanging messages"
        self._active_menu = _Menu("Operation in progress...", [])
        self._redraw()
        self._adapter.start_register_announcements(self._on_server_announcement)
        self._is_listening_passive = True

        # And quit
        self._show_information_dialog("Press any key to quit message exchange")
        self._active_menu = _Menu("Aborting...", [])
        self._adapter.stop_register_announcements()
        self._adapter.stop_message_exchange_server()
        self._redraw()

        # Back to nornmal
        self._active_menu = self._get_root_menu()
        self._redraw()


    def _get_messages_to_send(self):
        self._db.connect_thread()
        stored_messages = self._db.get_messages_to_forward()
        user_messages = [UserMessage(m.header_address, m.header_sent_at, m.contents)
                             for m in
                             stored_messages]
        return user_messages


    def _on_server_announcement(self, *args):
        """Callback when a server announcement is picked up"""
        host, port = args
        self._db.connect_thread()

        user_messages = self._get_messages_to_send()

        self._logger.debug("Messages slated for exchange: " + str(user_messages))

        self._adapter.exchange_messages_with_server(
            (host, port),
            user_messages,
            self._on_message_received)

        # Once exchange is complete, we'll uptick the number of transfers for all
        # exchanged messages.

        self._db.disconnect_thread()


    def _on_message_received(self, *args):
        # We really expect only one "user message" to be returned per call. Anything else
        # is an error. Some strong typing would be in order. Python 3.4 says no.
        message = args[0]
        self._logger.info("Message received: {}".format(message))
        self._db.store_message(message)
        self._logger.info("Message stored.")


    def received_messages(self):
        """
        This command will list messages that match our own internally generated addresses -
        Generally this will mean that they are addressed to us/this node
        """
        self._status = "Listing received messages"
        messages = self._db.get_recieved_messages()

        def _show_message(m):
            self._show_message_cleartext(m.id, m.contents, m.header_address)
            self._redraw()

        menu_items = []
        i = 1
        for m in messages:
            menu_items.append(_MenuItem(str(i), m.id,
                                        lambda m=m: _show_message(m)))
            i = i + 1
        menu_items.append(_MenuItem("q", "Back to root menu", self.reset))

        self._active_menu = _Menu("Messages to me: ", menu_items)


    def _show_message_cleartext(self, message_id: str, ciphertext: str, address_id: str) -> None:
        key_id, private_key = self._db.get_own_address_nacl_key(address_id)
        cleartext = self._crypto_provider.decrypt(ciphertext, private_key)

        # Cleartext is supposed to be a MIME formatted message
        msg = BytesParser(policy=policy.default).parsebytes(cleartext)

        ## DEBUG
        self._logger.debug("Message id: {0} - Content: {1}".format(message_id, msg.as_string()))

        content = []
        address_pad = None
        address_pad_req = None

        for part in msg.walk():
            # Account for stuff we know will turn up - Specifically wrappers and protocol
            # control messages
            if part.get_content_type() == 'application/json':
                if part['Content-Description'] == NodeIntercom.address_pad_request_description:
                    address_pad_req = NodeIntercom.AddressPadRequest.deserialize(part.get_content())
                if part['Content-Description'] == NodeIntercom.address_pad_description:
                    address_pad = NodeIntercom.AddressPad.deserialize(part.get_content())
            elif part.get_content_maintype() == 'multipart' or \
              part.get_content_maintype() == 'application':
                continue
            else:
                content.append(part.get_content())

        msg_string = "From: {0}\nTo: {1}\n\n{2}".format(msg['from'], msg['to'], "\n".join(content))

        def _delete_message(message_id):
            self._logger.debug("Attempting to clean out message: {0}".format(message_id))
            self._db.clean_out_received_message(message_id)
            self.received_messages()  # Reload the messages menu
            return True

        def _no_action():
            return True

        # If the mail contained a address pad request or a message pad, show the alternatives
        if address_pad:
            import_prompt = "This message includes a block of addresses to {0}. " \
            "Import these?".format(address_pad.from_alias)
            should_import = self._show_confirmation_dialog(import_prompt)
            self._redraw()

            if should_import:
                self._import_address_pad(address_pad, msg['to'])

        if address_pad_req:
            request_prompt = "This message includes a request by {0} to send {1} additional " \
              "addresses. Enqueue addresses to {0}?".format(msg['from'], address_pad_req.pad_size)
            should_respond = self._show_confirmation_dialog(request_prompt)
            self._redraw()

            if should_respond:
                # Takes the "from" field and finds a contact from it, which is not ideal -
                # A "real" version of this would offer some kind of contact selection interaction
                # instead of trusting the from-header.
                destination = self._db.read_contact_from_nickname(msg['from'])
                # If the destination is not a known nickname, we'll just drop it - Again not ideal.
                if not destination:
                    return
                address_data = self._db.get_address_pad_nacl(destination.contact_id)[0]
                return_msg = self._generate_own_address_pad_mime_message(destination, 10)
                self._enqueue_generic_message(address_data, return_msg)


        # With the system messages done and dusted, let's show the defaul choices
        menu_items = []
        menu_items.append(_MenuItem("q", "Return", lambda: _no_action))
        menu_items.append(_MenuItem("d", "Delete", lambda: _delete_message(message_id)))
        action_menu = _Menu("Choice", menu_items)

        self._show_selection_dialog(action_menu, vertical=False, text=msg_string)


    def _import_address_pad(self, address_pad: NodeIntercom.AddressPad, own_alias: str) -> None:
        """
        This method will import foreign keys into our database in order for us to be able to send
        messages to the contact identified by the "owner" nickname in the pad - A "real" version of
        this would offer some kind of selection interaction instead of just using the nickname sent
        in the pad.
        """
        contact = self._db.read_contact_from_nickname(address_pad.from_alias)

        # If the destination is not a known nickname, we'll just create a new one - A better
        # interaction model would be good, but I want this shit done quick.
        if not contact:
            contact_id = self._db.store_contact(address_pad.from_alias, own_alias)
        else:
            contact_id = contact.contact_id

        for key_mapping in address_pad.key_mappings:
            contact_key_id = self._db.store_contact_nacl_key(key_mapping.key)
            for adr in key_mapping.address_list:
                self._db.store_contact_address(contact_id, adr, contact_key_id)


    def _generate_own_address_pad_mime_message(self, destination: contact.Contact,
                                               size: int) -> EmailMessage:
        address_pad_part = self._generate_own_address_pad(destination, size)
        msg = _MIME.construct_top_level_mime_message(destination.nickname,
                                                    destination.alias,
                                                    'Addresses to use when contacting me.',
                                                    [address_pad_part])
        return msg


    def _generate_own_address_pad(self, contact: contact.Contact, size: int) -> EmailMessage:
        """
        This method will generate an address pad MIME message. It takes the message
        recipients contact_id as argument as well as the intended size of the address pad.

        This implementation defaults the alias to send along with the address pad to be the
        same as the one registered for the contact - This is not mandated, but probably a
        reasonable guess at what a normal user would expect.
        """
        # Retrieve a suitable public key to send
        (key_id, public_key) = self._generate_new_key()

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
            self._db.store_own_address(adr, contact.contact_id, key_id)

        # Remember: contact.alias is the name by which we are known to the contact
        return NodeIntercom.generate_address_pad(contact.alias, [key_mapping])


    def _generate_foreign_address_pad_mime_message(self, destination: contact.Contact,
                                                   address_owner: contact.Contact,
                                                   size: int) -> EmailMessage:
        address_pad_part = self._generate_foreign_address_pad(destination, address_owner, size)
        msg = _MIME.construct_top_level_mime_message(destination.nickname,
                                                     destination.alias,
                                                     'Addresses to use when contacting {}.'.\
                                                         format(address_owner.nickname),
                                                     [address_pad_part])
        return msg

    def _generate_foreign_address_pad(self, recipient: contact.Contact, \
                                      address_owner: contact.Contact, size: int) -> EmailMessage:
        """
        This method will generate an address pad MIME message containing addresses beloning to the
        address_owner - A contact that should be known to this node - the recipient is another
        contact to which the address pad should be sent
        """
        address_list = self._db.get_address_pad_nacl(address_owner.contact_id, size)

        mappings = {}
        for address in address_list:
            if not address.key_id in mappings:
                mappings[address.key_id] = NodeIntercom.KeyMapping(address.public_key, [])
            mappings[address.key_id].add_address(address.address_id)
            # Note that as we are exporting these addresses, we need to mark them as used in
            # order not to send addresses that might have been used / might be used in the future
            # by our contact.
            self._db.mark_contact_address(address.address)

        return NodeIntercom.generate_address_pad(address_owner.nickname, mappings.values())


    def enqueue_address_pad(self) -> None:
        """
        This command will enqueue an address pad of our own addresses OR a pad of addresses for
        a known contact that we want to forward to some third party (basically).
        """
        self.status = "Enqueueing address pad"

        menu_items = []
        i = 1
        menu_items.append(_MenuItem(str(i), "Myself", self.reset))
        i = i + 1
        contacts = self._db.get_contacts()
        for contact in contacts:
            menu_items.append(_MenuItem(str(i), contact.nickname, self.reset))
            i = i + 1
        menu_items.append(_MenuItem("q", "Back to root menu", self.reset))

        self._active_menu = _Menu("Send addresses belonging to: ", menu_items)
