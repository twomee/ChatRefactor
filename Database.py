import os
import sys
import shelve

class Database(object):
    def __init__(self,name):
        "Create the database"
        self._path = os.path.abspath(os.path.dirname(sys.argv[0])) + "\\database\\"+name
        db = shelve.open(self._path)
        db.close()

    def getValue(self,username):
        "get password"
        db = shelve.open(self._path)
        value=db[username]
        db.close()
        return value

    def addValue(self,username,value):
        "add username"
        db = shelve.open(self._path)
        db[username]=value
        db.close()

    def checkPassword(self,username,password):
        "check if password is correct"
        db = shelve.open(self._path)
        if db[username]==password:
            isCorrect=True
        elif db[username]!=password:
            isCorrect=False
        db.close()
        return isCorrect
    
    def isExist(self,username):
        "check if user exist"
        db = shelve.open(self._path)
        keyExist=db.has_key(username)
        db.close()
        return keyExist

    def clearDatabase(self):
        "clear all the users which registered to the chat"
        db = shelve.open(self._path)
        db.clear()
        db.close()
