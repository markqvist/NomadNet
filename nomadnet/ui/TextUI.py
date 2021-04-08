import RNS
from nomadnet import NomadNetworkApp
import importlib

class TextUI:

    def __init__(self):
        self.app = NomadNetworkApp.get_shared_instance()

        self.loop = None
        self.main_widget = None

        if importlib.util.find_spec("urwid") != None:
            import urwid
        else:
            RNS.log("The text-mode user interface requires Urwid to be installed on your system.", RNS.LOG_ERROR)
            RNS.log("You can install it with the command: pip3 install urwid", RNS.LOG_ERROR)
            nomadnet.panic()

        loop = urwid.MainLoop(self.build_intro())
        loop.run()

    def build_intro(self):
        import urwid

        font = urwid.font.HalfBlock5x4Font()

        big_text = "Nomad Network"
        big_text = urwid.BigText(("intro_bigtext", big_text), font)
        big_text = urwid.Padding(big_text, align="center", width="clip")

        intro = urwid.Pile([
            big_text,
            urwid.Text(["Version %s" % (str(self.app.version))], align="center"),
            urwid.Divider(),
            urwid.Text(("intro_smalltext", "-= Starting =-"), align="center"),
        ])

        return urwid.Filler(intro) 