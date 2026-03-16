import wx
import wx.lib.agw.gradientbutton as GB
import chatClient
import os

username=""
password=""
DEFAULT_ALPHA = 242

class loginWindow(wx.Frame):
    def __init__(self, parent,client, title):
        super(loginWindow, self).__init__(parent, title=title,
            style=wx.DEFAULT_FRAME_STYLE)
        self.WIDTH = 400
        self._InitUI(client)
        self.Center()
        self.Show()

    def _InitUI(self,client):
        "create the apperance of window"
        self._panel = wx.Panel(self)
        self._client=client
        self._client._loginGuiGiveVar(self)
        self._user_name_lbl = wx.StaticText(self._panel, label="User name:")
        self._user_name_txt = wx.TextCtrl(self._panel)
        self._password_lbl = wx.StaticText(self._panel, label="Password:")
        self._password_txt = wx.TextCtrl(self._panel,style=wx.TE_PASSWORD)
        self._login_button = ""
        self._register_button = ""
        self.SetTransparent(DEFAULT_ALPHA)#transparent background
        fg_sizer = wx.FlexGridSizer(cols=2, vgap=5, hgap=5)
        fg_sizer.Add(self._user_name_lbl, 0, wx.ALIGN_RIGHT | wx.ALIGN_BOTTOM)#add label to window
        fg_sizer.Add(self._user_name_txt, 0, wx.EXPAND)
        fg_sizer.Add(self._password_lbl, 0, wx.ALIGN_RIGHT | wx.ALIGN_BOTTOM)
        fg_sizer.Add(self._password_txt, 0, wx.EXPAND)
        fg_sizer.AddGrowableCol(1)
        panel_sizer = wx.BoxSizer(wx.VERTICAL)
        panel_sizer.Add(fg_sizer, 0, wx.ALL | wx.EXPAND, 5)	
	self._loginButton()
        panel_sizer.Add(self._login_button, 0, wx.EXPAND | wx.ALL, 5)
        self._registerButton()
        panel_sizer.Add(self._register_button, 0, wx.EXPAND | wx.ALL, 5)
        self._panel.SetSizer(panel_sizer)
        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(self._panel, 1, wx.EXPAND)#add the panel to the window
        self.SetSizer(frame_sizer)
        self.SetMinSize((self.WIDTH, -1))#set the size of the window
        self.Fit()
        self.Bind(wx.EVT_CLOSE, self._onClickExit)
        
    def errorMessage(self,message):
        "if user not type the username and password"
        wx.MessageBox(message)
        self._user_name_txt.SetValue("")
        self._password_txt.SetValue("")
        
    def close(self):
        self.Destroy()
    	
    def _loginButton(self):
        "create login button"
        self._login_button = GB.GradientButton(self._panel, label="Login")
        self._login_button.Bind(wx.EVT_BUTTON,self._OnClickLogin)
        self._login_button.SetToolTip(wx.ToolTip("Login"))
        
    def _registerButton(self):
        self._register_button = GB.GradientButton(self._panel, label="Register")
        self._register_button.Bind(wx.EVT_BUTTON,self._OnClickRegister)
        self._register_button.SetToolTip(wx.ToolTip("Register"))
        
    def _OnClickLogin(self,event):
	"cause to button to do something when click them"
	global username,password
	username=self._user_name_txt.GetValue()
	password=self._password_txt.GetValue()
	self._client._giveUserDetails(username,password,"Login")

    def _OnClickRegister(self,event):
	"cause to button to do something when click them"
	global username,password
	username=self._user_name_txt.GetValue()
	password=self._password_txt.GetValue()
	self._client._giveUserDetails(username,password,"Register")
	
    def _onClickExit(self,e):
        os._exit(1)

def enableLogin(client):
    app = wx.App(False)
    window=loginWindow(None,client, title="Login")
    app.MainLoop()
