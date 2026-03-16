import File

class Files(object):
    def __init__(self):
        self._files={}

    def fileAdd(self,file):
	self._files[file.getId()]=file
    
    def getFileById(self,id):
        for idFile,file in self._files.items():
            if id==idFile:
                return file

    def getTimeById(self,id):
        for idFile,file in self._files.items():
            if id==idFile:
                return file.getTime()

    def getFilesName(self):
        files=[]
        for id,fileObject in self._files.items():
            name=fileObject.getFileName()
            files.append(name)
        return files
