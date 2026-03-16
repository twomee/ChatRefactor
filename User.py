class User(object):
	def __init__(self,username,socket):
		self._username=username
		self._socket=socket
		self._names=[]
		
	def roomAdd(self,room):
		"add user to room"
		self._names.append(room)
		
	def getUserName(self):
		return self._username
		
	def getSocket(self):
		return self._socket
	
	def getRoom(self):
		"return the room that user belong"
		return self._names

	def getRoomsId(self):
                "return list of rooms number"
                roomsId=[]
                for room in self._names:
                        id=room.getId()
                        roomsId.append(id)
		return roomsId

        def getRoomString(self):
                "Return string of rooms of user"
                rooms=""
                for room in self._names:
                        id=room.getId()
                        rooms+=str(id)+","
                return rooms
		
	def roomLeave(self,room):
		"delete user from room"
		self._names.remove(room)
