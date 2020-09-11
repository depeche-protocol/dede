import wx
import logging
import threading

import depeche.ui.common as util

from depeche.ui.state import DedeStateKeeper
from depeche.ui.wx.rendezvous_events import RendezvousBeginEvent
from depeche.ui.wx.rendezvous_events import RendezvousEndEvent


class RendezvousFrame(wx.Frame):
    """
    This frame will set up and trigger rendezvous actions. Please note
    that once the rendezvous has been started, progress is indicated
    on the main window status bar.
    """

    def __init__(self, parent: wx.Frame, state_keeper: DedeStateKeeper):
        super(RendezvousFrame, self).__init__(parent, title='Rendezvous operation')
        self._parent = parent

        # Set up logging
        self._logger = logging.getLogger(__name__)
        self._logger.info("Rendezvous window opened")

        self._state_keeper = state_keeper

        # Set up UI
        self.init_ui()
        self.Center()
        self.Show()

    def init_ui(self):
        self.panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        input_container = wx.FlexGridSizer(2, 2, 9, 25)

        alias = wx.StaticText(self.panel, label="Alias to send")
        secret = wx.StaticText(self.panel, label="Shared secret")
        self.alias_tc = wx.TextCtrl(self.panel)
        self.secret_tc = wx.TextCtrl(self.panel)

        input_container.Add(alias, 1, wx.ALIGN_CENTER_VERTICAL, 0, 0)
        input_container.Add(self.alias_tc, 1, wx.EXPAND, 0, 0)
        input_container.Add(secret, 1, wx.ALIGN_CENTER_VERTICAL, 0, 0)
        input_container.Add(self.secret_tc, 1, wx.EXPAND, 0, 0)

        input_container.AddGrowableCol(1, 1)

        vbox.Add(input_container,
                 flag=wx.ALL | wx.EXPAND, border=15)

        self.panel.SetSizer(vbox)

        cancelButton = wx.Button(self.panel, label='Cancel')
        cancelButton.Bind(wx.EVT_BUTTON, self.OnClose)

        startButton = wx.Button(self.panel, label='Start')
        startButton.Bind(wx.EVT_BUTTON, self.OnStart)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(cancelButton)
        hbox.Add(startButton)

        vbox.Add(hbox, flag=wx.ALIGN_RIGHT | wx.ALL, border=15)

    def OnClose(self, e):
        self.Close(True)

    def OnStart(self, e):
        secret = self.secret_tc.Value
        alias = self.alias_tc.Value

        # Start the actual operation thread and close the dialogue window - Ensure that thread calls
        # back to the main window on change of state
        worker = RendezvousThread(self._parent, self._state_keeper, secret, alias)
        self.Close(True)


class RendezvousThread(threading.Thread):
    """Worker thread to perform the long-running rendezvous job"""

    def __init__(self, notify_window: wx.Frame, state_keeper: DedeStateKeeper, secret: str, alias: str):
        threading.Thread.__init__(self)

        # Notify window is the window that should be sent the notification on
        # complation.
        self._notify_window = notify_window
        # State keeper used to access persistence and networking backends
        self._state_keeper = state_keeper
        self._secret = secret
        self._alias = alias
        # Start executing the operation immediately on creation. No fuss.
        self.start()

    def run(self):
        adapter = self._state_keeper.adapter
        crypto = self._state_keeper.crypto
        db = self._state_keeper.db

        wx.PostEvent(self._notify_window, RendezvousBeginEvent(None))
        db.connect_thread()

        info_success, key_id, rendezvous_info = util.rendezvous_produce_info(db, crypto, self._alias)
        success, foreign_info = adapter.rendezvous(self._secret, rendezvous_info)
        # TODO: Add step for actually accepting the foreign info before importing it into the DB
        #       This will mean that the "save info" will occur on the main thread instead of here
        if success:
            wx.PostEvent(self._notify_window, RendezvousEndEvent("Rendezvous successful"))
            util.rendezvous_save_info(db, key_id, rendezvous_info, foreign_info)
        else:
            wx.PostEvent(self._notify_window, RendezvousEndEvent("Rendezvous failed"))

        db.disconnect_thread()
