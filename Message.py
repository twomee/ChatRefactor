import struct
import log


class Message(object):
	
	MSG_NO = [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34]
	ID_WITH_LEN=[3,5,7,9,10,11,15,16,17,19,20,21,23,28,32]
	MSG_CONNECT_ERROR="This user not exist!"
	LEN_CONNECT_ERROR=len(MSG_CONNECT_ERROR)
	MSG_LOGIN="Login..."
	MSG_REGISTER="register sucssed!"
	LEN_LOGIN=len(MSG_LOGIN)
	MSG_OKAY_ROOM="The Room is okay!"
	LEN_OKAY_ROOM=len(MSG_OKAY_ROOM)
	MSG_OKAY_QUIT="quit"
	MSG_CANT_SEND_FILE="NO"
	MSG_SEND_FILE="YES"
	LEN_CANT_SEND_FILE=len(MSG_CANT_SEND_FILE)
	msgLen={1:25,2:18,3:23,4:19,5:5,6:29,7:5,8:27,9:21,10:5,11:23,12:19,13:17,14:19,15:7,16:5,17:5,18:35,19:129,20:111,21:1104,22:21,23:27,24:119,25:1000,26:5,27:1,28:7,29:35,30:35,31:35,32:39,33:25,34:18}
	def __init__(self,log):
		"The constructor of the class, do not get anything"
		self._log=log
		
	#SERVER MESSAGES
	def _errorMessage(self,data):
		"error login binari message"
		length=len(data)
		packedData=struct.pack("=BI"+str(length)+"s",self.MSG_NO[4],length,data)
		return packedData

        def _SuccessRegister(self):
                "success register binari message"
		packedData=struct.pack("=B17s",self.MSG_NO[33],self.MSG_REGISTER)
		return packedData
	
	def _SuccessLogin(self,username):
		"Success login binari message"
		packedData=struct.pack("=B16s12s",self.MSG_NO[5],username,self.MSG_LOGIN)
		return packedData
		
	def _roomList(self,rooms):
		"room List binari message"
		length=len(rooms)
		packedData=struct.pack("=BI"+str(length)+"s",self.MSG_NO[6],length,rooms)
		return packedData

	def _okayRoom(self,roomId):
		"Confirm Room binari message"
		packedData=struct.pack("=BH24s",self.MSG_NO[7],roomId,self.MSG_OKAY_ROOM)
		return packedData
	
	def _userList(self,users,roomId):
		"user list binari message"
		length=len(users)
		packedData=struct.pack("=BIH"+str(length)+"s",self.MSG_NO[14],length,int(roomId),users)
		return packedData

        def _adminList(self,admins,roomId):
                "admin list binari message"
		length=len(admins)
		packedData=struct.pack("=BIH"+str(length)+"s",self.MSG_NO[27],length,int(roomId),admins)
		return packedData

	def _roomsOfUser(self,rooms):
                "room of user binari message"
                length=len(rooms)
		packedData=struct.pack("=BI"+str(length)+"s",self.MSG_NO[15],length,rooms)
		return packedData

	def _quitConfirm(self,roomsOfUser):
                "server confirm quit of client binari message"
                length=len(roomsOfUser)
                packedData=struct.pack("=BI"+str(length)+"s",self.MSG_NO[16],length,roomsOfUser)
		return packedData
	
	def _getNewMessage(self,unpackData,username):
		"get client message binari message"
		length=len(unpackData)
		packedData=struct.pack("=BI16s"+str(length)+"s",self.MSG_NO[8],length,str(username),unpackData)
		return packedData
		
	def _updateRoomStatus(self):
		"updateRoomStatus binari message"
		unpackData="The room is okay!"
		length=len(unpackData)
		packedData=struct.pack("=BI"+str(length)+"s",self.MSG_NO[9],length,unpackData)
		return packedData
			
        def _adminGetOutUserToClient(self,username,roomId):
                "send get out user from admin"
		packedData=struct.pack("=BH16s",self.MSG_NO[11],roomId,username)
		return packedData
	
	def _sendedMessageFromClient(self,unpackData,roomId,username):
		"send message of client to other clients binari message"
		unpackData=str(unpackData)
		length=len(unpackData)
		packedData=struct.pack("=BI16sH"+str(length)+"s",self.MSG_NO[10],length,str(username),int(roomId),unpackData)
		return packedData

	def _sendedFileFromClient(self,byte,size,filename):
                "send file from server to client"
                filenameLength=len(filename)
                packedData=struct.pack("=B10s100s"+str(size)+"s"+str(filenameLength)+"s",self.MSG_NO[19],str(size),str(filenameLength),byte,filename)
		return packedData

        def _sendedMessageFileFromClient(self,unpackData,roomId,username,fileId):
                "send message of sended file to client"
		unpackData=str(unpackData)
		length=len(unpackData)
		packedData=struct.pack("=BI16sHI"+str(length)+"s",self.MSG_NO[22],length,str(username),int(roomId),int(fileId),unpackData)
		return packedData
        
        def _sendFileName(self,idFile,filename,time):
                "server send filename and his id to client"
                length=len(filename)
                packedData=struct.pack("=B100sI999s"+str(length)+"s",self.MSG_NO[20],str(length),int(idFile),str(time),str(filename))
                return packedData
        
        def _CanSendFile(self,roomId):
                "server confirm that file not over 150mb"
		packedData=struct.pack("=BH2s",self.MSG_NO[25],roomId,self.MSG_SEND_FILE)
		return packedData

	def _sendTimeOfSendedFile(self,time):
                "send the time transfer of a file"
		packedData=struct.pack("=B999s",self.MSG_NO[24],time)
		return packedData

        def _cantBeInRoomTwice(self):
                "server send message that user cant be in two same room"
                packedData=struct.pack("=B",self.MSG_NO[26])
                return packedData
        
	#CLIENT MESSAGES
	def _login(self,username,password):
		"login binari message"
		packedData= struct.pack("=B8s16s",self.MSG_NO[0],str(password),str(username))
		return packedData

	def _register(self,username,password):
                "register binari message"
                packedData= struct.pack("=B8s16s",self.MSG_NO[32],str(password),str(username))
                return packedData
		
	def _chooseRoom(self,username,roomName):
		"choose Room binari message"
		packedData=struct.pack("=BB16s",self.MSG_NO[1],int(roomName),str(username))
		return packedData
		
	def _sendedMessage(self,input,roomId,username):
		"sended Message binari message"
		length=len(str(input))
		packedData=struct.pack("=BI16sH"+str(length)+"s",self.MSG_NO[2],length,str(username),int(roomId),input)
		return packedData
	
        def _sendedFileMessage(self,byte,size,filename,roomId,username):
                "send file content"
                filenameLength=len(filename)
                print "!!!!!!!!!!!!!!!!!!!!!!",filename
                print "{{{{{{{{{{{{{{{{{{{{{{",size
                print "}}}}}}}}}}}}}}}}}}}}}}",filenameLength
                packedData=struct.pack("=B10s100s16sH"+str(size)+"s"+str(filenameLength)+"s",self.MSG_NO[18],str(size),str(filenameLength),username,int(roomId),byte,filename)
		return packedData

        def _sendSizeFile(self,username,size,roomId):
                "send size file"
		packedData=struct.pack("=B100s16sH",self.MSG_NO[23],str(size),username,roomId)
		return packedData
        
        def _sendRequestFile(self,idFile,username):
                "send request for specific file"
		packedData=struct.pack("=BI16s",self.MSG_NO[21],idFile,username)
		return packedData
	
        def _adminGetOutUserToServer(self,username,usernameOut,roomId):
                "send get out user from admin"
		packedData=struct.pack("=BH16s16s",self.MSG_NO[17],roomId,username,usernameOut)
		return packedData
	
        def _adminAppendUserToAdmins(self,username,usernameToAdmin,roomId):
                "send append user to admins file from admin"
		packedData=struct.pack("=BH16s16s",self.MSG_NO[28],roomId,username,usernameToAdmin)
		return packedData

	def _adminMuteUser(self,username,usernameToMute,roomId):
                "send user mute from admin"
		packedData=struct.pack("=BH16s16s",self.MSG_NO[29],roomId,username,usernameToMute)
		return packedData

	def _adminUnMuteUser(self,username,usernameToUnMute,roomId):
                "send user unmute from admin"
		packedData=struct.pack("=BH16s16s",self.MSG_NO[30],roomId,username,usernameToUnMute)
		return packedData

	def _userPrivateMessage(self,username,usernameToSend,roomId,message):
                "send private message from one user to another"
                length=len(message)
		packedData=struct.pack("=BIH16s16s"+str(length)+"s",self.MSG_NO[31],length,roomId,username,usernameToSend,message)
		return packedData
	
	def _exitChat(self,username,roomId):
		"exit Chat binari message"
		packedData=struct.pack("=B16sH",self.MSG_NO[3],str(username),int(roomId))
		return packedData
	
	def _requestRoomList(self,username):
		"client request room list"
		packedData=struct.pack("=B16s",self.MSG_NO[12],username)
		return packedData
	
	def _exitFromServer(self,username,roomId):
		"client exit from server"
		packedData=struct.pack("=B16sH",self.MSG_NO[13],username,int(roomId))
		return packedData
	
	def _unpackdata(self,data):
		"take the data(message)of the packed data of client"
		id= list(struct.unpack_from("B",data))[0]#take id of data
		try:

                        #register response
                        if id==self.MSG_NO[32]:#if id==33
                                id,password,username=struct.unpack_from("=B8s16s",data)
                                username=username.split("\x00")[0]
                                password=password.strip("\x00")
                                print "register response\n"
                                print "id=",id
                                print "username=",username
                                print "password=",password + "\n\r"
                                return id,password,username,0,0,""
                        
                        #login response
                        if id==self.MSG_NO[0]:#if id==1
                                id,password,username=struct.unpack_from("=B8s16s",data)
                                username=username.split("\x00")[0]
                                password=password.strip("\x00")
                                print "login response\n"
                                print "id=",id
                                print "username=",username
                                print "password=",password + "\n\r"
                                return id,password,username,0,0,""
                                
                        #choosen room
                        elif id==self.MSG_NO[1]:#if id==2
                                id,roomId,username=struct.unpack_from("=BB16s",data)
                                username=username.split("\x00")[0]
                                print "choosen room\n"
                                print "id=",id
                                print "data=",roomId
                                return id,"",username,roomId,0,""
                                
                        #sended message
                        elif id==self.MSG_NO[2]:#if id==3
                                id,length,username,roomId=struct.unpack_from("=BI16sH",data)
                                length=str(length)
                                unpackData=struct.unpack_from("=BI16sH"+length+"s",data)[4]
                                username=username.split("\x00")[0]
                                print "sended message\n"
                                print "id=",id
                                print username+":"+str(unpackData)
                                return id,unpackData,username,roomId,0,""
                                
                        #exit chat	
                        elif id==self.MSG_NO[3]:#if id==4
                                id,username,roomId=struct.unpack_from("=B16sH",data)
                                username=username.split("\x00")[0]
                                print "exit chat\n"
                                print "id=",id
                                print username+":"+str(roomId)
                                return id,"",username,roomId,0,""
                        
                        #request room list 
                        elif id==self.MSG_NO[12]:#if id==13
                                id,username=struct.unpack_from("=B16s",data)
                                username=username.split("\x00")[0]
                                print "id=",id
                                return id,"",username,0,0,""
                                
                                
                        #quit from server
                        elif id==self.MSG_NO[13]:#if id==14
                                id,username,roomId=struct.unpack_from("=B16sH",data)
                                username=username.split("\x00")[0]
                                print "id=",id
                                return id,"",username,roomId,0,""
                        
                        #error message
                        elif id==self.MSG_NO[4]:#if id==5
                                id,length=struct.unpack_from("=BI",data)
                                unpackedData=struct.unpack("=BI"+ str(length)+"s",data)[2]
                                print "error message:\n"
                                print "id=",id
                                print "data=",unpackedData
                                return id,unpackedData,"",0,0

                        #succses register
                        elif id==self.MSG_NO[33]:#if id==34
                                id,unpackedData=struct.unpack_from("=B17s",data)
                                print "sucsses register message:\n"
                                print "id=",id
                                print "data=",unpackedData
                                return id,unpackedData,"",0,0
                        
                        #login message
                        elif id==self.MSG_NO[5]:#if id==6
                                id,username,unpackedData=struct.unpack_from("=B16s12s",data)
                                username=username.split("\x00")[0]
                                print "login message:\n"
                                print "id=",id
                                print "data=",unpackedData
                                print "Y"
                                return id,unpackedData,username,0,0
                                
                        #room list
                        elif id==self.MSG_NO[6]:#if id==7
                                id,length=struct.unpack_from("=BI",data)
                                length=str(length)
                                unpackedData=struct.unpack("=BI"+ length+"s",data)[2]
                                print "room list:\n"
                                print "id=",id
                                print "data=","1"+unpackedData
                                return id,unpackedData,"",0,0


                        #confirm room
                        elif id==self.MSG_NO[7]:#if id==8
                                id,roomId,unpackedData=struct.unpack_from("=BH24s",data)
                                print "confirm room\n"
                                print "id=",id
                                print "data=",unpackedData
                                return id,unpackedData,"",roomId,0

                        #user list
                        elif id==self.MSG_NO[14]:#if id==15
                                id,length,roomId=struct.unpack_from("=BIH",data)
                                unpackedData=struct.unpack_from("=BIH"+str(length)+"s",data)[3]
                                print "user list\n"
                                print "id=",id
                                print "data=",unpackedData
                                return id,unpackedData,"",roomId,0

                        #confirm quit of client
                        elif id==self.MSG_NO[16]:#if id==17
                                id,length=struct.unpack_from("=BI",data)
                                unpackedData=struct.unpack_from("=BI"+str(length)+"s",data)[2]
                                print "user list\n"
                                print "id=",id
                                print "data=",unpackedData
                                return id,unpackedData,"",0,0

                        #admin get out user - server
                        elif id==self.MSG_NO[17]:#if id==18
                                id,roomId,username,usernameOut=struct.unpack_from("=BH16s16s",data)
                                username=username.split("\x00")[0]
                                usernameOut=usernameOut.split("\x00")[0]
                                print "admin get out user\n"
                                print "id=",id
                                print "data=",username
                                return id,"",usernameOut,roomId,username,""

                        #admin get out user - client
                        elif id==self.MSG_NO[11]:#if id==12
                                id,roomId,username=struct.unpack_from("=BH16s",data)
                                username=username.split("\x00")[0]
                                print "admin get out user\n"
                                print "id=",id
                                print "data=",username
                                return id,"",username,roomId,0

                        #client send file
                        elif id==self.MSG_NO[18]:#if id==19
                                id,length,filenameLength,username,roomId=struct.unpack_from("=B10s100s16sH",data)
                                length=self.fixLength(length)
                                filenameLength=self.fixLength(filenameLength)
                                unpackedData=struct.unpack_from("=B10s100s16sH"+str(length)+"s"+str(filenameLength)+"s",data)[5]
                                filename=struct.unpack_from("=B10s100s16sH"+str(length)+"s"+str(filenameLength)+"s",data)[6]
                                username=username.split("\x00")[0]
                                print "client send file\n"
                                print "id=",id
                                return id,str(unpackedData),username,roomId,int(length),filename

                        elif id==self.MSG_NO[19]:#if id==20
                                id,length,filenameLength=struct.unpack_from("=B10s100s",data)
                                length=self.fixLength(length)
                                filenameLength=self.fixLength(filenameLength)
                                unpackedData=struct.unpack_from("=B10s100s"+str(length)+"s"+str(filenameLength)+"s",data)[3]
                                filename=struct.unpack_from("=B10s100s"+str(length)+"s"+str(filenameLength)+"s",data)[4]
                                print "server send file\n"
                                print "id=",id
                                return id,unpackedData,filename,0,0

                        #server send filename and id of him to client
                        elif id==self.MSG_NO[20]:#if id==21
                                id,length,idFile,time=struct.unpack_from("=B100sI999s",data)
                                length=self.fixLength(length)
                                time=self.fixLength(time)
                                unpackedData=struct.unpack_from("=B100sI"+str(length)+"s",data)[3]
                                print "111111111111111111111111111111111111111-TIME",list(str(time))
                                print "server send filename and his id\n"
                                print "id=",id
                                print "time=",time
                                print "data=",unpackedData
                                return id,unpackedData,"",time,idFile

                        #client request file by id
                        elif id==self.MSG_NO[21]:#if id==22
                                id,idFile,username=struct.unpack_from("=BI16s",data)
                                username=username.split("\x00")[0]
                                print "client send id of file(request file)\n"
                                print "id=",id
                                print "idFile=",idFile
                                return id,idFile,username,0,0,""
                        
                        #new message
                        elif id==self.MSG_NO[8]:#if id==9
                                id,length,username=struct.unpack_from("=BI16s",data)
                                length=str(length)
                                unpackedData=struct.unpack_from("=BI16s"+length+"s",data)[3]
                                username=username.split("\x00")[0]
                                print "new message\n"
                                print "id=",id
                                print "data=",unpackedData
                                return id,unpackedData,username,0,0
                        


                        #update room status
                        elif id==self.MSG_NO[9]:#if id==10
                                id,length=struct.unpack_from("=BI",data)
                                length=str(length)
                                unpackedData=struct.unpack_from("=BI"+length+"s",data)[2]
                                print "update room status\n"
                                print "id=",id
                                print "data=",unpackedData
                                return id,unpackedData,"",0,0
                        
                        #room list of user 
                        elif id==self.MSG_NO[15]:#if id==16
                                id,length=struct.unpack_from("=BI",data)
                                length=str(length)
                                unpackedData=struct.unpack_from("=BI"+length+"s",data)[2]
                                print "update room status\n"
                                print "id=",id
                                print "data=",unpackedData
                                return id,unpackedData,"",0,0
                        
                        #server message file that client send
                        elif id==self.MSG_NO[22]:#if id==23
                                id,length,username,roomId,fileId=struct.unpack_from("=BI16sHI",data)
                                length=str(length)
                                unpackedData=struct.unpack_from("=BI16sHI"+length+"s",data)[5]
                                unpackedData=str(unpackedData)
                                username=username.split("\x00")[0]
                                print "server message file that client send\n"
                                print "id=",id
                                print username+":"+unpackedData
                                return id,unpackedData,username,roomId,fileId

                        #client send file size to check 
                        elif id==self.MSG_NO[23]:#if id==24
                                id,size,username,roomId=struct.unpack_from("=B100s16sH",data)
                                size=self.fixLength(size)
                                username=username.split("\x00")[0]
                                print "client send file size\n"
                                print "id=",id
                                return id,"",username,roomId,size,""
                        
                        #server message that client send
                        elif id==self.MSG_NO[10]:#if id==11
                                id,length,username,roomId=struct.unpack_from("=BI16sH",data)
                                length=str(length)
                                unpackedData=struct.unpack_from("=BI16sH"+length+"s",data)[4]
                                unpackedData=str(unpackedData)
                                username=username.split("\x00")[0]
                                print "server message that client send\n"
                                print "id=",id
                                print username+":"+unpackedData
                                return id,unpackedData,username,roomId,0
                        
                        #Can send file
                        elif id==self.MSG_NO[25]:#if id==26
                                id,roomId,unpackedData=struct.unpack_from("=BH2s",data)
                                print "id=",id
                                print unpackedData
                                return id,unpackedData,"",roomId,0

                        #cant be in the same room twice
                        elif id==self.MSG_NO[26]:#if id==27
                                id=list(struct.unpack_from("=B",data))[0]
                                print "id=",id
                                return id,"","",0,0
                        
                        #admins list
                        elif id==self.MSG_NO[27]:#if id==28
                                id,length,roomId=struct.unpack_from("=BIH",data)
                                unpackedData=struct.unpack_from("=BIH"+str(length)+"s",data)[3]
                                print "admin list\n"
                                print "id=",id
                                print "data=",unpackedData
                                return id,unpackedData,"",roomId,0

                        #admin appende user to admins
                        elif id==self.MSG_NO[28]:#if id==29
                                id,roomId,username,usernameToAdmin=struct.unpack_from("=BH16s16s",data)
                                username=username.split("\x00")[0]
                                usernameToAdmin=usernameToAdmin.split("\x00")[0]
                                print "admin append user to admin\n"
                                print "id=",id
                                print "data=",username
                                return id,"",usernameToAdmin,roomId,username,""

                        #admin mute user
                        elif id==self.MSG_NO[29]:#if id==30
                                print "&&&&&&&&&&&&&&&&&&&&&"
                                id,roomId,username,usernameToMute=struct.unpack_from("=BH16s16s",data)
                                username=username.split("\x00")[0]
                                usernameToMute=usernameToMute.split("\x00")[0]
                                print "admin mute user\n"
                                print "id=",id
                                print "data=",username
                                return id,"",usernameToMute,roomId,username,""

                        #admin unmute user
                        elif id==self.MSG_NO[30]:#if id==31
                                id,roomId,username,usernameToUnMute=struct.unpack_from("=BH16s16s",data)
                                username=username.split("\x00")[0]
                                usernameToUnMute=usernameToUnMute.split("\x00")[0]
                                print "admin unmute user\n"
                                print "id=",id
                                print "data=",username
                                return id,"",usernameToUnMute,roomId,username,""

			#user send private message to user
                        elif id==self.MSG_NO[31]:#if id==32
                                print "!@@!@!@!@!@!@!@!@!@!@!@!@!@!@!@!@!"
                                id,length,roomId,username,usernameToSend=struct.unpack_from("=BIH16s16s",data)
                                message=struct.unpack_from("=BIH16s16s"+str(length)+"s",data)[5]
                                username=username.split("\x00")[0]
                                usernameToSend=usernameToSend.split("\x00")[0]
                                print "user send private message\n"
                                print "id=",id
                                print "data=",message
                                return id,message,usernameToSend,roomId,username,""
                        
		except struct.error,e:
			self._log.saveToLog(str(e))
			
        def fixLength(self,length):
                "delete all \x00 from length string"
                length=str(length).strip("\x00")#remove all \x00
                length=int(length)#length must be int
                return length
        
	def _checkLenOfMessageById(self,data):
                try:
                        id = list(struct.unpack_from("B",data[:1]))[0]
                        if id in self.ID_WITH_LEN:
                                if id==self.MSG_NO[18] or id==self.MSG_NO[19]:#id==19 or id==20
                                        if len(data)==5:#if the 5 byte no enough
                                                return "more 111 bytes"#return response to more 96 byte for message length
                                        id,length,filenameLength =struct.unpack_from("=B10s100s",data)
                                        length=self.fixLength(length)
                                        filenameLength=self.fixLength(filenameLength)
                                        msglen=self.msgLen[id] + length + filenameLength
                                        print "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!",msglen
                                        print "(((((((((((((((((((((((((((((((((",length
                                        print ")))))))))))))))))))))))))))))))))", filenameLength
                                        return msglen
                                elif id==self.MSG_NO[20]:#id==21
                                        if len(data)==5:#if the 5 byte no enough
                                                return "more 101 bytes"#return response to more 6 byte for message length
                                        id,length =struct.unpack_from("=B100s",data)

                                else:
                                        id,length =struct.unpack_from("=BI",data)

                                length=self.fixLength(length)
                                
                                msglen=self.msgLen[id] + length
                        else:
                                msglen=self.msgLen[id]
                        return msglen
                except Exception,e:
                        self._log.saveToLog(str(e))
                        return ""
