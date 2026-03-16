import socket
import struct
import select
import log
import time
import Message
import threading 
import string
import loginWindow
import chatWindow
import File
import Files
import chooseRoomWindow
import os
from win32com.shell import shell, shellcon
import hashlib
import uuid

users=""

class ClientConnect(object):
	
    def __init__(self,log,hostIp,port=300):
        self._log=log#logger
        self._mut=threading.Lock()#create mutex
        self._message=Message.Message(log)
        self._username=""
        self._path=""
        self._dirFile=shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)+"\\Chat Files\\"#dir of files of client
        self._dirFile=self._dirFile.replace("\\","/")
        self._dirPassword=shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)+"\\Password\\"
        self._dirPassword=self._dirPassword.replace("\\","/")
        self._quit=False
        self._startSendFile=""#for precentage on gui of send fle
        self._sendUpdate=False#if to send user list to gui after he create
        self._queue=[]#queue for revc message
        self._rooms=[]#the rooms the current user exist
        self._windows={}
        self._chooseRoom=None
        self._chooseRoomRun=False
        self._loginVar=None
        self._messages=[]#queue for messages
        self._filesList=Files.Files()
        self._createFolder()
        self._dirPassword=self._dirPassword + "Introduction.txt"
        self._createFileText(False)
        self._host = hostIp
        self._port = port
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)#create socket
        except socket.error,e:#exception to error
            self._log.saveToLog(str(e),"Error")
            if self._socket: 
                self.close() 
	
    def connect(self):
        "Initial connection"
        try:
            self._socket.connect((self._host, self._port))
            self._log.saveToLog("connect to host port")
        except Exception, e:
            self._log.saveToLog(str(e),"Error")
            raise Exception("Error connecting! "+str(e))
        
    def _receive(self,i,lenMessage,data):
        "recv message from server"
        try:
            while (len(data)<lenMessage) and self._quit==False:
                packedData = i.recv(lenMessage-len(data))#take the new data
                if not packedData:
                    return None
                print "here"
                data+=packedData
            self._log.saveToLog("receive message")
            return data
        except socket.timeout,e:
            self._log.saveToLog(str(e),"Error")
            return None
        
    def _decryptReceivedMessage(self):	
        "send to all client the message from server"
        try:
            rlist, wlist, xlist = select.select( [self._socket], [self._socket], [],0)#get all client who read and exist
            if rlist!=[]:
                for i in rlist:
                    data=''
                    data=self._receive(i,5,data)
                    if data==None:
                        return None
                    msglen=self._message._checkLenOfMessageById(data)
                    if msglen=="":
                        return None
                    if msglen=="more 11 bytes":#if user send message and message length is 11 byte
                        data=self._receive(i,11,data)
                        msglen=self._message._checkLenOfMessageById(data)

                    if msglen=="more 101 bytes":#if user send message and message length is 101 byte
                        data=self._receive(i,101,data)
                        msglen=self._message._checkLenOfMessageById(data)
                        
                    if msglen=="more 111 bytes":#if user send message and message length is 111 byte
                        print 1
                        data=self._receive(i,111,data)
                        print 2
                        msglen=self._message._checkLenOfMessageById(data)
                        print 3
                    packedData=self._receive(i,msglen,data)#get data from server
                    print 4
                    id,unpackedData,username,roomId,fileId=self._message._unpackdata(packedData)#unpack data from server
                    print 5
                    self._queue.append([id,unpackedData,username,roomId,fileId])
                    return "Ok"
            return ""
        except Exception,e:
            self._log.saveToLog(str(e),"Error")
            os._exit(1)
            return None
        
    def ManageMessages(self):
        "Take care of message server and send message"
        threading.Thread(target=self._takeCareAboutSend).start()
        self._userLogin()
        while self._quit==False:
            result=self._decryptReceivedMessage()

    def _giveUserDetails(self,username,password,operation):
        "Take the username and password that user wrote,hash password and send to server"
        username=str(username)
        password=str(password)
        if password=="":
            self._loginVar.errorMessage("you musr enter password!")
        else:
            print "username=",username
            print "password=",password
            print "operation=",operation
            salt=self._readFileText()
            if operation=="Login":
                hashed_password = self._hashPassword(password,salt)
                packedData=self._message._login(username,hashed_password)#login to server
            elif operation=="Register":
                hashed_password = self._hashPassword(password,salt)
                packedData=self._message._register(username,hashed_password)#login to server
            self._send(packedData)#send to server

    def _hashPassword(self,password,salt):
        "hash password with salt"
        hashed_password = hashlib.sha512(password + salt).digest()
        return hashed_password
        
    def _userLogin(self):
        "user login to server"
        threading.Thread(target=loginWindow.enableLogin,args=(self,)).start()
        
    def _takeCareAboutSend(self):
        "manage all the sends"
        while self._quit==False:
            self._mut.acquire() # yay mutex! this is a lock!
            if self._queue!=[]:#message that come from server 
                data=self._queue.pop()
                id=int(data[0])
                message=data[1]
                username=data[2]
                roomId=data[3]
                fileId=data[4]

                if id==5:#error login
                    self._loginVar.errorMessage(message)

                if id==34:#succes register
                    self._loginVar.errorMessage(message)
                
                if id==6:#if success login
                    "take the username"
                    self._loginVar.close()
                    self._loginVar=None
                    self._username=username
                    self._log.saveToLog("user logged in")
            
                if id==7:#turn on choose room/room list
                    "enable choose room gui"
                    if self._chooseRoomRun==True:
                        self._chooseRoom.setUserName(self._username)
                        self._chooseRoom.setRooms(message)
                        self._chooseRoom.createMenuOfRooms()
                        self._chooseRoom.Show()
                    else:
                        threading.Thread(target=chooseRoomWindow.enableChooseRoom,args=(message,self,self._username)).start()
                        
                    print self._loginVar
                    self._log.saveToLog("user choose room")
                    
                if id==8:#if the room that user choose is okay,turn on the gui of chat
                    pass
                    
                if id==15:#if user log in to room or exit from room
                    "update user lsit in chat gui"
                    message=message.strip(",")#remove ',' from the end of list
                    users=message.split(",")#users name string to list
                    self._windows[roomId]._addUsersNames(users)
                    self._log.saveToLog("update user name list in gui")
                    
                if id==11:#if server send message of client to other client,send this for gui
                    "set message that client send on chat gui"
                    self._windows[roomId].setValueOnViewScreen(message,username,"")
                    self._log.saveToLog("set value on gui screen") 

                if id==17:#server confirm the exit of client
                    "exit from chat"
                    roomsId=message.split()
                    for room in roomsId:#close all chat gui of user
                        print "SSSSSSSSSSSSSSSSSSSSSSSSSSSS",room
                        room=int(room)
                        self._windows[room].CloseWindow()
                    self._quit=True
                    self._log.saveToLog("client closing")
                    os._exit(1)#exit from all gui
                        
                if id==12:#admin get out this client from room
                    "exit from all gui"
                    self._windows[roomId]._onExitRoom()
                    self._log.saveToLog("admin get out user - close gui user")
                
                if id==20:#server send file to client
                    "write file to client folder"
                    filename=username
                    t3= threading.Thread(target=self._writeFile,args=(message,filename))
                    t3.start()

                if id==21:#SERVER GIVE FILENAME AND HIS ID
                    "append file object to file list object"
                    sendFileTime=roomId
                    self._appendFile(message,fileId,sendFileTime)

                if id==23:#server send message that user sended file
                    "set detail about file that client send on gui chat and give chatWindow file list object"
                    self._windows[roomId].takeFilesFromClinet(self._filesList)
                    self._log.saveToLog("send file list object to gui")
                    self._windows[roomId].setValueOnViewScreen(message,username,fileId)
                    self._log.saveToLog("set filename on gui screen")
                    
                if id==26:#server confirm that file is max 150mb
                    "send the file,his content and his size to server"
                    byte=self._readFile()
                    size=self._getSizeOfFile()
                    filename=self._path.split("\\")[-1]
                    packedData=self._message._sendedFileMessage(byte,size,filename,roomId,self._username)
                    self._send(packedData)
                    self._log.saveToLog("user send file")

                if id==27:#if client try to be in the same room twice
                    self._chooseRoom.toStart(False)

                if id==28:#if server send admin list
                    admins=message
                    self._windows[roomId].takeAdminsList(admins)
                
            self._mut.release()#unlock
            #if user write a message and want to send this,the gui will call to function in client that append the message and the room of message to list and client send her to servver for other client
            if self._messages!=[]:#message that come from gui
                self._mut.acquire() # yay mutex! this is a lock!
                data=self._messages.pop()
                self._mut.release()#unlock
                message=data[0]
                roomNumber=data[1]
                if message=="Go Another Room":
                    "send to server request to rooms"
                    packedData=self._message._requestRoomList(self._username)

                elif message=="ExitChat":
                    "client exit from chat"
                    packedData=self._message._exitFromServer(self._username,roomNumber)
                    self._log.saveToLog("user exit from chat")

                elif message=="ExitRoom":
                    "client exit from room"
                    packedData=self._message._exitChat(self._username,roomNumber)
                    self._send(packedData)
                    packedData=self._message._requestRoomList(self._username)
                    self._log.saveToLog("user exit from room")

                elif message=="Room":
                    "client choose room"
                    packedData=self._message._chooseRoom(self._username,roomNumber)

                elif "Get Out" in message:
                    "admin get out user"
                    usernameOut=message.split(",")[0]
                    packedData=self._message._adminGetOutUserToServer(self._username,usernameOut,roomNumber)

                elif "Append Admin" in message:
                    "admin append user to admin"
                    usernameToAdmin=message.split(",")[0]
                    packedData=self._message._adminAppendUserToAdmins(self._username,usernameToAdmin,roomNumber)

                elif "Mute User" in message:
                    "admin mute user"
                    usernameToMute=message.split(",")[0]
                    packedData=self._message._adminMuteUser(self._username,usernameToMute,roomNumber)

                elif "UnMuted User" in message:
                    "admin ummute user"
                    usernameToUnMute=message.split(",")[0]
                    packedData=self._message._adminUnMuteUser(self._username,usernameToUnMute,roomNumber)

                elif "Private Message" in message:  
                    userToSend=message.split(",")[0]
                    print "!#!#!#",userToSend
                    msg=message.split(",")[1]
                    print "^^&%$&5$&",msg
                    packedData=self._message._userPrivateMessage(self._username,userToSend,roomNumber,msg)
                    
                elif "Send File" in message:
                    "client send size file to server"
                    self._path=message.split(",")[0]
                    size=self._getSizeOfFile()
                    packedData=self._message._sendSizeFile(self._username,size,roomNumber)#check if size of file can be send

                elif "Downlaod File" in message:
                    "client request file from server"
                    id=message.split(",")[0]
                    id=int(id)
                    packedData=self._message._sendRequestFile(id,self._username)
                    
                else:
                    packedData=self._message._sendedMessage(message,roomNumber,self._username)
                    self._log.saveToLog("user send message")
                self._send(packedData)
        self.close()
        
    def _appendFile(self,filename,fileId,time):
        "append file object to file list object"
        new_file= File.File(filename,"",fileId,time)
        self._filesList.fileAdd(new_file)
        self._log.saveToLog("Client append file object to file list object")
    
    def _createFolder(self):
        "create folder for files"
        if os.path.isdir(self._dirFile)==False:#if the folder logs doesnt exist will create this folder
	    os.mkdir(self._dirFile)
            self._log.saveToLog("Client create dir-'Chat Files'")
        if os.path.isdir(self._dirPassword)==False:
            os.mkdir(self._dirPassword)
            self._log.saveToLog("Client create 'dir-password'")

    def _createFileText(self,registered):
        "create file text and save the salt of password"
        if os.path.isfile(self._dirPassword) == False or registered==True:
            salt=uuid.uuid4().bytes
            with open(self._dirPassword,"wb") as f:
                f.write(salt)
            self._log.saveToLog("Client write hash key in file")

    def _readFileText(self):
        "read the salt from text file"
        try:
            with open(self._dirPassword,"rb") as f:
                data=f.read()
                print len(data)
            return data
        except Exception,e:
            self._log.saveToLog(str(e))
            return ""

    def _readFile(self):
        "read binari file"
        try:
            with open(self._path, "rb") as f:
                byte = f.read()
                self._log.saveToLog("Client Read File")
            return byte
        except Exception,e:
            self._log.saveToLog(str(e),"Error")
            return ""

    def _getSizeOfFile(self):
        "get size of file"
        return int(os.path.getsize(self._path))
        self._log.saveToLog("get size of file")

    def _writeFile(self,byte,filename):
        "write file to folder"
        absoluteFile=self._dirFile + filename
        with open(absoluteFile, "wb") as f:
            byte = f.write(byte)
        os.startfile(absoluteFile)#open the file himself
        self._log.saveToLog("Client Write File to 'Chat Files' folder")
        
    def _guiGiveWindowVar(self,room,window):
        "window give himself"
        self._mut.acquire()
        self._windows[room]=window
        self._log.saveToLog("chatWindow give his self var")
        self._mut.release()

    def _loginGuiGiveVar(self,login):
        "login window give his var"
        self._loginVar=login

    def _chooseRoomGiveWindowVar(self,window,isExist):
        "choose room give himself"
        self._chooseRoom=window
        self._log.saveToLog("chooseRoomWindow give his self var")
        self._chooseRoomRun=isExist
        
    def _appendMessageFromGui(self,input,room):
        "the gui's communicate with client"
        print "append"
        print "input==>",input
        print "room==>",room
        self._messages.append([str(input),room])
        self._log.saveToLog("append message from gui to client")
        
    def _send(self,packedData):
        "send the packed data to server"
        try:
            self._socket.sendall(packedData)
            self._log.saveToLog("client sent data")
        except socket.error,e:			
            self._log.saveToLog(str(e))
            self.close()
            
    def close(self):
        try:
            self._socket.close()
            return
            self._log.saveToLog("client closing")
        except Exception,e:
            self._log.saveToLog(str(e))
