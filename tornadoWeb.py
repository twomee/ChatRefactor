import tornado.ioloop
import tornado.web
import os
import sys
import Users
import Database
import hashlib

class indexHandler(tornado.web.RequestHandler):
    "display the idex.html"
    def initialize(self,server):
        self._server=server
    
    def get(self):
        try:
            name = self.request.uri
            confirm=self._server.getConfirm()
            if confirm==True:
                self.render("index.htm")
            else:
                self.render("simpleUser.html")
        except Exception,e:
            self.write("404: Not Found")
            
class RoomsHandler(tornado.web.RequestHandler):
    "display the rooms of chat"
    def initialize(self,rooms,server):
        self._rooms=rooms.getRoomString()
        self._rooms=self._rooms.split(" ")
        self._roomsDict={}
        self.orderRooms()
        self._server=server

    def orderRooms(self):
        for room in self._rooms:
            if list(room)!=[]:
                num=room.split("-")[0]
                name=room.split("-")[1]
                self._roomsDict[num]=name         

    def get(self):
        try:
            name = self.request.uri
            confirm=self._server.getConfirm()
            if confirm==True:
                self.render("rooms.html",rooms=self._roomsDict)
            else:
                self.render("simpleUser.html")
        except Exception,e:
            self.write("404: Not Found")
    
class UsersHandler(tornado.web.RequestHandler):
    "display the users are connected to chat"
    def initialize(self,users,server):
        self._users=users.getUsersName()
        self._server=server

    def get(self):
        try:
            name = self.request.uri
            confirm=self._server.getConfirm()
            if confirm==True:
                self.render("users.html",users=self._users)
            else:
                self.render("simpleUser.html")
        except Exception,e:
            self.write("404: Not Found")

class BlockHandler(tornado.web.RequestHandler):
    "close the chat"
    def initialize(self,server):
        self._server=server
        
    def get(self):
        try:
            name = self.request.uri
            confirm=self._server.getConfirm()
            if confirm==True:
                self.render("block.html")
                self._server.blockChat(True)
            else:
                self.render("simpleUser.html")         
        except Exception,e:
            pass

class EnableHandler(tornado.web.RequestHandler):
    "disable the close of the chat"
    def initialize(self,server):
        self._server=server
        
    def get(self):
        try:
            name = self.request.uri
            confirm=self._server.getConfirm()
            if confirm==True:
                self.render("enable.html")
                self._server.blockChat(False)
            else:
                self.render("simpleUser.html")      
        except Exception,e:
            pass

class manageChatHandler(tornado.web.RequestHandler):
    "show page with two button,one to 'block chat' and another to 'enable caht'"
    def initialize(self,server):
        self._server=server
    
    def get(self):
        try:
            name = self.request.uri
            confirm=self._server.getConfirm()
            if confirm==True:
                self.render("manageChat.html")
            else:
                self.render("simpleUser.html")   
        except Exception,e:
            pass

class manageDBHandler(tornado.web.RequestHandler):
    "show page with button to 'reset Database'"
    def initialize(self,server):
        self._server=server
        
    def get(self):
        try:
            name = self.request.uri
            confirm=self._server.getConfirm()
            if confirm==True:
                self.render("manageDB.html")
            else:
                self.render("simpleUser.html")         
        except Exception,e:
            pass
        
class resetDBHandler(tornado.web.RequestHandler):
    "reset the database of the chat"
    def initialize(self,server):
        self._server=server
    
    def get(self):
        try:
            name = self.request.uri
            confirm=self._server.getConfirm()
            if confirm==True:
                self.render("reset.html")
                self._server.resetDatabase()
            else:
                self.render("simpleUser.html")  
        except Exception,e:
            pass

class manageAdminHandler(tornado.web.RequestHandler):
    "show page with list of users name and beside them buttons to change user to become admin in all the rooms"
    def initialize(self,users,server):
        self._users=users.getUsersName()
        self._server=server

    def get(self):
        try:
            name = self.request.uri
            confirm=self._server.getConfirm()
            if confirm==True:
                name = self.get_argument('name', True)
                self.render("manageAdmins.html",users=self._users)
            else:
                self.render("simpleUser.html") 

        except Exception,e:
            pass

