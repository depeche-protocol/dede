"""
This is the main file for the wx windowed interface for interactive
desktop systems. It will eventually replace the curses interface, since
that is getting increasinly cumbersome to navigate.

Please note that wxPython likes camel case. I don't.
"""
import wx
import logging

from configparser import ConfigParser

import depeche.ui.common as util

from depeche.ui.state import DedeStateKeeper
from depeche.ui.wx.rendezvous_frame import RendezvousFrame
from depeche.ui.wx.rendezvous_events import EVT_RENDEZVOUS_BEGIN_ID
from depeche.ui.wx.rendezvous_events import EVT_RENDEZVOUS_END_ID
from depeche.ui.wx.exchange_events import EVT_EXCHANGE_COMPLETE_ID
from depeche.ui.wx.exchange_events import ExchangeCompleteEvent
from depeche.ui.wx.contacts_frame import ContactsFrame
from depeche.ui.wx.new_message_frame import NewMessageFrame


# Handy little shorthand
def connect_event(win, event_id, func):
    win.Connect(-1, -1, event_id, func)


class MainFrame(wx.Frame):
    """
    The main window of the DeDe application. This will show status of
    ongoing operations as well as a list of messages that has been
    received.
    """

    @staticmethod
    def main_screen_turn_on(conf: ConfigParser):
        """
        Main entry point to the WX GUI. Call this to show start the app.
        """
        app = wx.App()
        frm = MainFrame(None, -1, 'DeDe - Depeche protocol demonstrator', conf)
        frm.Show()
        app.MainLoop()

    def __init__(self, parent, id, title, conf: ConfigParser):
        # ensure the parent's __init__ is called
        super(MainFrame, self).__init__(parent, title=title, size=wx.Size(700, 450))

        self._state = DedeStateKeeper(conf)
        self._active = False

        # Set up logging
        self._logger = logging.getLogger(__name__)
        self._logger.info("Starting WX GUI")

        self.Bind(wx.EVT_CLOSE, self.on_close)

        # Set up event handlers
        connect_event(self, EVT_RENDEZVOUS_BEGIN_ID, self.on_rendezvous_begin)
        connect_event(self, EVT_RENDEZVOUS_END_ID, self.on_rendezvous_end)
        connect_event(self, EVT_EXCHANGE_COMPLETE_ID, self.on_exchange_completed)

        # Set up UI
        self.init_ui()
        self.Show(True)

    def init_ui(self):
        self.make_menu_bar()
        self.make_message_area()

        # Status bar will track status of the application - Inactive is the
        # default starting state
        self.CreateStatusBar()
        self.SetStatusText("Inactive")

    def make_message_area(self):
        self.message_panel = wx.Panel(self)

        hbox = wx.BoxSizer(wx.HORIZONTAL)

        # Message list part where we display messages the user can read
        self.message_list = wx.ListCtrl(self.message_panel, -1, style=wx.LC_REPORT)
        self.message_list.InsertColumn(0, 'ID', width=140)
        self.message_list.InsertColumn(1, 'Received at', width=130)
        self.message_list.InsertColumn(2, 'To alias', wx.LIST_FORMAT_RIGHT, 90)

        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_message_selected, self.message_list)
        self.fill_message_list()
        hbox.Add(self.message_list, 1, wx.EXPAND)

        # Message contents part where the actual contents of messages are displayed
        self.contents_box = wx.BoxSizer(wx.VERTICAL)
        self.message_contents = wx.TextCtrl(self.message_panel,
                                            style=wx.CB_READONLY | wx.TE_MULTILINE)
        self.contents_box.Add(self.message_contents, 1, wx.EXPAND)

        self.pad_box = wx.BoxSizer(wx.VERTICAL)
        self.pad_action_box1 = wx.BoxSizer(wx.HORIZONTAL)
        self.pad_request_present_label = wx.StaticText(self.message_panel, wx.ID_ANY,
                                                       "Request for addresses found")
        self.pad_request_present_label.Show(False)
        self.reply_with_pad_button = wx.Button(self.message_panel, wx.ID_ANY,
                                               'Reply with addresses')
        self.reply_with_pad_button.Show(False)
        self.Bind(wx.EVT_BUTTON, self.on_reply, self.reply_with_pad_button)

        self.pad_action_box1.Add(self.pad_request_present_label, 0)
        self.pad_action_box1.Add(self.reply_with_pad_button, 0)

        self.pad_action_box2 = wx.BoxSizer(wx.HORIZONTAL)
        self.pad_present_label = wx.StaticText(self.message_panel, wx.ID_ANY,
                                               "Attached addresses found")
        self.pad_present_label.Show(False)
        self.import_pad_button = wx.Button(self.message_panel, wx.ID_ANY,
                                           'Import addresses')
        self.import_pad_button.Show(False)
        self.Bind(wx.EVT_BUTTON, self.on_import_addresses, self.import_pad_button)
        self.pad_action_box2.Add(self.pad_present_label, 0)
        self.pad_action_box2.Add(self.import_pad_button, 0)

        self.pad_box.Add(self.pad_action_box1, 0, wx.EXPAND)
        self.pad_box.Add(self.pad_action_box2, 0, wx.EXPAND)
        self.contents_box.Add(self.pad_box, 0, wx.EXPAND)

        hbox.Add(self.contents_box, 1, wx.EXPAND)
        self.message_panel.SetSizer(hbox)
        self.Centre()

    def fill_message_list(self):
        self.message_list.DeleteAllItems()
        self.messages = self._state.db.get_recieved_messages()
        index = 0
        for m in self.messages:
            self.message_list.InsertItem(index, m.id)
            self.message_list.SetItemData(index, index)
            self.message_list.SetItem(index, 1, str(m.received_at) + " UTC")
            self.message_list.SetItem(index, 2, str(m.forward_count))
            index += 1

    def make_menu_bar(self):
        """
        A menu bar is composed of menus, which are composed of menu items.
        This method builds a set of menus and binds handlers to be called
        when the menu item is selected.
        """

        # Make a file menu with Hello and Exit items
        file_menu = wx.Menu()
        exit_item = file_menu.Append(wx.ID_EXIT)

        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT)

        # Menu for operations
        self.op_menu = wx.Menu()
        new_alias_item = self.op_menu.Append(1, "New &Alias")
        rendezvous_item = self.op_menu.Append(2, "&Rendezvous")
        enqueue_message_item = self.op_menu.Append(3, "New &Message")
        exchange_toggle_item = self.op_menu.Append(4, "E&xchange messages")

        # Menu for editing data and internal state
        others_menu = wx.Menu()
        contacts_item = others_menu.Append(5, "&Contacts")

        # Top menu of the root window. Should expose all interesting
        # functionality as clearly as possible
        menuBar = wx.MenuBar()
        menuBar.Append(file_menu, "&File")
        menuBar.Append(self.op_menu, "&Operations")
        menuBar.Append(others_menu, "&Edit")
        menuBar.Append(help_menu, "&Help")
