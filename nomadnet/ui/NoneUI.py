import RNS
import nomadnet
import time

from nomadnet import NomadNetworkApp

class NoneUI:

    def __init__(self):
        self.app = NomadNetworkApp.get_shared_instance()
        self.app.ui = self

        if not self.app.force_console_log:
            RNS.log("Nomad Network started in daemon mode, all further messages are logged to "+str(self.app.logfilepath), RNS.LOG_INFO, _override_destination=True)
        else:
            RNS.log("Nomad Network daemon started", RNS.LOG_INFO)

        while True:
            time.sleep(1)