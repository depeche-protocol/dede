import wx
import logging

import depeche.ui.common as util

from depeche.contacts.contact import Contact
from depeche.ui.state import DedeStateKeeper


class NewMessageFrame(wx.Frame):
    """
    This frame is intended as a simple message composition utility - Text input, selection
    of recipient and "enqueue to send" once done and valid
    """

    def __init__(self, parent: wx.Frame, state_keeper: DedeStateKeeper,
                 default_recipient: Contact = None, default_include_address_pad: bool = False):

        super(NewMessageFrame, self).__init__(parent, title='New Message')
        self._parent = parent
        self._recipient = default_recipient
        self._include_address_pad = default_include_address_pad

        # Set up logging
        self._logger = logging.getLogger(__name__)
        self._logger.info("New message window opened")

        self._state_keeper = state_keeper

        # Initialize witha "None" recipient - recipient will be chosen in later user interaction
        # Please note - recipient should be of type "Contact"
        self.recipient = None

        # Set up UI
        self.init_ui()
        self.Center()
        self.Show()

    def init_ui(self):
        self.panel = wx.Panel(self, wx.ID_ANY)
        top_sizer = wx.BoxSizer(wx.VERTICAL)

        # Recipient input area
        recipient_label = wx.StaticText(self.panel, wx.ID_ANY, 'Recipient')

        self.recipient_cb = wx.ComboBox(self.panel, size=wx.Size(200, 30),
                                        style=wx.CB_READONLY, choices=[])
        self.fill_recipient_cb(self.recipient_cb)
        self.Bind(wx.EVT_COMBOBOX, self.on_pick_recipient, self.recipient_cb)

        recipient_top_sizer = wx.BoxSizer(wx.VERTICAL)
        recipient_top_sizer.Add(recipient_label, 0, wx.ALL | wx.LEFT, 5)

        recipient_input_line_sizer = wx.BoxSizer(wx.HORIZONTAL)
        recipient_input_line_sizer.Add(self.recipient_cb, 0, wx.ALL, 5)

        recipient_top_sizer.Add(recipient_input_line_sizer, 0, wx.ALL | wx.LEFT)
        top_sizer.Add(recipient_top_sizer, 0, wx.ALL | wx.LEFT, 5)

        # Message input area
        message_label = wx.StaticText(self.panel, wx.ID_ANY, 'Message text')
        self.message_input = wx.TextCtrl(self.panel, wx.ID_ANY, '', size=(300, 400),
                                         style=wx.TE_MULTILINE | wx.HSCROLL)

        message_sizer = wx.BoxSizer(wx.VERTICAL)
        message_sizer.Add(message_label, 0, wx.ALL | wx.CENTER, 5)
        message_sizer.Add(self.message_input, 0, wx.ALL | wx.CENTER, 5)

        top_sizer.Add(message_sizer, 0, wx.ALL | wx.LEFT, 5)

        # Checkboxes indicating whether to attach an address pad or
        # an address pad request
        self.include_address_pad_check = wx.CheckBox(self.panel, wx.ID_ANY,
                                                     label="Include address pad")
        top_sizer.Add(self.include_address_pad_check, 0, wx.ALL)
        self.include_address_pad_check.SetValue(self._include_address_pad)

        self.include_address_req_check = wx.CheckBox(self.panel, wx.ID_ANY,
                                                     label="Include address reuqest")
        top_sizer.Add(self.include_address_req_check, 0, wx.ALL)

        # Buttons that go at the bottom of the window
        self.ok_button = wx.Button(self.panel, wx.ID_ANY, 'OK')
        self.ok_button.Disable()
        cancel_button = wx.Button(self.panel, wx.ID_ANY, 'Cancel')
        self.Bind(wx.EVT_BUTTON, self.on_ok, self.ok_button)
        self.Bind(wx.EVT_BUTTON, self.on_cancel, cancel_button)

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.Add(self.ok_button, 0, wx.ALL | wx.CENTER, 5)
        button_sizer.Add(cancel_button, 0, wx.ALL | wx.CENTER, 5)

        top_sizer.Add(button_sizer, 0, wx.ALL | wx.CENTER, 5)

        # If we have a default recipient, we should now set that as the default
        if(self._recipient):
            self.ok_button.Enable()
            self.recipient_cb.SetValue(self._recipient.nickname)

        # Finally fit the top-level sizer to the panel
        self.panel.SetSizer(top_sizer)
        top_sizer.Fit(self)

    def fill_recipient_cb(self, combo_box):
        contacts = self._state_keeper.db.get_contacts()
        for c in contacts:
            combo_box.Append(c.nickname, c)

    def on_pick_recipient(self, event):
        """If a valid recipient has been picked, the send button may be enabled"""
        self.ok_button.Enable()
        self._recipient = self.recipient_cb.GetClientData(self.recipient_cb.GetSelection())

    def on_ok(self, event):
        """On press on OK, action will be taken"""
        util.enqueue_user_message(self._state_keeper.db, self._state_keeper.crypto,
                                  self._recipient, self.message_input.GetValue(),
                                  self.include_address_req_check.GetValue(),
                                  self.include_address_pad_check.GetValue())
        self.Close()

    def on_cancel(self, event):
        """On press of Cancel, the window will be closed without action"""
        self.Close()
