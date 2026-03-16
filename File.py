class File(object):
    def __init__(self,filename,size,id,time):
        self._filename=filename
        self._size=size
        self._id=id
        self._time=time

    def getFileName(self):
        return self._filename

    def getSize(self):
        return self._size

    def getId(self):
        return self._id

    def getTime(self):
        return self._time
