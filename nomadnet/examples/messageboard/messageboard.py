# Simple message board that can be hosted on a NomadNet node, messages can be posted by 'conversing' with a unique peer, all messages are then forwarded to the message board.
# https://github.com/chengtripp/lxmf_messageboard

import RNS
import LXMF
import os, time
from queue import Queue
import RNS.vendor.umsgpack as msgpack

display_name = "NomadNet Message Board"
max_messages = 20

def setup_lxmf():
    if os.path.isfile(identitypath):
        identity = RNS.Identity.from_file(identitypath)
        RNS.log('Loaded identity from file', RNS.LOG_INFO)
    else:
        RNS.log('No Primary Identity file found, creating new...', RNS.LOG_INFO)
        identity = RNS.Identity()
        identity.to_file(identitypath)

    return identity

def lxmf_delivery(message):
    # Do something here with a received message
    RNS.log("A message was received: "+str(message.content.decode('utf-8')))

    message_content = message.content.decode('utf-8')
    source_hash_text = RNS.hexrep(message.source_hash, delimit=False)

    #Create username (just first 5 char of your addr)
    username = source_hash_text[0:5]

    RNS.log('Username: {}'.format(username), RNS.LOG_INFO)

    time_string = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(message.timestamp))
    new_message = '{} {}: {}\n'.format(time_string, username, message_content)

    # Push message to board
    # First read message board (if it exists
    if os.path.isfile(boardpath):
        f = open(boardpath, "rb")
        message_board = msgpack.unpack(f)
        f.close()
    else:
        message_board = []

    #Check we aren't doubling up (this can sometimes happen if there is an error initially and it then gets fixed)
    if new_message not in message_board:
        # Append our new message to the list
        message_board.append(new_message)

    # Prune the message board if needed
    while len(message_board) > max_messages:
        RNS.log('Pruning Message Board')
        message_board.pop(0)

    # Now open the board and write the updated list
    f = open(boardpath, "wb")
    msgpack.pack(message_board, f)
    f.close()

    # Send reply
    message_reply = '{}_{}_Your message has been added to the messageboard'.format(source_hash_text, time.time())
    q.put(message_reply)

def announce_now(lxmf_destination):
    lxmf_destination.announce()

def send_message(destination_hash, message_content):
    try:
      # Make a binary destination hash from a hexadecimal string
      destination_hash = bytes.fromhex(destination_hash)

    except Exception as e:
      RNS.log("Invalid destination hash", RNS.LOG_ERROR)
      return

    # Check that size is correct
    if not len(destination_hash) == RNS.Reticulum.TRUNCATED_HASHLENGTH//8:
      RNS.log("Invalid destination hash length", RNS.LOG_ERROR)

    else:
      # Length of address was correct, let's try to recall the
      # corresponding Identity
      destination_identity = RNS.Identity.recall(destination_hash)

      if destination_identity == None:
        # No path/identity known, we'll have to abort or request one
        RNS.log("Could not recall an Identity for the requested address. You have probably never received an announce from it. Try requesting a path from the network first. In fact, let's do this now :)", RNS.LOG_ERROR)
        RNS.Transport.request_path(destination_hash)
        RNS.log("OK, a path was requested. If the network knows a path, you will receive an announce with the Identity data shortly.", RNS.LOG_INFO)

      else:
        # We know the identity for the destination hash, let's
        # reconstruct a destination object.
        lxmf_destination = RNS.Destination(destination_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")

        # Create a new message object
        lxm = LXMF.LXMessage(lxmf_destination, local_lxmf_destination, message_content, title="Reply", desired_method=LXMF.LXMessage.DIRECT)

        # You can optionally tell LXMF to try to send the message
        # as a propagated message if a direct link fails
        lxm.try_propagation_on_fail = True

        # Send it
        message_router.handle_outbound(lxm)

def announce_check():
    if os.path.isfile(announcepath):
        f = open(announcepath, "r")
        announce = int(f.readline())
        f.close()
    else:
        RNS.log('failed to open announcepath', RNS.LOG_DEBUG)
        announce = 1

    if announce > int(time.time()):
        RNS.log('Recent announcement', RNS.LOG_DEBUG)
    else:
        f = open(announcepath, "w")
        next_announce = int(time.time()) + 1800
        f.write(str(next_announce))
        f.close()
        announce_now(local_lxmf_destination)
        RNS.log('Announcement sent, expr set 1800 seconds', RNS.LOG_INFO)

#Setup Paths and Config Files
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

identitypath = configdir+"/storage/identity"
announcepath = configdir+"/storage/announce"
boardpath = configdir+"/storage/board"

# Message Queue
q = Queue(maxsize = 5)

# Start Reticulum and print out all the debug messages
reticulum = RNS.Reticulum(loglevel=RNS.LOG_VERBOSE)

# Create a Identity.
current_identity = setup_lxmf()

# Init the LXMF router
message_router = LXMF.LXMRouter(identity = current_identity, storagepath = configdir)

# Register a delivery destination (for yourself)
# In this example we use the same Identity as we used
# to instantiate the LXMF router. It could be a different one,
# but it can also just be the same, depending on what you want.
local_lxmf_destination = message_router.register_delivery_identity(current_identity, display_name=display_name)

# Set a callback for when a message is received
message_router.register_delivery_callback(lxmf_delivery)

# Announce node properties

RNS.log('LXMF Router ready to receive on: {}'.format(RNS.prettyhexrep(local_lxmf_destination.hash)), RNS.LOG_INFO)
announce_check()

while True:

    # Work through internal message queue
    for i in list(q.queue):
        message_id = q.get()
        split_message = message_id.split('_')
        destination_hash = split_message[0]
        message = split_message[2]
        RNS.log('{} {}'.format(destination_hash, message), RNS.LOG_INFO)
        send_message(destination_hash, message)

    # Check whether we need to make another announcement
    announce_check()

    #Sleep
    time.sleep(10)
