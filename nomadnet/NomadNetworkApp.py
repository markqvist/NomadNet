import os
import time
import atexit

import RNS
import LXMF
import nomadnet

from nomadnet.Directory import DirectoryEntry

import RNS.vendor.umsgpack as msgpack

from ._version import __version__
from .vendor.configobj import ConfigObj

class NomadNetworkApp:
    time_format      = "%Y-%m-%d %H:%M:%S"
    _shared_instance = None

    configdir = os.path.expanduser("~")+"/.nomadnetwork"

    def exit_handler(self):
        RNS.log("Nomad Network Client exit handler executing...", RNS.LOG_VERBOSE)
        RNS.log("Saving directory...", RNS.LOG_VERBOSE)
        self.directory.save_to_disk()
        RNS.log("Nomad Network Client exiting now", RNS.LOG_VERBOSE)

    def __init__(self, configdir = None, rnsconfigdir = None):
        self.version       = __version__
        self.enable_client = False
        self.enable_node   = False
        self.identity      = None

        self.uimode        = None

        if configdir == None:
            self.configdir = NomadNetworkApp.configdir
        else:
            self.configdir = configdir

        if NomadNetworkApp._shared_instance == None:
            NomadNetworkApp._shared_instance = self

        self.rns = RNS.Reticulum(configdir = rnsconfigdir)

        self.configpath        = self.configdir+"/config"
        self.logfilepath       = self.configdir+"/logfile"
        self.storagepath       = self.configdir+"/storage"
        self.identitypath      = self.configdir+"/storage/identity"
        self.cachepath         = self.configdir+"/storage/cache"
        self.resourcepath      = self.configdir+"/storage/resources"
        self.conversationpath  = self.configdir+"/storage/conversations"
        self.directorypath     = self.configdir+"/storage/directory"
        self.peersettingspath  = self.configdir+"/storage/peersettings"

        self.pagespath         = self.configdir+"/storage/pages"
        self.filespath         = self.configdir+"/storage/files"
        self.cachepath         = self.configdir+"/storage/cache"

        self.downloads_path    = os.path.expanduser("~/Downloads")

        self.firstrun          = False

        self.peer_announce_at_start  = True
        self.try_propagation_on_fail = True

        if not os.path.isdir(self.storagepath):
            os.makedirs(self.storagepath)

        if not os.path.isdir(self.cachepath):
            os.makedirs(self.cachepath)

        if not os.path.isdir(self.resourcepath):
            os.makedirs(self.resourcepath)

        if not os.path.isdir(self.conversationpath):
            os.makedirs(self.conversationpath)

        if not os.path.isdir(self.pagespath):
            os.makedirs(self.pagespath)

        if not os.path.isdir(self.filespath):
            os.makedirs(self.filespath)

        if not os.path.isdir(self.cachepath):
            os.makedirs(self.cachepath)

        if os.path.isfile(self.configpath):
            try:
                self.config = ConfigObj(self.configpath)
                try:
                    self.applyConfig()
                except Exception as e:
                    RNS.log("The configuration file is invalid. The contained exception was: "+str(e), RNS.LOG_ERROR)
                    nomadnet.panic()

                RNS.log("Configuration loaded from "+self.configpath)
            except Exception as e:
                RNS.log("Could not parse the configuration at "+self.configpath, RNS.LOG_ERROR)
                RNS.log("Check your configuration file for errors!", RNS.LOG_ERROR)
                nomadnet.panic()
        else:
            RNS.log("Could not load config file, creating default configuration file...")
            self.createDefaultConfig()
            self.firstrun = True

        if os.path.isfile(self.identitypath):
            try:
                self.identity = RNS.Identity.from_file(self.identitypath)
                if self.identity != None:
                    RNS.log("Loaded Primary Identity %s from %s" % (str(self.identity), self.identitypath))
                else:
                    RNS.log("Could not load the Primary Identity from "+self.identitypath, RNS.LOG_ERROR)
                    nomadnet.panic()
            except Exception as e:
                RNS.log("Could not load the Primary Identity from "+self.identitypath, RNS.LOG_ERROR)
                RNS.log("The contained exception was: %s" % (str(e)), RNS.LOG_ERROR)
                nomadnet.panic()
        else:
            try:
                RNS.log("No Primary Identity file found, creating new...")
                self.identity = RNS.Identity()
                self.identity.to_file(self.identitypath)
                RNS.log("Created new Primary Identity %s" % (str(self.identity)))
            except Exception as e:
                RNS.log("Could not create and save a new Primary Identity", RNS.LOG_ERROR)
                RNS.log("The contained exception was: %s" % (str(e)), RNS.LOG_ERROR)
                nomadnet.panic()

        if os.path.isfile(self.peersettingspath):
            try:
                file = open(self.peersettingspath, "rb")
                self.peer_settings = msgpack.unpackb(file.read())
                file.close()

                if not "node_last_announce" in self.peer_settings:
                    self.peer_settings["node_last_announce"] = None

                if not "propagation_node" in self.peer_settings:
                    self.peer_settings["propagation_node"] = None

            except Exception as e:
                RNS.log("Could not load local peer settings from "+self.peersettingspath, RNS.LOG_ERROR)
                RNS.log("The contained exception was: %s" % (str(e)), RNS.LOG_ERROR)
                nomadnet.panic()
        else:
            try:
                RNS.log("No peer settings file found, creating new...")
                self.peer_settings = {
                    "display_name": "Anonymous Peer",
                    "announce_interval": None,
                    "last_announce": None,
                    "node_last_announce": None,
                    "propagation_node": None
                }
                self.save_peer_settings()
                RNS.log("Created new peer settings file")
            except Exception as e:
                RNS.log("Could not create and save a new peer settings file", RNS.LOG_ERROR)
                RNS.log("The contained exception was: %s" % (str(e)), RNS.LOG_ERROR)
                nomadnet.panic()


        self.directory = nomadnet.Directory(self)

        self.message_router = LXMF.LXMRouter(identity = self.identity, storagepath = self.storagepath, autopeer = True)
        self.message_router.register_delivery_callback(self.lxmf_delivery)

        self.lxmf_destination = self.message_router.register_delivery_identity(self.identity, display_name=self.peer_settings["display_name"])
        self.lxmf_destination.set_default_app_data(self.get_display_name_bytes)

        RNS.Identity.remember(
            packet_hash=None,
            destination_hash=self.lxmf_destination.hash,
            public_key=self.identity.get_public_key(),
            app_data=None
        )

        RNS.log("LXMF Router ready to receive on: "+RNS.prettyhexrep(self.lxmf_destination.hash))

        if self.enable_node:
            self.message_router.enable_propagation()
            RNS.log("LXMF Propagation Node started on: "+RNS.prettyhexrep(self.message_router.propagation_destination.hash))
            self.node = nomadnet.Node(self)
        else:
            self.node = None

        RNS.Transport.register_announce_handler(nomadnet.Conversation)
        RNS.Transport.register_announce_handler(nomadnet.Directory)

        self.autoselect_propagation_node()

        if self.peer_announce_at_start:
            self.announce_now()

        atexit.register(self.exit_handler)

        nomadnet.ui.spawn(self.uimode)

    def set_display_name(self, display_name):
        self.peer_settings["display_name"] = display_name
        self.lxmf_destination.display_name = display_name
        self.save_peer_settings()

    def get_display_name(self):
        return self.peer_settings["display_name"]

    def get_display_name_bytes(self):
        return self.peer_settings["display_name"].encode("utf-8")

    def get_sync_status(self):
        if self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_IDLE:
            return "Idle"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_PATH_REQUESTED:
            return "Path requested"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_LINK_ESTABLISHING:
            return "Establishing link"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_LINK_ESTABLISHED:
            return "Link established"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_REQUEST_SENT:
            return "Sync request sent"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_RECEIVING:
            return "Receiving messages"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_RESPONSE_RECEIVED:
            return "Messages received"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_COMPLETE:
            new_msgs = self.message_router.propagation_transfer_last_result
            if new_msgs == 0:
                return "Done, no new messages"
            else:
                return "Downloaded "+str(new_msgs)+" new messages"
        else:
            return "Unknown"

    def sync_status_show_percent(self):
        if self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_IDLE:
            return False
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_PATH_REQUESTED:
            return True
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_LINK_ESTABLISHING:
            return True
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_LINK_ESTABLISHED:
            return True
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_REQUEST_SENT:
            return True
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_RECEIVING:
            return True
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_RESPONSE_RECEIVED:
            return True
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_COMPLETE:
            return False
        else:
            return False

    def get_sync_progress(self):
        return self.message_router.propagation_transfer_progress

    def request_lxmf_sync(self, limit = None):
        if self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_IDLE or self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_COMPLETE:
            self.message_router.request_messages_from_propagation_node(self.identity, max_messages = limit)

    def cancel_lxmf_sync(self):
        if self.message_router.propagation_transfer_state != LXMF.LXMRouter.PR_IDLE:
            self.message_router.cancel_propagation_node_requests()

    def announce_now(self):
        self.lxmf_destination.announce()
        self.peer_settings["last_announce"] = time.time()
        self.save_peer_settings()

    def autoselect_propagation_node(self):
        selected_node = None

        if "propagation_node" in self.peer_settings and self.directory.find(self.peer_settings["propagation_node"]):
            selected_node = self.directory.find(self.peer_settings["propagation_node"])
        else:
            nodes = self.directory.known_nodes()
            trusted_nodes = []

            best_hops = RNS.Transport.PATHFINDER_M+1

            for node in nodes:
                if node.trust_level == DirectoryEntry.TRUSTED:
                    hops = RNS.Transport.hops_to(node.source_hash)

                    if hops < best_hops:
                        best_hops = hops
                        selected_node = node

        if selected_node == None:
            RNS.log("Could not autoselect a prepagation node! LXMF propagation will not be available until a trusted node announces on the network.", RNS.LOG_WARNING)
        else:
            node_identity = RNS.Identity.recall(selected_node.source_hash)
            if node_identity != None:
                propagation_hash = RNS.Destination.hash_from_name_and_identity("lxmf.propagation", node_identity)
                RNS.log("Selecting "+selected_node.display_name+" "+RNS.prettyhexrep(propagation_hash)+" as default LXMF propagation node", RNS.LOG_INFO)
                self.message_router.set_outbound_propagation_node(propagation_hash)
            else:
                RNS.log("Could not recall identity for autoselected LXMF propagation node "+RNS.prettyhexrep(selected_node.source_hash), RNS.LOG_WARNING)
                RNS.log("LXMF propagation will not be available until a trusted node announces on the network.", RNS.LOG_WARNING)

    def get_user_selected_propagation_node(self):
        if "propagation_node" in self.peer_settings:
            return self.peer_settings["propagation_node"]
        else:
            return None

    def set_user_selected_propagation_node(self, node_hash):
        self.peer_settings["propagation_node"] = node_hash
        self.save_peer_settings()
        self.autoselect_propagation_node()
    
    def get_default_propagation_node(self):
        return self.message_router.get_outbound_propagation_node()

    def save_peer_settings(self):
        file = open(self.peersettingspath, "wb")
        file.write(msgpack.packb(self.peer_settings))
        file.close()

    def lxmf_delivery(self, message):
        time_string = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(message.timestamp))
        signature_string = "Signature is invalid, reason undetermined"
        if message.signature_validated:
            signature_string = "Validated"
        else:
            if message.unverified_reason == LXMF.LXMessage.SIGNATURE_INVALID:
                signature_string = "Invalid signature"
            if message.unverified_reason == LXMF.LXMessage.SOURCE_UNKNOWN:
                signature_string = "Cannot verify, source is unknown"

        nomadnet.Conversation.ingest(message, self)

    def conversations(self):
        return nomadnet.Conversation.conversation_list(self)

    def has_unread_conversations(self):
        if len(nomadnet.Conversation.unread_conversations) > 0:
            return True
        else:
            return False

    def conversation_is_unread(self, source_hash):
        if bytes.fromhex(source_hash) in nomadnet.Conversation.unread_conversations:
            return True
        else:
            return False

    def mark_conversation_read(self, source_hash):
        if bytes.fromhex(source_hash) in nomadnet.Conversation.unread_conversations:
            nomadnet.Conversation.unread_conversations.pop(bytes.fromhex(source_hash))
            if os.path.isfile(self.conversationpath + "/" + source_hash + "/unread"):
                os.unlink(self.conversationpath + "/" + source_hash + "/unread")

    def createDefaultConfig(self):
        self.config = ConfigObj(__default_nomadnet_config__)
        self.config.filename = self.configpath
        
        if not os.path.isdir(self.configdir):
            os.makedirs(self.configdir)
        self.config.write()
        self.applyConfig()


    def applyConfig(self):
        if "logging" in self.config:
            for option in self.config["logging"]:
                value = self.config["logging"][option]
                if option == "loglevel":
                    RNS.loglevel = int(value)
                    if RNS.loglevel < 0:
                        RNS.loglevel = 0
                    if RNS.loglevel > 7:
                        RNS.loglevel = 7
                if option == "destination":
                    if value.lower() == "file":
                        RNS.logdest = RNS.LOG_FILE
                        if "logfile" in self.config["logging"]:
                            self.logfilepath = self.config["logging"]["logfile"]
                        RNS.logfile = self.logfilepath
                    else:
                        RNS.logdest = RNS.LOG_STDOUT

        if "client" in self.config:
            for option in self.config["client"]:
                value = self.config["client"][option]

                if option == "enable_client":
                    value = self.config["client"].as_bool(option)
                    self.enable_client = value

                if option == "downloads_path":
                    value = self.config["client"]["downloads_path"]
                    self.downloads_path = os.path.expanduser(value)

                if option == "announce_at_start":
                    value = self.config["client"].as_bool(option)
                    self.peer_announce_at_start = value

                if option == "try_propagation_on_send_fail":
                    value = self.config["client"].as_bool(option)
                    self.try_propagation_on_fail = value

                if option == "user_interface":
                    value = value.lower()
                    if value == "none":
                        self.uimode = nomadnet.ui.UI_NONE
                    if value == "menu":
                        self.uimode = nomadnet.ui.UI_MENU
                    if value == "text":
                        self.uimode = nomadnet.ui.UI_TEXT
                        if "textui" in self.config:
                            if not "intro_time" in self.config["textui"]:
                                self.config["textui"]["intro_time"] = 1
                            else:
                                self.config["textui"]["intro_time"] = self.config["textui"].as_int("intro_time")

                            if not "editor" in self.config["textui"]:
                                self.config["textui"]["editor"] = "editor"

                            if not "glyphs" in self.config["textui"]:
                                self.config["textui"]["glyphs"] = "unicode"

                            if not "mouse_enabled" in self.config["textui"]:
                                self.config["textui"]["mouse_enabled"] = True
                            else:
                                self.config["textui"]["mouse_enabled"] = self.config["textui"].as_bool("mouse_enabled")

                            if not "hide_guide" in self.config["textui"]:
                                self.config["textui"]["hide_guide"] = False
                            else:
                                self.config["textui"]["hide_guide"] = self.config["textui"].as_bool("hide_guide")

                            if not "animation_interval" in self.config["textui"]:
                                self.config["textui"]["animation_interval"] = 1
                            else:
                                self.config["textui"]["animation_interval"] = self.config["textui"].as_int("animation_interval")

                            if not "colormode" in self.config["textui"]:
                                self.config["textui"]["colormode"] = nomadnet.ui.COLORMODE_16
                            else:
                                if self.config["textui"]["colormode"].lower() == "monochrome":
                                    self.config["textui"]["colormode"] = nomadnet.ui.TextUI.COLORMODE_MONO
                                elif self.config["textui"]["colormode"].lower() == "16":
                                    self.config["textui"]["colormode"] = nomadnet.ui.TextUI.COLORMODE_16
                                elif self.config["textui"]["colormode"].lower() == "88":
                                    self.config["textui"]["colormode"] = nomadnet.ui.TextUI.COLORMODE_88
                                elif self.config["textui"]["colormode"].lower() == "256":
                                    self.config["textui"]["colormode"] = nomadnet.ui.TextUI.COLORMODE_256
                                elif self.config["textui"]["colormode"].lower() == "24bit":
                                    self.config["textui"]["colormode"] = nomadnet.ui.TextUI.COLORMODE_TRUE
                                else:
                                    raise ValueError("The selected Text UI color mode is invalid")

                            if not "theme" in self.config["textui"]:
                                self.config["textui"]["theme"] = nomadnet.ui.TextUI.THEME_DARK
                            else:
                                if self.config["textui"]["theme"].lower() == "dark":
                                    self.config["textui"]["theme"] = nomadnet.ui.TextUI.THEME_DARK
                                elif self.config["textui"]["theme"].lower() == "light":
                                    self.config["textui"]["theme"] = nomadnet.ui.TextUI.THEME_LIGHT
                                else:
                                    raise ValueError("The selected Text UI theme is invalid")
                        else:
                            raise KeyError("Text UI selected in configuration file, but no [textui] section found")
                    if value == "graphical":
                        self.uimode = nomadnet.ui.UI_GRAPHICAL
                    if value == "web":
                        self.uimode = nomadnet.ui.UI_WEB

        if "node" in self.config:
            if not "enable_node" in self.config["node"]:
                self.enable_node = False
            else:
                self.enable_node = self.config["node"].as_bool("enable_node")

            if not "node_name" in self.config["node"]:
                self.node_name = None
            else:
                value = self.config["node"]["node_name"]
                if value.lower() == "none":
                    self.node_name = None
                else:
                    self.node_name = self.config["node"]["node_name"]

            if not "announce_at_start" in self.config["node"]:
                self.node_announce_at_start = False
            else:
                value = self.config["node"].as_bool("announce_at_start")
                self.node_announce_at_start = value

            if not "announce_interval" in self.config["node"]:
                self.node_announce_interval = 720
            else:
                value = self.config["node"].as_int("announce_interval")
                if value < 1:
                    value = 1
                self.node_announce_interval = value

            if "pages_path" in self.config["node"]:
                self.pagespath = self.config["node"]["pages_path"]

            if "files_path" in self.config["node"]:
                self.filespath = self.config["node"]["files_path"]

              
    @staticmethod
    def get_shared_instance():
        if NomadNetworkApp._shared_instance != None:
            return NomadNetworkApp._shared_instance
        else:
            raise UnboundLocalError("No Nomad Network applications have been instantiated yet")


    def quit(self):
        RNS.log("Nomad Network Client shutting down...")
        os._exit(0)


