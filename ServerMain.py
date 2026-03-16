import log
import chatServer

log=log.logger(verbose=True)
server = chatServer.ServerConnect(log)
server.connect()
server.ManageMessages()
