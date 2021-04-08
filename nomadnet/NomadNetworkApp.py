import os
import RNS
import atexit

from .vendor.configobj import ConfigObj

class NomadNetworkApp:
    _shared_instance = None

    configdir = os.path.expanduser("~")+"/.nomadnetwork"

    def exit_handler():
        RNS.log("Nomad Network Client exit handler executing...")

    def __init__(self, configdir = None, rnsconfigdir = None):
        self.enable_client = False
        self.enable_node   = False
        self.identity      = None

        if configdir == None:
            self.configdir = NomadNetworkApp.configdir
        else:
            self.configdir = configdir

        if NomadNetworkApp._shared_instance == None:
            NomadNetworkApp._shared_instance = self

        self.configpath    = self.configdir+"/config"
        self.storagepath   = self.configdir+"/storage"
        self.identitypath   = self.configdir+"/storage/identity"
        self.cachepath     = self.configdir+"/storage/cache"
        self.resourcepath  = self.configdir+"/storage/resources"

        if not os.path.isdir(self.storagepath):
            os.makedirs(self.storagepath)

        if not os.path.isdir(self.cachepath):
            os.makedirs(self.cachepath)

        if not os.path.isdir(self.resourcepath):
            os.makedirs(self.resourcepath)

        if os.path.isfile(self.configpath):
            try:
                self.config = ConfigObj(self.configpath)
                RNS.log("Configuration loaded from "+self.configpath)
            except Exception as e:
                RNS.log("Could not parse the configuration at "+self.configpath, RNS.LOG_ERROR)
                RNS.log("Check your configuration file for errors!", RNS.LOG_ERROR)
                RNS.panic()
        else:
            RNS.log("Could not load config file, creating default configuration file...")
            self.createDefaultConfig()
            RNS.log("Default config file created. Make any necessary changes in "+self.configdir+"/config and start Nomad Network Client again.")
            RNS.log("Exiting now!")
            exit(1)

        if os.path.isfile(self.identitypath):
            try:
                self.identity = RNS.Identity.from_file(self.identitypath)
                if self.identity != None:
                    RNS.log("Loaded Primary Identity %s from %s" % (str(self.identity), self.identitypath))
                else:
                    RNS.log("Could not load the Primary Identity from "+self.identitypath, RNS.LOG_ERROR)
                    RNS.panic()
            except Exception as e:
                RNS.log("Could not load the Primary Identity from "+self.identitypath, RNS.LOG_ERROR)
                RNS.log("The contained exception was: %s" % (str(e)), RNS.LOG_ERROR)
                RNS.panic()
        else:
            try:
                RNS.log("No Primary Identity file found, creating new...")
                self.identity = RNS.Identity()
                self.identity.save(self.identitypath)
                RNS.log("Created new Primary Identity %s" % (str(self.identity)))
            except Exception as e:
                RNS.log("Could not create and save a new Primary Identity", RNS.LOG_ERROR)
                RNS.log("The contained exception was: %s" % (str(e)), RNS.LOG_ERROR)
                RNS.panic()

        self.applyConfig()

        self.rns = RNS.Reticulum(configdir = rnsconfigdir)

        atexit.register(self.exit_handler)


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

        if "client" in self.config:
            for option in self.config["client"]:
                value = self.config["client"][option]

                if option == "enable_client":
                    value = self.config["client"].as_bool(option)
                    self.enable_client = value

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

[client]

enable_client = Yes

[node]

enable_node = No

'''.splitlines()