# Default configuration file:
__default_nomadnet_config__ = '''# This is the default Nomad Network config file.
# You should probably edit it to suit your needs and use-case,

[logging]
# Valid log levels are 0 through 7:
#   0: Log only critical information
#   1: Log errors and lower log levels
#   2: Log warnings and lower log levels
#   3: Log notices and lower log levels
#   4: Log info and lower (this is the default)
#   5: Verbose logging
#   6: Debug logging
#   7: Extreme logging

loglevel = 4
destination = file

[client]

enable_client = yes
user_interface = text
downloads_path = ~/Downloads

# By default, the peer is announced at startup
# to let other peers reach it immediately.
announce_at_start = yes

# By default, the client will try to deliver a
# message via the LXMF propagation network, if
# a direct delivery to the recipient is not
# possible.
try_propagation_on_send_fail = yes

[textui]

# Amount of time to show intro screen
intro_time = 1

# You can specify the display theme.
# theme = light
theme = dark

# Specify the number of colors to use
# valid colormodes are:
# monochrome, 16, 88, 256 and 24bit
#
# The default is a conservative 256 colors.
# If your terminal does not support this,
# you can lower it. Some terminals support
# 24 bit color.

# colormode = monochrome
# colormode = 16
# colormode = 88
colormode = 256
# colormode = 24bit

# By default, unicode glyphs are used. If
# you have a Nerd Font installed, you can
# enable this for a better user interface.
# You can also enable plain text glyphs if
# your terminal doesn't support unicode.

# glyphs = plain
glyphs = unicode
# glyphs = nerdfont

# You can specify whether mouse events
# should be considered as input to the
# application. On by default.
mouse_enabled = True

# What editor to use for editing text. By
# default the operating systems "editor"
# alias will be used.
editor = editor

# If you don't want the Guide section to
# show up in the menu, you can disable it.

hide_guide = no

[node]

# Whether to enable node hosting

enable_node = no

# The node name will be visible to other
# peers on the network, and included in
# announces.

node_name = None

# Automatic announce interval in minutes.
# 6 hours by default.

announce_interval = 360

# Whether to announce when the node starts

announce_at_start = Yes

'''.splitlines()