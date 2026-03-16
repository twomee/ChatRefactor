import wx
import wx.lib.agw.gradientbutton as GB
import time
import threading
import chatWindow

DEFAULT_ALPHA = 242

class ChooseRoomWindow(wx.Frame):
    def __init__(self,parent,rooms,client,username,title):
        wx.Frame.__init__(self,parent, title=title,size=(500, 500),style=wx.CAPTION )
        self._InitUI(rooms,client,username)
        self.Center()
        self.Show()
        
    def _InitUI(self,rooms,client,username):
        "create the apperance of window"
        self._panel = wx.Panel(self)
        self._client=client
        self._client._chooseRoomGiveWindowVar(self,True)
        self._roomString=rooms.split()#for view the room list for users
        self._roomId=0
        self._windows={}
        self._startChat=True#if to start chat gui,default is yes
        self.popupmenu = None
        self._username=username
        self.createMenuOfRooms()
        self.SetTransparent(DEFAULT_ALPHA)#transparent background
        self.SetBackgroundColour(wx.Colour(64, 64, 64))#gray background color
        wx.StaticText(self._panel, -1,"Right-click on the panel to show a rooms",(25,25))
        menu = wx.Menu()
        hide = menu.Append(-1, "Hide")
        self.Bind(wx.EVT_MENU, self._onHide, hide)
        menuBar = wx.MenuBar()
        menuBar.Append(menu, "Menu")
        self.SetMenuBar(menuBar)

    def _onHide(self,event):
        self.Hide()

    def toStart(self,start):
        self._startChat=start
        
    def enableChat(self):
        "hide self and start chat"
        if self._startChat==True:
            self.Hide()
            chatWindow.MainGUI(None,self._client,self._roomId,self._username,"Chat")
            
    def createMenuOfRooms(self):
        "create the menu of rooms names"
        self.popupmenu = wx.Menu()
        count=1
        for roomName in self._roomString:
            item = self.popupmenu.Append(-1, roomName)
            self.Bind(wx.EVT_MENU, self._OnPopupItemSelected, item)
            count+=1
        self._panel.Bind(wx.EVT_CONTEXT_MENU, self._OnShowPopup)
        
    def _OnShowPopup(self, event):
        "on click right in mouse open menu"
        pos = event.GetPosition()
        pos = self._panel.ScreenToClient(pos)
        self._panel.PopupMenu(self.popupmenu, pos)
        
    def _OnPopupItemSelected(self, event):
        "show the room the user choose and take him"
        item = self.popupmenu.FindItemById(event.GetId())
        name = item.GetText()
        self._roomId=name.split("-")[0]
        self._roomId=int(self._roomId)
        wx.MessageBox("You selected item '%s'" % name)
        self._client._appendMessageFromGui("Room",self._roomId)
        self.enableChat()
        
    def setUserName(self,username):
        self._username=username

    def setRooms(self,rooms):
        self._roomString=rooms
        self._roomString=self._roomString.split()
        
    def _exitFromWindow(self):
        self.Close()

def enableChooseRoom(rooms,client,username):
    mut=threading.Lock()#create mutex
    app2 = wx.App(False)
    frame_2 = ChooseRoomWindow(None,rooms,client,username,title="Choosing Room")
    print wx.GetTopLevelWindows()
    app2.MainLoop()
