import os
import time
import atexit

import RNS
import LXMF
import nomadnet

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

        if not os.path.isdir(self.storagepath):
            os.makedirs(self.storagepath)

        if not os.path.isdir(self.cachepath):
            os.makedirs(self.cachepath)

        if not os.path.isdir(self.resourcepath):
            os.makedirs(self.resourcepath)

        if not os.path.isdir(self.conversationpath):
            os.makedirs(self.conversationpath)

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
            except Exception as e:
                RNS.log("Could not load local peer settings from "+self.peersettingspath, RNS.LOG_ERROR)
                RNS.log("The contained exception was: %s" % (str(e)), RNS.LOG_ERROR)
                nomadnet.panic()
        else:
            try:
                RNS.log("No peer settings file found, creating new...")
                self.peer_settings = {
                    "display_name": "",
                    "announce_interval": None,
                    "last_announce": None,
                }
                self.save_peer_settings()
                RNS.log("Created new peer settings file")
            except Exception as e:
                RNS.log("Could not create and save a new peer settings file", RNS.LOG_ERROR)
                RNS.log("The contained exception was: %s" % (str(e)), RNS.LOG_ERROR)
                nomadnet.panic()


        atexit.register(self.exit_handler)

        self.message_router = LXMF.LXMRouter()
        self.message_router.register_delivery_callback(self.lxmf_delivery)

        self.lxmf_destination = self.message_router.register_delivery_identity(self.identity, display_name=self.peer_settings["display_name"])
        self.lxmf_destination.set_default_app_data(self.get_display_name_bytes)

        RNS.Identity.remember(
            packet_hash=None,
            destination_hash=self.lxmf_destination.hash,
            public_key=self.identity.pub_bytes,
            app_data=None
        )

        RNS.Transport.register_announce_handler(nomadnet.Conversation)

        RNS.log("LXMF Router ready to receive on: "+RNS.prettyhexrep(self.lxmf_destination.hash))

        self.directory = nomadnet.Directory.Directory(self)

        nomadnet.ui.spawn(self.uimode)

    def set_display_name(self, display_name):
        self.peer_settings["display_name"] = display_name
        self.lxmf_destination.display_name = display_name
        self.save_peer_settings()

    def get_display_name(self):
        return self.peer_settings["display_name"]

    def get_display_name_bytes(self):
        return self.peer_settings["display_name"].encode("utf-8")

    def announce_now(self):
        self.lxmf_destination.announce()
        self.peer_settings["last_announce"] = time.time()
        self.save_peer_settings()

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
            for option in self.config["node"]:
                value = self.config["node"][option]

                if option == "enable_node":
                    value = self.config["node"].as_bool(option)
                    self.enable_node = value

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

enable_client = Yes
user_interface = text

[textui]

intro_time = 1

# Specify the number of colors to use
# valid colormodes are:
# monochrome, 16, 88, 256 and 24bit
#
# The default is a conservative 88 colors,
# but 256 colors can probably be used on
# most terminals. Some terminals

# colormode = monochrome
# colormode = 16
colormode = 88
# colormode = 256
# colormode = 24bit

[node]

enable_node = No

'''.splitlines()