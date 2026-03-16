# -*- coding: cp1255 -*-
import socket
import struct
import select
import threading 
import time
import log
import Message
import Room
import Rooms
import Users
import User
import chatWindow
import File
import Files
import Database
import os
import datetime
from mimetypes import MimeTypes
import tornado.ioloop
import tornadoWeb
import Settings
from win32com.shell import shell, shellcon
import sys

class ServerConnect(object):

    ADMINS=["ido"]
    USERNAME="ido"
    PASSWORD = '''\xf7\x92\xa3\x1aR\xa0\x8f\x15\x7f\xcc\x1c\x85Mb\xd4%\x99\xba%[H\x08\x05\x83\xb9_\xb5\xee\xea\xe7\xfc3\x17\x889=\xacTE\x08l\x07P\\\xeba 9\x0fN$HFnJ/\x04\xde\xe4\x03=\xd7\x8d\xf9'''
    SALT = "\x18\xd4\xcb\x0c\x9e\xb9M\xa8\xb4&D\xe7v\xc3F\xa2"
	
    def __init__(self,log,host="",port=300):
        self._log=log#logger
        self._allsock=""
        self._exit=False
        self._blockChat=False
        self._startSendFile=""
        self._mime = MimeTypes()
        self._mut=threading.Lock()#create mutex
        self._open_sockets=[]
        self._queue=[]#queue to append all the recv message from clients
        self._message=Message.Message(log)
        self._roomlist = Rooms.Rooms()
        self._roomNumber=1
        self.addRoom("politics")
        self.addRoom("sports")
        self.addRoom("movies")
        self._dirFile=shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)+"\\Server Files\\"
        self._dirFile=self._dirFile.replace("\\","/")
        self._dirFileWeb=shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)+"\\Files From Web\\"
        self._createFolder()
        self._createAdmins()
        self._usersToMute=[]
        self._loggedUserList=Users.Users()
        self._database=Database.Database("DB")
        self._webDatabase=Database.Database("webDB")
        self._webDetails()
        self._fileCount=1
        self._filesList=Files.Files()
        self._getIntoWeb=False
        self._new_socket=""
        self._host = host
        self._port = port
	try:
            self._listening_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)#create socket
            self._log.saveToLog("create socket")
	except socket.error,e:#exception to error
            self._log.saveToLog(str(e),"Error")
	    if self._listening_socket: 
                self.close(self._listening_socket)
        self._application = None
        threading.Thread(target=self._enableTorando).start()     

    def _enableTorando(self):
        settings = {
            #give the html page
            "template_path": Settings.TEMPLATE_PATH,
            "static_path": Settings.STATIC_PATH,
        }
        template_path=os.path.abspath(os.path.dirname(sys.argv[0]))+"\\website"
        css_path=os.path.abspath(os.path.dirname(sys.argv[0]))+"\\website\\Css"
        images_path=os.path.abspath(os.path.dirname(sys.argv[0]))+"\\website\\Photo"
        fonts_path=os.path.abspath(os.path.dirname(sys.argv[0]))+"\\website\\fonts"
        handlers=[
            (r"/", tornadoWeb.indexHandler,{"server":self}),
            (r"/simpleUser.html", tornadoWeb.simpleUserHandler,{"server":self}),
            (r"/login.html", tornadoWeb.loginHandler,{"server":self,"db":self._webDatabase,"salt":self.SALT}),
            (r"/manageChat.html", tornadoWeb.manageChatHandler,{"server":self}),
            (r"/manageDB.html", tornadoWeb.manageDBHandler,{"server":self}),
            (r"/manageAdmins.html", tornadoWeb.manageAdminHandler,{"users":self._loggedUserList,"server":self}),
            (r"/downloadFile.html", tornadoWeb.downloadFileHandler,{"server":self}),
            (r"/admin.html", tornadoWeb.adminHandler,{"server":self}),
            (r"/reset.html", tornadoWeb.resetDBHandler,{"server":self}),
            (r"/block.html", tornadoWeb.BlockHandler,{"server":self}),
            (r"/enable.html", tornadoWeb.EnableHandler,{"server":self}),
            (r"/Photo/(.*)",tornado.web.StaticFileHandler, {"path": images_path}),
            (r"/Css/(.*\.css)",tornado.web.StaticFileHandler, {"path": css_path}),
            (r"/fonts/(.*\.ttf)",tornado.web.StaticFileHandler, {"path": fonts_path}),
            (r"/rooms.html", tornadoWeb.RoomsHandler,{"rooms":self._roomlist,"server":self}),
            (r"/addRoom.html", tornadoWeb.addRoomHandler,{"server":self}),
            (r"/room.html", tornadoWeb.roomHandler,{"server":self}),
            (r"/files.html", tornadoWeb.filesHandler,{"files":self._filesList,"server":self}),
            (r"/users.html", tornadoWeb.UsersHandler,{"users":self._loggedUserList,"server":self})
            ]
        self._application = tornado.web.Application(handlers,**settings)
        self._application.listen(150)
        tornado.ioloop.IOLoop.instance().start()
        
    def _webDetails(self):
        "register of admin to the website of the chat"
