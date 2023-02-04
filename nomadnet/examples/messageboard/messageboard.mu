#!/bin/python3
import time
import os
import RNS.vendor.umsgpack as msgpack

message_board_peer = 'please_replace'
userdir = os.path.expanduser("~")

if os.path.isdir("/etc/nomadmb") and os.path.isfile("/etc/nomadmb/config"):
    configdir = "/etc/nomadmb"
elif os.path.isdir(userdir+"/.config/nomadmb") and os.path.isfile(userdir+"/.config/nomadmb/config"):
    configdir = userdir+"/.config/nomadmb"
else:
    configdir = userdir+"/.nomadmb"

storagepath  = configdir+"/storage"
if not os.path.isdir(storagepath):
    os.makedirs(storagepath)

boardpath = configdir+"/storage/board"

print('`!`F222`Bddd`cNomadNet Message Board')

print('-')
print('`a`b`f')
print("")
print("To add a message to the board just converse with the NomadNet Message Board at `[lxmf@{}]".format(message_board_peer))
time_string = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
print("Last Updated: {}".format(time_string))
print("")
print('>Messages')
print("  Date       Time    Username     Message")
f = open(boardpath, "rb")
board_contents = msgpack.unpack(f)
board_contents.reverse()

for content in board_contents:
    print("`a{}".format(content.rstrip()))
    print("")

f.close()
