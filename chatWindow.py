# -*- coding: iso-8859-15 -*-
import wx
import chatClient
import threading
import time
import chooseRoomWindow
from win32com.shell import shell, shellcon
import win32gui
import os
import Files
import File

ID_EXIT_FROM_ROOM=1
ID_EXIT_FROM_CHAT=2
ID_ANOTHER_ROOM=3
ID_GET_OUT=4
ID_CHOOSE_FILE=5
ID_OPEN_FOLDER=6
ID_APPEND_ADMIN=7
ID_MUTE_USER=8
ID_UNMUTE_USER=9
ID_PRIVATE_MESSAGE=10
ID_START_RECORD=11
ID_OPEN_RECORDS=12
DEFAULT_ALPHA = 242
ADMINS=["ido"]
user=""
filename=""
id=0

class MainGUI(wx.Frame):
    def __init__(self, parent,client,roomId,username,title):
        wx.Frame.__init__(self, parent,roomId, title=title,style=wx.DEFAULT_FRAME_STYLE)
        self._initUI(client,roomId,username)
        self._menuBar()
        self.__set_properties()
        self.__do_layout()
        self.Center()
        self.Show()
        
    def _initUI(self,client,roomId,username):
        self._roomId=roomId
        self._client=client
        self._client._guiGiveWindowVar(self._roomId,self)
        self._path=shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)+"\\Chat Files\\"
        self._menu=None
        self._takeFile=None#menu of file to download
        self._username=username
        self._admins=[]
        self._index=0
        self._fileList=None
        self._messageNumber=0
        self._downloadNumber=7
        self.SetTransparent(DEFAULT_ALPHA)#transparent background
        self.list_ctrl_1 = wx.ListCtrl(self, -1, style=wx.LC_REPORT|wx.SUNKEN_BORDER)#for users list who connect
        self.list_ctrl_1.InsertColumn(0, 'Users')
        self.list_ctrl_2 = wx.ListCtrl(self, -1, style=wx.LC_REPORT|wx.SUNKEN_BORDER|wx.TE_MULTILINE)#for see the message which send to server
        self.list_ctrl_2.InsertColumn(0, 'Messages')#for see the message which send to server
        self.list_ctrl_2.SetColumnWidth(0, 1000)
        self.text_ctrl_2 = wx.TextCtrl(self, -1, "", style=wx.TE_MULTILINE,size=(1000,1000))#to write a message and send for server
        self.text_ctrl_2.Bind(wx.EVT_KEY_DOWN, self.OnEnter)#on enter,mesage will be send to server
        self.Bind(wx.EVT_CLOSE, self._onClickExit)
    
    def _addUsersNames(self,users):
        "add to chat gui the users are connect"
        self._index=0
        self.list_ctrl_1.DeleteAllItems()
        for user in users:
            print "user==>",user
            self.list_ctrl_1.InsertStringItem(self._index,user)
            content=str(self._roomId)+":"+self._username
            print "index=", self._index
            self._index += 1
        if content in self._admins:
            self.list_ctrl_1.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self._OnClick, self.list_ctrl_1)
        else:
            self.list_ctrl_1.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self._OnPrivateMessage, self.list_ctrl_1)
   
    def takeAdminsList(self,adminList):
        "save admin list in chat gui"
        self._admins=adminList
        
    def _OnClick(self, event):
        "admin open menu of get out user"
        global user
        user=event.GetText()
        print user
        user=str(user)
        self._menu = wx.Menu()
        getOut=self._menu.Append(ID_GET_OUT, 'Kick Out')    
        self.Bind(wx.EVT_MENU, self._OnPopupItemSelected,getOut)
        appendAdmin=self._menu.Append(ID_APPEND_ADMIN, 'Append To Admins')    
        self.Bind(wx.EVT_MENU, self._OnPopupItemSelected,appendAdmin)
        muteUser=self._menu.Append(ID_MUTE_USER, 'Mute User')    
        self.Bind(wx.EVT_MENU, self._OnPopupItemSelected,muteUser)
        unmutedUser=self._menu.Append(ID_UNMUTE_USER, 'UnMute User')    
        self.Bind(wx.EVT_MENU, self._OnPopupItemSelected,unmutedUser)
        privateMessage=self._menu.Append(ID_PRIVATE_MESSAGE, 'Send Private Message To This User')    
        self.Bind(wx.EVT_MENU, self._OnPopupItemSelected,privateMessage)
        self.PopupMenu(self._menu)
        self._menu.Destroy()

    def _OnPrivateMessage(self,event):
        "user can send private message to another user"
        global user
        user=event.GetText()
        print user
        user=str(user)
        self._menu = wx.Menu()
        privateMessage=self._menu.Append(ID_PRIVATE_MESSAGE, 'Send Private Message To This User')    
        self.Bind(wx.EVT_MENU, self._OnPopupItemSelected,privateMessage)
        self.PopupMenu(self._menu)
        self._menu.Destroy()
    
    def setValueOnViewScreen(self,message,userName,fileId):
        "set string of user on chat gui"
        print "add"
        if fileId!="":
            data=userName+":"+str(fileId)+"-"+message
        elif userName!="":
            data=userName+":"+message
        else:
            data=message
        lines=data.split("\n")
        for line in lines:
            self.list_ctrl_2.InsertStringItem(self._messageNumber,line)
            if "-filename=" in line:#if the row is with id and filename
                self.list_ctrl_2.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self._OnClickFile, self.list_ctrl_2)
            self._messageNumber+=1
            
    def takeFilesFromClinet(self,files):
        "take file list object from client"
        self._fileList=files
        
    def _OnClickFile(self,e):
        "open menu of download file"
        global filename,id
        text=e.GetText()
        if "-filename=" in text:
            id=text.split("-")[0].split(":")[1]#take thi id of file
            id=int(id)
            #create menu of download files
            self._takeFile = wx.Menu()
            downloadFile=self._takeFile.Append(self._downloadNumber, 'Download')
            self._downloadNumber+=1
            self.Bind(wx.EVT_MENU, self._OnPopupFileSelected,downloadFile)
            self.PopupMenu(self._takeFile)
            self._takeFile.Destroy()
            
    def OnEnter(self, e):
        "send message"
        if e.GetKeyCode() == wx.WXK_RETURN or e.GetKeyCode() == wx.WXK_NUMPAD_ENTER:
            if self.text_ctrl_2.GetValue()!="":#if user write nothing
                input = self.text_ctrl_2.GetValue()#get text of user write
                self._checkInput(input)
                self._client._appendMessageFromGui(input,self._roomId)#send input for client class
            self.text_ctrl_2.SetValue("")
        else:
            e.Skip()

    def _checkInput(self,input):
        "if input contain unilegal words"
        if "-filename=" in input or "size=" in input:
            string="You cant use in this words!"
            wx.MessageBox(string)
            
    def _OnPopupFileSelected(self,event):
        "on click download file"
        item = self._takeFile.FindItemById(event.GetId())
        if item!=None:
            name = item.GetText()
            string="You selected" + name + "\nYou can see your files in menu:->File->open folder files"
            wx.MessageBox(string)
            self._downloadUserFile()
        
    def _OnPopupItemSelected(self, event):
        "show the room the user choose and take him"
        item = self._menu.FindItemById(event.GetId())
        name = item.GetText()
        print "^^^^^^^^^^^^^^^^^^^^^^^^",name
        if name=="Kick Out":
            if item!=None:
                if user==self._username:
                    string="you cannot choose your user!"
                    wx.MessageBox(string)
                else:
                    string="You selected item '%s'" % name
                    wx.MessageBox(string)
                    self._getOut()
        elif name=="Append To Admins":
            if item!=None:
                if user==self._username:
                    string="you cannot choose your user!"
                    wx.MessageBox(string)
                else:
                    string="You selected item '%s'" % name
                    wx.MessageBox(string)
                    self._appendAdmin()
        elif name=="Mute User":
            if item!=None:
                if user==self._username:
                    string="you cannot choose your user!"
                    wx.MessageBox(string)
                else:
                    string="You selected item '%s'" % name
                    wx.MessageBox(string)
                    self._muteUser()
                    
        elif name=="UnMute User":
            if item!=None:
                if user==self._username:
                    string="you cannot choose your user!"
                    wx.MessageBox(string)
                else:
                    string="You selected item '%s'" % name
                    wx.MessageBox(string)
                    self._adminUnMuteUser()

        elif name=="Send Private Message To This User":
            if item!=None:
                if user==self._username:
                    string="you cannot choose your user!"
                    wx.MessageBox(string)
                else:
                    string="You selected item '%s'" % name
                    wx.MessageBox(string)
                    self._privateMessage()
                    
    def _OnExit(self, event):
        self.Close()
    
    def _menuBar(self):
        self._menubar = wx.MenuBar()
        fileMenu = wx.Menu()
        AnotherRoom=fileMenu.Append(ID_ANOTHER_ROOM, '&Join Another Room')
        self.Bind(wx.EVT_MENU, self._onGoAnotherRoom, AnotherRoom)
        fileMenu.AppendSeparator()
        addFile = wx.Menu()
        chooseFile=addFile.Append(ID_CHOOSE_FILE, 'Add File')
        self.Bind(wx.EVT_MENU, self._openBrowserFiles, chooseFile)
        showBrowser=addFile.Append(ID_OPEN_FOLDER, 'Open Folder Files')
        self.Bind(wx.EVT_MENU, self._showBrowser, showBrowser)
        imp = wx.Menu()
        ExitRoom=imp.Append(ID_EXIT_FROM_ROOM, 'Exit From Room')
        self.Bind(wx.EVT_MENU, self._onExitRoomEvent, ExitRoom)
        ExitChat=imp.Append(ID_EXIT_FROM_CHAT, 'Exit From Chat')
        self.Bind(wx.EVT_MENU, self._onExitChat, ExitChat)
        fileMenu.AppendMenu(0, 'Exit', imp)
        self._menubar.Append(fileMenu, '&Menu')
        self._menubar.Append(addFile, '&File')
        self.SetMenuBar(self._menubar)
        
    def _showBrowser(self,e):
        "open folder files of clinet"
        os.popen("start explorer " + self._path)
        
    def _openBrowserFiles(self,e):
        "open browser of choose files"
        try:
            mydocs_pidl = shell.SHGetFolderLocation (0, shellcon.CSIDL_DESKTOP, 0, 0)
            pidl, display_name, image_list = shell.SHBrowseForFolder (
              win32gui.GetDesktopWindow (),
              mydocs_pidl,
              "Select a file",
              shellcon.BIF_BROWSEINCLUDEFILES,
              None,
              None
            )
            path = shell.SHGetPathFromIDList (pidl)
            self._checkPath(path)
            self._onChooseFile(path)
        except:
            pass

    def _checkPath(self,path):
        "check if path is file and not folder"
        if os.path.isdir(path):
            string="you cant send this!"
            wx.MessageBox(string)

    def _getSizeOfFile(self,path):
        "size of file"
        return int(os.path.getsize(path))

    def _onChooseFile(self,path):
        "send size of file to client"
        message=path+",Send File"
        size=self._getSizeOfFile(path)
        size=size/(1024*1024.0)#convert from byte to mb
        self._client._appendMessageFromGui(message,self._roomId)
        if size>150.00:#if the file is more than 150mb,the file will not send
            wx.MessageBox("you cant send file over 150mb!")
            
    def _enableProgressBar(self,time):
        "show progress bar of file download"
        max = 80
        dlg = wx.ProgressDialog("Progress dialog example",
                               "An informative message",
                               maximum = max,
                               parent=self,
                               style = wx.PD_CAN_ABORT
                                | wx.PD_APP_MODAL
                                | wx.PD_ELAPSED_TIME
                                | wx.PD_ESTIMATED_TIME
                                | wx.PD_REMAINING_TIME
                                )
 
        keepGoing = True
        count = 0
        while keepGoing and count < max:
            count += 1
            wx.MilliSleep(time)
            if count >= max / 2:
                (keepGoing, skip) = dlg.Update(count, "Half-time!")
            if count == max:
                (keepGoing, skip) = dlg.Update(count, "Done!")
            else:
                (keepGoing, skip) = dlg.Update(count)      
        dlg.Destroy()
        
    def _downloadUserFile(self):
        "enable progress bar"
        message=str(id)+","+"Downlaod File"
        self._client._appendMessageFromGui(message,self._roomId)
        sendFileTime=self._fileList.getTimeById(id)
        sendFileTime=str(sendFileTime)+"0"
        sendFileTime=int(sendFileTime)
        self._enableProgressBar(sendFileTime)

    def _privateMessage(self):
        "user send message with content to another user"
        if self.text_ctrl_2.GetValue()=="":
            string="you must write message and then click on send private message!"
            wx.MessageBox(string)
        else:
            message=user+","+str(self.text_ctrl_2.GetValue())+",Private Message"
            self._client._appendMessageFromGui(message,self._roomId)
            self.text_ctrl_2.SetValue("")
            
    def _adminUnMuteUser(self):
        message=user+",UnMuted User"
        self._client._appendMessageFromGui(message,self._roomId)

    def _muteUser(self):
        message=user+",Mute User"
        self._client._appendMessageFromGui(message,self._roomId)

    def _appendAdmin(self):
        message=user+",Append Admin"
        self._client._appendMessageFromGui(message,self._roomId)
        
    def _getOut(self):
        message=user+",Get Out"
        self._client._appendMessageFromGui(message,self._roomId)

    def _onGoAnotherRoom(self,e):
        message="Go Another Room"
        self._client._appendMessageFromGui(message,self._roomId)

    def _onExitRoomEvent(self,e):
        message="ExitRoom"
        self._client._appendMessageFromGui(message,self._roomId)
        self.CloseWindow()

    def _onExitChat(self,e):
        print "in"
        message="ExitChat"
        self._client._appendMessageFromGui(message,self._roomId)

    def _onClickExit(self,e):
        print "in"
        message="ExitChat"
        self._client._appendMessageFromGui(message,self._roomId)
    
    def _onExitRoom(self):
        "when admin get out user,he exit from room from here"
        message="ExitRoom"
        self._client._appendMessageFromGui(message,self._roomId)
        self.CloseWindow()

    def CloseWindow(self):
        self.Destroy()
    
    def __set_properties(self):
        # begin wxGlade: MainGUI.__set_properties
        self.SetTitle("Chat-"+self._username+"    "+"Room Number:"+str(self._roomId))
        font = wx.Font(pointSize=14, family=wx.ROMAN, style=wx.NORMAL, weight=wx.BOLD,underline=False, face="", encoding=wx.FONTENCODING_DEFAULT)
        self.list_ctrl_2.SetFont(font)
        self.SetBackgroundColour(wx.Colour(64, 64, 64))
        self.list_ctrl_2.SetForegroundColour((0,25,51))#blue dark color
        self.list_ctrl_2.SetBackgroundColour((192,192,192))#gray color
        self.text_ctrl_2.SetBackgroundColour((255,204,153))#orange color
        self.list_ctrl_1.SetBackgroundColour((255,204,204))#red color
        self.list_ctrl_1.SetFont(font)
        self.list_ctrl_1.SetForegroundColour((0,53,102))#blue color
        self.list_ctrl_1.SetMinSize((100, 264))
        self.list_ctrl_2.SetMinSize((500, 300))
        self.text_ctrl_2.SetMinSize((0, 100))
        # end wxGlade

    def __do_layout(self):
        # begin wxGlade: MainGUI.__do_layout
        sizer_1 = wx.BoxSizer(wx.VERTICAL)
        sizer_2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_3 = wx.BoxSizer(wx.VERTICAL)
        sizer_4 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_5 = wx.BoxSizer(wx.VERTICAL)
        sizer_6 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_4.Add((20, 20), 1, wx.EXPAND, 0)
        sizer_5.Add((50, 20), 1, wx.EXPAND, 0)
        sizer_6.Add((50, 20), 1, wx.EXPAND, 0)
        sizer_1.Add(sizer_4, 0, wx.EXPAND, 0)
        sizer_2.Add(self.list_ctrl_1, 0, wx.ALL|wx.EXPAND, 5)
        sizer_2.Add(sizer_5, 0, wx.EXPAND, 5)
        sizer_2.Add(self.list_ctrl_2, 0, wx.ALL|wx.EXPAND, 5)
        sizer_2.Add(sizer_3, 0, wx.EXPAND, 0)
        sizer_1.Add(sizer_2, 1, wx.EXPAND, 0)
        sizer_1.Add(sizer_6, 0, wx.ALL|wx.EXPAND, 5)
        sizer_1.Add(self.text_ctrl_2, 0, wx.ALL|wx.EXPAND, 5)
        self.SetSizer(sizer_1)
        sizer_1.Fit(self)
        self.Layout()