##        username="ido"
##        password="1234"
        isExist=self._webDatabase.isExist(self.USERNAME)
        if isExist==False:
            self._webDatabase.addValue(self.USERNAME,self.PASSWORD)
    
    def manageAdmin(self,name):
        "change user to admin by the website"
        username=name
        socket=self._loggedUserList.getSocketByUser(username)
        user=self._loggedUserList.getUserBySocket(socket)#get user object
        rooms=user.getRoom()#get all rooms of user
        for room in rooms:
            roomId=room.getId()
            result=self._checkIfUserIsAdmin(roomId,username)#if the user that append to admins is not admin
            if result==False:
                self._appendAdminToFile(room,username)
                self._sendAdminsList("",roomId,room)
                self._sendUserList("",roomId,room)
                unpackData=username + " has become to admin by the primary admin"
                self._sendMessageOfClintToClient(unpackData,roomId,room,"","")

    def confirmGoToWeb(self):
        "confirm access to the website,when admin login"
        self._getIntoWeb=True

    def notConfirmGoToWeb(self):
        "cancel the confirm access to the website,when admin logout"
        self._getIntoWeb=False
    
    def getConfirm(self):
        "get state of access"
        return self._getIntoWeb
    
    def downloadFileFromWeb(self,filename):
        "admin choose to download file of user to his computer"
        byte=self._readFile(filename)
        self._writeFile(byte,filename,self._dirFileWeb)

    def openBrowser(self):
        "open folder where chat's files download"
        os.popen("start explorer " + self._dirFileWeb)
        
    def resetDatabase(self):
        "reset the database of the chat,users cant login,they deleted"
        self._database.clearDatabase()

    def blockChat(self,degel):
        "close the chat and kick out all the users from all the rooms,nobody can get to the chat"
        self._blockChat=degel
        self._kickOutAllUsers()

    def enableChat(self,degel):
        "open the chat,everyone can get in to the chat"
        self._blockChat=degel

    def addRoom(self,name):
        "add room to the chat"
        room=Room.Room(str(name),self._roomNumber,self._log)
        self._roomlist.roomAdd(room)
        self._roomNumber+=1

    def _removeUserDetailes(self,socket,username):
        "remove user's details from all the lists in the server"
        try:
            try:#if user not insert to server
                self._open_sockets.remove(socket)#delete from server
                self._allsock.remove(socket)
            except Exception,e:#do not nothing
                self._log.saveToLog(str(e))
            self._loggedUserList.deleteUser(username)#delete from rooms
            self._log.saveToLog("delete user socket from lists")
        except Exception,e:
            self._log.saveToLog(str(e),"Error")

    def _sendQunfirmQuit(self,user,socket):
        "confirm quit to client,exit"
        roomsOfUserId=user.getRoomsId()
        stringRooms=map(str,roomsOfUserId)
        stringRooms=" ".join(stringRooms)
        packedData=self._message._quitConfirm(stringRooms)
        self._sendone(packedData,socket)#send exit message for client

    def _kickOutAllUsers(self):
        "kick out all the user from all the rooms in chat"
        usersInChat=self._loggedUserList.getUsers()[0:]#take all the users,zugi and ezugi
        for userInChat in usersInChat:
            usernameInChat = userInChat.getUserName()#get username
            socket=self._loggedUserList.getSocketByUser(usernameInChat)#get socket
            self._sendQunfirmQuit(userInChat,socket)
            rooms=userInChat.getRoom()#get all rooms of user
            self._removeUserDetailes(socket,usernameInChat)#remove user from server list
            for room in rooms:
                roomId=room.getId()
                print room
                print roomId
                content=str(roomId)+":"+usernameInChat
                admins=self._readAdminsFile()
                self._deleteAdminFromFile(content,admins)
                room.deleteUserSocket(usernameInChat)
                self._deleteFromMuted(roomId,usernameInChat)
    
    def connect(self):
        "Initial connection"
        try:
            self._listening_socket.bind((self._host,self._port))
            self._listening_socket.listen(1)
        except Exception, e:
            self._log.saveToLog(str(e),"Error")
	
    def _selectSockets(self):
        "Create option of select in sockets"
        try:
            self._allsock=[self._listening_socket]+self._open_sockets#all sockets - ALSO NEED THE OPEN_SOCKETS FROM ROOMS
            rlist,wlist,elist=select.select(self._allsock,[],[])#create the select option
            return rlist
        except Exception,e:
            self._log.saveToLog(str(e),"Error")
            return None     
	
    def _appendNewSocket(self):
        "Accpet client and append him to list"
        try:
            self._new_socket,address=self._listening_socket.accept()#waiting to connect to client
            self._log.saveToLog("accept client")
            self._open_sockets.append(self._new_socket)#append the new client to list of sockets
            self._log.saveToLog("append socket to list")
        except Exception, e:
            self._log.saveToLog(str(e))
            raise Exception("Error connecting! "+str(e),"Error")
		
    def _receive(self,i,lenMessage,data):
        "Get message from client"
        try:
            while len(data)<lenMessage:
                print "before recv"
                size=lenMessage-len(data)
                packedData = i.recv(size)#waiting to get a message from client
                if not packedData:
                    return None
                data+=packedData
            return data
            self._log.saveToLog("server receive message")
        except socket.error,e:
            self._log.saveToLog(str(e),"Error")
            self._open_sockets.remove(i)
            self._allsock.remove(i)
            try:
                userR=self._loggedUserList.getUserBySocket(i)
                username=userR.getUserName()
                if username==None:
                    return None
                packedData=self._message._exitFromServer(username,0)
                self._queue.append((i,packedData))
                self.close(i)
            except Exception,e:
                self._log.saveToLog(str(e),"Error")           
			
    def _sendone(self,packedData,socket):
        "send the packed data to all client"
        for i in self._open_sockets:#send for all open socket in server 
            if i==socket:
                self._send(packedData,i)             				
				
    def _send(self,packedData,i):
        #send the packed data to client
        try:
            i.sendall(packedData)
            self._log.saveToLog("server send message")
        except socket.error,e:			
            self._log.saveToLog(str(e),"Error")
				
    def ManageMessages(self):
        "Take care of message from client"
        t1= threading.Thread(target=self._loop)
        t1.start()
        while self._exit==False:
            rlist=self._selectSockets()
            if rlist==None:
                self._exit=True
                self.close(self._listening_socket)
            
            if rlist!=[]:
                for i in rlist:#if the socket in read socket
                    if i is self._listening_socket:#if the listening socket get new socket(if new socket connect to server)
                        self._appendNewSocket()
                    else:
                        if i in self._open_sockets:
                            data=''
                            data=self._receive(i,5,data)
                            msglen=self._message._checkLenOfMessageById(data)
                            if msglen=="":
                                continue
                            if msglen=="more 111 bytes":#if user send message and message length is 101 byte
                                data=self._receive(i,111,data)
                                msglen=self._message._checkLenOfMessageById(data)
                                print msglen

                            if msglen=="more 101 bytes":#if user send message and message length is 101 byte
                                data=self._receive(i,101,data)
                                msglen=self._message._checkLenOfMessageById(data)

                            packedData=self._receive(i,msglen,data)
                            self._queue.append((i,packedData))
					
    def _appendUser(self,username,i):
        "check if user exist in chat"
        new_user= User.User(username,i)
        self._loggedUserList.userAdd(new_user)
        self._log.saveToLog("append user object to user list object")	

    def _checkUserInRoom(self,room,user):
        "check if user in room"
        print "rrrrrrrrr",user.getRoom()
        if room in user.getRoom():
            return True 
        return False
		
    def _sendOkayRoom(self,socket,roomId):
        packedData=self._message._okayRoom(roomId)
        self._sendone(packedData,socket)
        
    def _sendUserList(self,socket,roomId,room):
        users=room.getUsersString()
        packedData=self._message._userList(users,roomId)
        room.sendToGroup(packedData,socket)#send to all users the change of users list in gui

    def _sendRoomList(self,socket,stringRoom):
        packedData=self._message._roomList(stringRoom)
        self._sendone(packedData,socket)

    def _sendAdminsList(self,socket,roomId,room):
        admins=self._readAdminsFile()
        packedData=self._message._adminList(admins,roomId)
        room.sendToGroup(packedData,socket)

    def _sendMessageOfClintToClient(self,unpackData,roomId,room,username,socket):
        packedData=self._message._sendedMessageFromClient(unpackData,roomId,username)
        room.sendToGroup(packedData,socket)

    def _sendMessageToOneClient(self,unpackData,roomId,username,socket):
        packedData=self._message._sendedMessageFromClient(unpackData,roomId,username)
        self._sendone(packedData,socket)

    def _sendMessageFileOfClintToClient(self,unpackData,roomId,room,username,idFile,socket):
        packedData=self._message._sendedMessageFileFromClient(unpackData,roomId,username,idFile)
        room.sendToGroup(packedData,socket)
    
    def _sendFileOfClintToClient(self,byte,size,filename,socket):
        packedData=self._message._sendedFileFromClient(byte,size,filename)
        self._sendone(packedData,socket)

    def _sendFileIdAndFileName(self,filename,room,sendFileTime,socket):
        packedData=self._message._sendFileName(self._fileCount,filename,sendFileTime)
        room.sendToGroup(packedData,socket)

    def _sendCantBeTwiceSameRoom(self,socket):
        packedData=self._message._cantBeInRoomTwice()
        self._sendone(packedData,socket)

    def _makeRoomsOrder(self,user):
        "create dictionary of rooms"
        rooms={}
        roomsOfUserId=user.getRoomsId()
        roomsId=self._roomlist.getRoomsId()
        for roomId in roomsId:
            if roomId not in roomsOfUserId:
                roomName=self._roomlist.getRoomNameById(roomId)
                rooms[roomId]=roomName
        self._log.saveToLog("create dictionary of rooms")
        return rooms
    
    def _convertRoomDictToString(self,rooms):
        "convert dict to str"
        stringRoom=""
        for id,value in rooms.items():
            stringRoom+=str(id)+"-"+str(value)+" "
        self._log.saveToLog("convert dictionary rooms to string")
        return stringRoom

    def _sendTimeFile(self,socket):
        "send the time of transfer file"
        packedData=self._message._finishTakeFile()
        room.sendToGroup(packedData,socket)
        
    def _readFile(self,filename):
        "read binari file"
        with open(self._dirFile+filename, "rb") as f:
            byte = f.read()
        self._log.saveToLog("Server Read File")
        return byte

    def _getSizeOfFile(self,unpackData):
        "get size of file"
        self._log.saveToLog("get size of file")
        return int(os.path.getsize(unpackData))
    

    def _writeFile(self,byte,filename,path):
        "write file to folder"
        absoluteFile=path + filename
        with open(absoluteFile, "wb") as f:
            byte = f.write(byte)
        self._log.saveToLog("Server Write File to 'server files'/'Files From Web' folder")

    def _appendFile(self,filename,size):
        "append file object to file list object"
        new_file= File.File(filename,size,self._fileCount,0)
        self._filesList.fileAdd(new_file)
        self._log.saveToLog("Server append file object to file list object")

    def _createFolder(self):
        "create folder for files"
        if os.path.isdir(self._dirFile)==False:#if the folder logs doesnt exist will create this folder
	    os.mkdir(self._dirFile)
	    self._log.saveToLog("Server create dir-server files")
        if os.path.isdir(self._dirFileWeb)==False:#if the folder logs doesnt exist will create this folder
            os.mkdir(self._dirFileWeb)
	    self._log.saveToLog("Server create dir-Files From Web")
	    
    def _createAdmins(self):
        "create txt file for admins"
        absoluteFile=self._dirFile + "Admin.txt"
	f=open(absoluteFile,"wb")
	f.close()
	self._log.saveToLog("Server Create Admins File")

    def _checkIfUserIsAdmin(self,roomId,username):
        "check if user in admins file"
        admins=self._readAdminsFile()
        admin=str(roomId)+":"+username#1:ido
        self._log.saveToLog("Server check if user is admin")
        return admin in admins

    def _deleteAdminFromFile(self,content,admins):
        "delete admin from txt admins file"
        admins=admins.strip("").split(",")
        absoluteFile=self._dirFile + "Admin.txt"
        f=open(absoluteFile,"wb")
        for admin in admins:
            if admin!=content and admin!="":
                f.write(admin+",")
                self._log.saveToLog("Server delete admin from Admins File")
                
    def _appendAdminToFile(self,room,username):
        "add admin to txt admins file"
        absoluteFile=self._dirFile + "Admin.txt"
        content=str(room.getId())+":"+username+","
        with open(absoluteFile,"a") as f:
            f.write(content)
        self._log.saveToLog("Server append admin to Admins File")

    def _readAdminsFile(self):
        "read binari txt file admins"
        absoluteFile=self._dirFile + "Admin.txt"
        with open(absoluteFile, "rb") as f:
            byte = f.read()
        self._log.saveToLog("Server Read Admins File")
        return byte

    def _deleteFromMuted(self,roomId,username):
        "remove user from muted"
        fullName=str(roomId)+":"+username
        if fullName in self._usersToMute:#if user in muted user and is only in the room or exit from chat
            self._usersToMute.remove(fullName)
            return True
        return False

    def _takeFirstUserAsAdmin(self,room,roomId):
        "take first user in user list of current room as admin"
        users=room.getUsers().getUsers()
        if len(users)>0:
            username=users[0].getUserName()
            isMuted=self._deleteFromMuted(roomId,username)
            result=self._checkIfUserIsAdmin(roomId,username)
            if result==False:
                self._appendAdminToFile(room,username)
                return username
            return ""
        return ""

    def _appendUserToMuted(self,roomId,username):
        "add user for muted"
        fullName=str(roomId)+":"+username
        if fullName not in self._usersToMute:
            self._usersToMute.append(fullName)
            self._log.saveToLog("Server append user to muted")
            return False
        return True

    def _checkExtension(self,filename):
        "check if file extension exist"
        mime_type = self._mime.guess_type(filename)#get type of file
        extension=mime_type[0]
        if extension==None:
            return None
        self._log.saveToLog("file extension is ok/exist")
        return "OK"  

    def _loop(self):
	"get data and response any time"
	while self._exit==False:
            if self._queue!=[]:#if the server get data
                self._mut.acquire() # yay mutex! this is a lock!
                socket,data=self._queue.pop()#socket is socket from rlist
                self._mut.release()#unlock
                id,unpackData,username,roomId,sizeFile,filename=self._message._unpackdata(data)
                print username
                if id!=1 and id!=33:
                    try:
                        print self._loggedUserList.getUsers()
                        print username
                        socket=self._loggedUserList.getSocketByUser(username)
                        print socket
                        user=self._loggedUserList.getUserBySocket(socket)#get user object
                        print user
                    except Exception,e:
                        self._log.saveToLog(str(e),"Error")
                if roomId!=0:
                    room=self._roomlist.getRoomById(roomId)
		    userInRoom=self._checkUserInRoom(room,user)
		    
		if id==33:#if user register
                    if self._blockChat==False:
                        password=unpackData
                        keyExist=self._database.isExist(username)#if user registerd
                        if keyExist==False:#if user send username + password with content
                            print password
                            print list(password)
                            print type(password)
                            print "UUUUUUUUUUUUUUUUUUUUU",username
                            if password=="":
                                packedData = self._message._errorMessage("You must enter password!")
                                self._sendone(packedData,socket)
                            elif username=="":
                                packedData = self._message._errorMessage("You must enter username!")
                                self._sendone(packedData,socket)
                            else:   
                                self._database.addValue(username,password)#add user to database 
                                packedData = self._message._SuccessRegister()
                                self._sendone(packedData,socket)
                                self._log.saveToLog("User regisered")
                        else:
                            packedData = self._message._errorMessage("You are already registerd!")
                            self._sendone(packedData,socket)
                    else:
                        packedData = self._message._errorMessage("The chat close now!")
                        self._sendone(packedData,socket)
                                            
		elif id==1:#login message from client
                    if self._blockChat==False:
                        password=unpackData
                        keyExist=self._database.isExist(username)
                        if keyExist==False:#if user not registered
                            packedData = self._message._errorMessage("You are not registerd!")
                            self._sendone(packedData,socket)

                        elif username in self._loggedUserList.getUsersName():
                            packedData = self._message._errorMessage("This user already loged in!")
                            self._sendone(packedData,socket)

                        else:
                                correctPassword=self._database.checkPassword(username,password)
                                if correctPassword==False:#if password wrong
                                    packedData = self._message._errorMessage("Wrong password!")
                                    self._sendone(packedData,socket)
                                else:#if everything ok
                                    self._appendUser(username,socket)
                                    packedData=self._message._SuccessLogin(username)
                                    self._sendone(packedData,socket)
                                    stringRoom=self._roomlist.getRoomString()
                                    self._sendRoomList(socket,stringRoom)
                                    self._log.saveToLog("add user to chat")
                    else:
                        packedData = self._message._errorMessage("The chat close now!")
                        self._sendone(packedData,socket)
                    
		elif id==2:#choose room message from client
                    if userInRoom==False:
                        room.userAdd(user)
                        userAdmin=self._takeFirstUserAsAdmin(room,roomId)
                        user.roomAdd(room)
                        self._sendOkayRoom(socket,roomId)
                        self._sendAdminsList("",roomId,room)
                        self._sendUserList("",roomId,room)
                        if userAdmin!="":
                            unpackData=userAdmin + " has become to admin automaticly"
                            self._sendMessageOfClintToClient(unpackData,roomId,room,"","")
                        self._log.saveToLog("add user to room")
                    else:
                        self._sendCantBeTwiceSameRoom(socket)
                        self._sendRoomList(socket,stringRoom)

		elif id==4:#exit room message from client
                    if userInRoom==True:
                        content=str(roomId)+":"+username
                        admins=self._readAdminsFile()
                        self._deleteAdminFromFile(content,admins)
                        room.deleteUserSocket(username)#delete user from room
                        user.roomLeave(room)#remove room id from user object.
                        userAdmin=self._takeFirstUserAsAdmin(room,roomId)                        
                        self._sendAdminsList("",roomId,room)
                        self._sendUserList("",roomId,room)
                        unpackData=username + " has left the room"
                        self._sendMessageOfClintToClient(unpackData,roomId,room,"",socket)
                        if userAdmin!="":
                            unpackData=userAdmin + " has become to admin"
                            self._sendMessageOfClintToClient(unpackData,roomId,room,"","")
                        self._log.saveToLog("user exit from room")
					
                elif id==13:#request room message from client
                    roomsUser=self._makeRoomsOrder(user)
                    stringRoom=self._convertRoomDictToString(roomsUser)
                    self._sendRoomList(socket,stringRoom)
                    self._log.saveToLog("send room list to user")
				
                elif id==14:#exit chat message from client
                    self._sendQunfirmQuit(user,socket)
                    self._loggedUserList.deleteUser(username)#delete from rooms
                    try:
                        self._open_sockets.remove(socket)#delete from server
                        self._allsock.remove(socket)
                        self._log.saveToLog("delete user socket from lists")
                    except Exception,e:
                        self._log.saveToLog(str(e),"Error")

                        
                    roomsOfUser=user.getRoom()
                    print "SSSSSSSSSSSSSSSSSSSSSSSSSSSSS",roomsOfUser
                    for room in roomsOfUser:
                        roomId=room.getId()
                        print room
                        print roomId
                        content=str(roomId)+":"+username
                        admins=self._readAdminsFile()
                        self._deleteAdminFromFile(content,admins)
                        room.deleteUserSocket(username)
                        self._deleteFromMuted(roomId,username)
                        userAdmin=self._takeFirstUserAsAdmin(room,roomId)
                        self._sendAdminsList("",roomId,room)
                        self._sendUserList("",roomId,room)
                        unpackData=username + " has left the chat"
                        self._sendMessageOfClintToClient(unpackData,roomId,room,"",socket)
                        if userAdmin!="":
                            unpackData=userAdmin + " has become to admin"
                            self._sendMessageOfClintToClient(unpackData,roomId,room,"","")
                        self._log.saveToLog("delete user socket from rooms")
                    self.close(socket)
                    self._log.saveToLog("user exit from chat")
                    
                elif id==18:
                    usernameAdmin=sizeFile
                    if usernameAdmin!=username:#if user not try about himself
                        isAdmin=self._checkIfUserIsAdmin(roomId,usernameAdmin)#if the user that do the action is admin
                        if isAdmin==True:
                            result=self._checkIfUserIsAdmin(roomId,username)#if try to kick out admin,cant kick out admins
                            if result==False:
                                packedData=self._message._adminGetOutUserToClient(username,roomId)
                                self._sendone(packedData,socket)
                            else:#if user is admin
                                socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                                unpackData=username + " is admin.cant kick out admin!"
                                self._sendMessageToOneClient(unpackData,roomId,"",socket)
                        else:#if user is not admin
                            socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                            unpackData="you are not admin!"
                            self._sendMessageToOneClient(unpackData,roomId,"",socket)
                    else:#if user try kick out himself
                        socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                        unpackData="you cant kick out your user!"
                        self._sendMessageToOneClient(unpackData,roomId,"",socket)

                elif id==19:
                    result=self._checkExtension(filename)
                    if result!=None:          
                        self._writeFile(unpackData,filename,self._dirFile)
                        end=datetime.datetime.now()#end timer
                        sendFileTime=(end-self._startSendFile).seconds#calculate second
                        self._appendFile(filename,sizeFile)
                        message="filename=" + str(filename)+"\nsize="+str(sizeFile/(1024*1024.0))+ "MB" +"\n"+username+" sent a file" 
                        self._sendFileIdAndFileName(filename,room,sendFileTime,"")
                        self._sendMessageFileOfClintToClient(message,roomId,room,username,self._fileCount,"")
                        self._fileCount+=1#id of file
                        self._log.saveToLog("server send client file message to other clients")

                elif id==22:
                    file=self._filesList.getFileById(unpackData)
                    filename=file.getFileName()
                    byte=self._readFile(filename)
                    size=file.getSize()
                    self._sendFileOfClintToClient(byte,size,filename,socket)
                    self._log.saveToLog("server send file")

                elif id==24:
                    sizeFile=sizeFile/(1024*1024.0)
                    if sizeFile>150.00:
                        pass
                        self._log.saveToLog("server send denied for file")
                    
                    else:
                        packedData=self._message._CanSendFile(roomId)
                        self._sendone(packedData,socket)
                        self._startSendFile=datetime.datetime.now()#start timer
                        self._log.saveToLog("server send accpet for file")

                elif id==29:
                    usernameAdmin=sizeFile
                    if usernameAdmin!=username:#if user not try about himself
                        isAdmin=self._checkIfUserIsAdmin(roomId,usernameAdmin)#if the user that do the action is admin
                        if isAdmin==True:
                            fullName=str(roomId)+":"+username
                            if fullName not in self._usersToMute:#if user in muted user,he cant become to admin
                                result=self._checkIfUserIsAdmin(roomId,username)#if the user that append to admins is not admin
                                if result==False:
                                    self._appendAdminToFile(room,username)
                                    self._sendAdminsList("",roomId,room)
                                    self._sendUserList("",roomId,room)
                                    unpackData=username + " has become to admin by " + usernameAdmin
                                    self._sendMessageOfClintToClient(unpackData,roomId,room,"","")
                                else:#if userToAdmin is admin
                                    socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                                    unpackData="This user is admin,cant add twice same admin!"
                                    self._sendMessageToOneClient(unpackData,roomId,"",socket)
                            else:#if user is muted
                                socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                                unpackData="This user muted,cant become to admin!"
                                self._sendMessageToOneClient(unpackData,roomId,"",socket)
                        else:#if user is not admin
                            socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                            unpackData="You are not admin!"
                            self._sendMessageToOneClient(unpackData,roomId,"",socket)
                    else:#if user try append as admin  himself
                        socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                        unpackData="You cant append your as admin!"
                        self._sendMessageToOneClient(unpackData,roomId,"",socket)

                
                elif id==30:
                    usernameAdmin=sizeFile
                    if usernameAdmin!=username:#if user not try about himself
                        isAdmin=self._checkIfUserIsAdmin(roomId,usernameAdmin)#if the user that do the action is admin
                        if isAdmin==True:
                            result=self._checkIfUserIsAdmin(roomId,username)#if try to mute admins,cant mute admins
                            if result==False:
                                isMuted=self._appendUserToMuted(roomId,username)
                                if isMuted==False:
                                    unpackData=username + " has become to muted by " + usernameAdmin
                                    self._sendMessageOfClintToClient(unpackData,roomId,room,"","")
                                else:#if user in muted
                                    socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                                    unpackData=username + " is muted.cant mute user twice!"
                                    self._sendMessageToOneClient(unpackData,roomId,"",socket)
                            else:#if user is admin
                                socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                                unpackData=username + " is admin.cant muted admin!"
                                self._sendMessageToOneClient(unpackData,roomId,"",socket)
                        else:#if user is not admin
                            socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                            unpackData="You are not admin!"
                            self._sendMessageToOneClient(unpackData,roomId,"",socket)
                    else:#if user try mute himself
                        socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                        unpackData="You cant mute your user!"
                        self._sendMessageToOneClient(unpackData,roomId,"",socket)

                elif id==31:
                    usernameAdmin=sizeFile
                    if usernameAdmin!=username:#if user not try about himself
                        isAdmin=self._checkIfUserIsAdmin(roomId,usernameAdmin)#if the user that do the action is admin
                        if isAdmin==True:
                            result=self._checkIfUserIsAdmin(roomId,username)#if try to mute admins,cant mute admins
                            if result==False:
                                isMuted=self._deleteFromMuted(roomId,username)
                                if isMuted==True:#if user is really was mute
                                    unpackData=username + " has become to unmuted by " + usernameAdmin
                                    self._sendMessageOfClintToClient(unpackData,roomId,room,"","")
                                else:#if user never be mute
                                    socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                                    unpackData=username + " is not mute!"
                                    self._sendMessageToOneClient(unpackData,roomId,"",socket)
                            else:#if user is admin
                                socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                                unpackData=username + " is admin.cant muted admin!"
                                self._sendMessageToOneClient(unpackData,roomId,"",socket)
                        else:#if user is not admin
                            socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                            unpackData="you are not admin!"
                            self._sendMessageToOneClient(unpackData,roomId,"",socket)
                    else:#if user try mute himself
                        socket=self._loggedUserList.getSocketByUser(usernameAdmin)
                        unpackData="you cant mute your user!"
                        self._sendMessageToOneClient(unpackData,roomId,"",socket)

                elif id==32:
                    usernameThatSend=sizeFile
                    if usernameThatSend!=username:#if user not try about himself
                        if unpackData!="":#if there is a message with content and not nothing
                            self._sendMessageToOneClient(unpackData+"(Private Message)",roomId,usernameThatSend,socket)
                        else:#if message is nothing/""
                            socket=self._loggedUserList.getSocketByUser(usernameThatSend)
                            unpackData="You cant send nothing in private message!"
                            self._sendMessageToOneClient(unpackData,roomId,"",socket)
                    else:#if user try mute himself
                        socket=self._loggedUserList.getSocketByUser(usernameThatSend)
                        unpackData="You cant send to your a private message!"
                        self._sendMessageToOneClient(unpackData,roomId,"",socket)
		else:
                    if userInRoom==True:
                        if "-filename=" not in unpackData and "size=" not in unpackData:
                            fullName=str(roomId)+":"+username#1:ido
                            if fullName not in self._usersToMute:
                                self._sendMessageOfClintToClient(unpackData,roomId,room,username,"")
                                self._log.saveToLog("server send user message")
			    else:
                                unpackData="You are muted!"
                                self._sendMessageToOneClient(unpackData,roomId,"",socket)
					
    def close(self,i):
	try:
            i.close()
            self._log.saveToLog("close server connection")
	except:
	    self._log.saveToLog("error closing socket!","Error")
