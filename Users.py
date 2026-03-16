import User

class Users(object):
	def __init__(self):
		"The constructor of the class, gets User name"
		self._users=[]
		
	def userAdd(self,user):
		"Adding a user creates a user list the name and the address of its socket"
		self._users.append(user)
		
	def getSocketByUser(self,username):
		"get the socket of current user"
		for user in self._users:
			if user.getUserName()==username:
				return user.getSocket()
		
	def deleteUser(self,username):
		"delete user from chat"
		for user in self._users:
			if user.getUserName()==username:
				self._users.remove(user)
	
	def getUserBySocket(self,socket):
		"get user object ny his socket"
		for user in self._users:
			if socket==user.getSocket():
				return user
			
	def getUsers(self):
		"Returns the user name"
		return self._users

	def getUsersName(self):
		"Returns the user name"
		names=[]
		for user in self._users:
			names.append(user.getUserName())
		return names
	
	
