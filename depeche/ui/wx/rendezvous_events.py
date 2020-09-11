import wx

# Define events that the main frame is interested in
EVT_RENDEZVOUS_BEGIN_ID = wx.NewId()
EVT_RENDEZVOUS_END_ID = wx.NewId()


class RendezvousBeginEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_RENDEZVOUS_BEGIN_ID)
        self.data = data


class RendezvousEndEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_RENDEZVOUS_END_ID)
        self.data = data
