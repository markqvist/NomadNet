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
        if configdir == None:
            self.configdir = NomadNetworkApp.configdir
        else:
            self.configdir = configdir

        self.rns = RNS.Reticulum(configdir = rnsconfigdir)

        if NomadNetworkApp._shared_instance == None:
            NomadNetworkApp._shared_instance = self

        atexit.register(self.exit_handler)


    @staticmethod
    def get_shared_instance():
        if NomadNetworkApp._shared_instance != None:
            return NomadNetworkApp._shared_instance
        else:
            raise UnboundLocalError("No Nomad Network applications have been instantiated yet")


    def quit(self):
        RNS.log("Nomad Network Client shutting down...")
        os._exit(0)