class adminHandler(tornado.web.RequestHandler):
    "change user to become admin in all the rooms"
    def initialize(self,server):
        self._server=server
    
    def get(self):
        try:
            name = self.get_argument('name', True)
            confirm=self._server.getConfirm()
            if confirm==True:
                self.render("admin.html")
                self._server.manageAdmin(name)
            else:
                self.render("simpleUser.html") 
        except Exception,e:
            pass

class filesHandler(tornado.web.RequestHandler):
    "show page with files name list and beside them button to download file"
    def initialize(self,files,server):
        self._files=files.getFilesName()
        self._server=server
        
    def get(self):
        try:
            name = self.get_argument('name', True)
            confirm=self._server.getConfirm()
            if confirm==True:
                self.render("files.html",files=self._files)
                if name=="openFolder":
                    self._server.openBrowser()
            else:
                self.render("simpleUser.html")
        except Exception,e:
            self.write("404: Not Found")
            
class downloadFileHandler(tornado.web.RequestHandler):
    "download file"
    def initialize(self,server):
        self._server=server
    
    def get(self):
        try:
            name = self.get_argument('name', True)
            confirm=self._server.getConfirm()
            if confirm==True:
                self._server.downloadFileFromWeb(name)
                self.render("downloadFile.html")
            else:
                self.render("simpleUser.html") 
        except Exception,e:
            pass
        
class simpleUserHandler(tornado.web.RequestHandler):
    "page which appear when users without access to the website try get into the website"
    def initialize(self,server):
        self._server=server
    
    def get(self):
        try:
            name = self.get_argument('name', True)
            confirm=self._server.getConfirm()
            if confirm==True:
                self._server.notConfirmGoToWeb()
                self.render("simpleUser.html")
            else:
                self.render("simpleUser.html") 
        except Exception,e:
            pass

class loginHandler(tornado.web.RequestHandler):
    "show page with login system,if the admin loged in,he get access to the website"
    def initialize(self,server,db,salt):
        self._server=server
        self._db=db
        self._salt=salt

    def checkDetails(self,name,password):
        exist=self._db.isExist(name)
        print exist
        if exist==True:
            correctPassword=self._db.checkPassword(name,password)
            if correctPassword==True:
                return True
            return False
        return False

    def hashPassword(self,password):
        hashed_password = hashlib.sha512(password + self._salt).digest()
        return hashed_password
    
    def post(self):
        try:
            goToWeb=self._server.getConfirm()
            if goToWeb==False:#if the server not confirm to go to the web
                self.render("login.html")
            name = self.get_argument("name", '')
            password = self.get_argument("pass", '')
            name=str(name)
            password=str(password)
            hashedPassword = self.hashPassword(password)
            confirm=self.checkDetails(name,hashedPassword)#check if user and password correct
            if confirm==True:#if yes
                self._server.confirmGoToWeb()#the server get accept to open the web to this user
            if goToWeb==True:#if server has accept to user to be in the web
                self.render("index.htm")
        except Exception,e:
            pass
    get = post

class addRoomHandler(tornado.web.RequestHandler):
    "show page with text input of room name.admnin can add room to the chat with any name he want"
    def initialize(self,server):
        self._server=server
        
    def get(self):
        try:
            confirm=self._server.getConfirm()
            if confirm==True:
                self.render("addRoom.html")
            else:
                self.render("simpleUser.html")
        except Exception,e:
            pass

class roomHandler(tornado.web.RequestHandler):
    "add room the the chat"
    def initialize(self,server):
        self._server=server
    
    def get(self):
        try:
            confirm=self._server.getConfirm()
            if confirm==True:
                name = self.get_argument('name', '')
                name=str(name)
                self._server.addRoom(name)
                self.render("room.html")
            else:
                self.render("simpleUser.html")      
        except Exception,e:
            pass