#
        self.SetMenuBar(menuBar)

        # Finally, associate a handler function with the EVT_MENU event for
        # each of the menu items. That means that when that menu item is
        # activated then the associated handler function will be called.
        self.Bind(wx.EVT_MENU, self.on_exit_selected, exit_item)
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        self.Bind(wx.EVT_MENU, self.on_new_alias, new_alias_item)
        self.Bind(wx.EVT_MENU, self.on_rendezvous_clicked, rendezvous_item)
        self.Bind(wx.EVT_MENU, self.on_enqueue_message_clicked, enqueue_message_item)
        self.Bind(wx.EVT_MENU, self.on_toggle_exchange, exchange_toggle_item)
        self.Bind(wx.EVT_MENU, self.on_contacts_clicked, contacts_item)

    def on_exit_selected(self, event):
        """Close the frame, terminating the application."""
        self.Close(True)

    def on_close(self, event):
        if self._active:
            util.exchange_messages_stop(self._state.adapter)
        self.Destroy()

    def on_about(self, event):
        """Display an About Dialog"""
        header = "About DeDe"
        body = ("This is the demonstrator application for the "
                "Depeche Protocol. It's primarily inteded as "
                "a validation that the protocol is possible to "
                "implement by mere humans, but may be used for "
                "actual message sending.\n\nPlease be aware that "
                "application security is NOT a part of this demo - "
                "if you are using it in a hostile environment, "
                "you should consider switching to a more secure "
                "implementation.")

        wx.MessageBox(body, header, wx.OK | wx.ICON_INFORMATION)

    def on_new_alias(self, event):
        """Create a new alias to use when communicating"""
        alias_dia = wx.TextEntryDialog(self, "Create a new alias")
        alias_dia.ShowModal()

    def on_rendezvous_clicked(self, event):
        """Will trigger a dialogue for a new rendezvous operation"""
        RendezvousFrame(self, self._state)

    def on_rendezvous_begin(self, event):
        self.SetStatusText("Rendezvous in progress...")

    def on_rendezvous_end(self, event):
        self.SetStatusText(event.data)

    def on_exchange_completed_from_server(self):
        """
        This callback will be invoked by the exchange server thread, and thus need to generate
        an event that can be picked up by the main UI thread.
        """
        wx.PostEvent(self, ExchangeCompleteEvent(None))

    def on_exchange_completed(self, event):
        """
        When an exchange operation has completed, we refresh the message list as we might have
        gotten some new messages!
        """
        self.fill_message_list()

    def on_enqueue_message_clicked(self, event):
        """Will allow simple creation of message and subsequent enqueuing of it"""
        NewMessageFrame(self, self._state)

    def on_toggle_exchange(self, event):
        """
        This will toggle message exchange on or off - Ideally should only be available
        when there is an active local network connection, but that is a TODO.
        """
        if not self._active:
            util.exchange_messages_start(self._state.db, self._state.adapter,
                                         self.on_exchange_completed_from_server)
            self.SetStatusText("Exchanging messages")
            self.op_menu.SetLabel(4, "Stop e&xchange")
        else:
            util.exchange_messages_stop(self._state.adapter)
            self.SetStatusText("Inactive")
            self.op_menu.SetLabel(4, "E&xchange messages")
        # State has flipped
        self._active = not self._active

    def on_contacts_clicked(self, event):
        """Will open a frame for viewing and manipulating contacts"""
        ContactsFrame(self, self._state)

    def on_message_selected(self, event):
        selected_message = self.messages[event.GetData()]

        (msg_string, address_pad_req, self.address_pad) = \
            util.parse_message(self._state.db, self._state.crypto, selected_message)

        self.message_contents.SetValue(msg_string)

        if address_pad_req:
            self.pad_request_present_label.Show(True)
            self.reply_with_pad_button.Show(True)
        if self.address_pad:
            self.pad_present_label.Show(True)
            self.import_pad_button.Show(True)
        self.contents_box.Layout()

    def on_reply(self, event):
        # TODO: Please note that we simply assume that the "from" of the address pad is
        # present in the DB. This is not actually assured, and should be handled.
        recipient = self._state.db.read_contact_from_nickname(self.address_pad.from_alias)
        NewMessageFrame(self, self._state, recipient, True)

    def on_import_addresses(self, event):
        # TODO: Please note that we don't actually know what the owner of the addresses
        # know us as. A fair assumption is that they call us the same as the contact who
        # sent us the message.
        util.import_address_pad(self._state.db, self.address_pad, "N/A")
