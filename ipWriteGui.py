#!/usr/bin/python
 
import wx
import os

def createFrame():
    frame = wx.Frame(None, -1)
    frame.SetDimensions(0,0,200,50)
    
def createTextInput(frame):
    dlg = wx.TextEntryDialog(frame, 'Enter Ip Of Server','Ip Entry')
    return dlg
    
def getIpValue(dlg):
    if dlg.ShowModal() == wx.ID_OK:
        ip=dlg.GetValue()
    else:
        os._exit(1)
    dlg.Destroy()
    return str(ip) 

def enableWindow():
    ip=""
    again=False
    app = wx.App(False)
    frame=createFrame()
    dlg=createTextInput(frame)
    ip=getIpValue(dlg)
    return ip

