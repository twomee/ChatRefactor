import Room


class Rooms(object):
	
	
	def __init__(self):
		self._rooms={}
		
	def roomAdd(self,room):
                "add room to list rooms"
		self._rooms[room.getId()]=room
	
	def getRoomById(self,id):
                "return room by his number"
		return self._rooms[id]

	def getRoomNameById(self,id):
                "return room name by his number"
		return self._rooms[id].getNameOfRoom()
	
        def getRoomString(self):
                "Return string of rooms"
                rooms=""
                for id,room in self._rooms.items():#convert the dictionary to string message
                        name=room.getNameOfRoom()
                        rooms=rooms+str(id)+"-"+str(name)+" "
                return rooms
        
        def getRoomsId(self):
                "get list of rooms number"
                roomsId=[]
                for id,room in self._rooms.items():#convert the dictionary to string message
                        roomsId.append(id)
                return roomsId
