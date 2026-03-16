import time
import os
import sys

class logger(object):
	DIRECTOR="D:\\Chat-Project\\logs\\"
	END=".txt"
	def __init__(self,verbose):
		"The constructor of the class, get verbose parameter determines whether the module also prints a message screen and not just a file."
		try:
			self._makedir()
			self._verbose=verbose
			self._date=""
			self._director = os.path.abspath(os.path.dirname(sys.argv[0])) + "\\logs\\"# script director
			self._filename=self._director + "logs"  + logger.END#the path of the file + his name
			self._createFile()
		except Exception,e:
			print "logger does not work - " + str(e)
			
	def _makedir(self):
		"Create a folder logs"
		if os.path.isdir("logs")==False:#if the folder logs doesnt exist will create this folder
			os.mkdir("logs")
	
	def _createFile(self):
		"Create log files"
		if os.path.isfile(self._filename)==False:#if the name of this file doesnt exist will create file with this name
			f=open(self._filename,"w")
			f.close()
	
	def saveToLog(self,text,mode="NORMAL"):
		"Receive a message (string) to document log. mode is a string that describes the type of message (default is normal, if you want to write error 'ERROR')"
		self._date=time.strftime("%c").replace(":","-").replace("/","-")#date of the error
		if self._verbose==True:
			print  mode + " " +self._date + " " +  text
		with open(self._filename,"a") as f:
			f.write(mode + "-" + self._date + "-" + text + "\n")
