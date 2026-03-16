import log
import chatClient
import ipWriteGui

log=log.logger(verbose=True)
ip=ipWriteGui.enableWindow()
client = chatClient.ClientConnect(log,ip)
client.connect()
client.ManageMessages()
