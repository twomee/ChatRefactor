import User
import Users

class Room(object):
	def __init__(self,roomName,id,log):
		"The constructor function, gets the name of the current room"
		self._id=id
		self._name=roomName
		self._users=Users.Users()
		self._openSockets=[]
		self._log=log
		
	def getUsers(self):
		"Returns a list of all persons present in the room"
		return self._users
	
        def getUsersString(self):
                "Return string of users in room"
                users=""
                for user in self._users.getUsers():
                        username=user.getUserName()
                        users+=username+","
                print "users==>",users
                return users
                        
	def getNameOfRoom(self):
		"Returns the name of the current room"
		return self._name
	
	def getId(self):
		return self._id
	
	def getOpenSockets(self):
		"return all the sockets in the room"
		return self._openSockets
	
	def deleteUserSocket(self,username):
		"delete socket and user from the room"
		for user in self._users.getUsers():
			print user
			if user.getUserName()==username:
                                self._users.deleteUser(username)
				self._openSockets.remove(user.getSocket())
				
	def userAdd(self,user):
		"add user to room dictionary"
		self._users.userAdd(user)
		self._openSockets.append(user.getSocket())
		
	def sendToGroup(self,packedData,socket):
		"send the packed data to all client"
		for i in self._openSockets:#send for all open socket in room 
			if i!=socket:
				self._send(packedData,i)
	
	def _send(self,packedData,i):
                "send the packed data to client"
		try:
                        i.sendall(packedData)
                        print('sent','data')
		except i.error,e:			
			self._log.saveToLog(str(e))
			i.close()
