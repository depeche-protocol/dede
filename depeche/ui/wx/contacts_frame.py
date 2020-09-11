import sys
import wx
import logging

import depeche.ui.common as util

from depeche.ui.state import DedeStateKeeper


class ContactsFrame(wx.Frame):
    """
    This frame will allow us to view and manipulate known contacts.
    """

    def __init__(self, parent: wx.Frame, state_keeper: DedeStateKeeper):
        super(ContactsFrame, self).__init__(parent, title='Contacts')
        self._parent = parent

        # Set up logging
        self._logger = logging.getLogger(__name__)
        self._logger.info("Contacts window opened")

        self._state_keeper = state_keeper

        # Set up UI
        self.init_ui()
        self.Center()
        self.Show()

    def init_ui(self):
        self.contact_panel = wx.Panel(self)
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        self.list = wx.ListCtrl(self.contact_panel, -1, style=wx.LC_REPORT)
        self.list.InsertColumn(0, 'Contact alias', width=140)
        self.list.InsertColumn(1, 'Created at', width=130)
        self.list.InsertColumn(2, 'Own alias', wx.LIST_FORMAT_RIGHT, 90)

        contacts = self._state_keeper.db.get_contacts()
        index = 0
        for c in contacts:
            self.list.InsertItem(index, c.nickname)
            self.list.SetItem(index, 1, c.created_at)
            self.list.SetItem(index, 2, c.alias)
            index += 1

        hbox.Add(self.list, 1, wx.EXPAND)
        self.contact_panel.SetSizer(hbox)

        self.Centre()

    def OnClose(self, e):
        self.Close(True)
