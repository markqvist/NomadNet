import RNS
import importlib
import time

from nomadnet import NomadNetworkApp
from nomadnet.ui import *
from nomadnet.ui.textui import *

class TextUI:

    def __init__(self):
        self.app = NomadNetworkApp.get_shared_instance()
        self.loop = None

        if importlib.util.find_spec("urwid") != None:
            import urwid
        else:
            RNS.log("The text-mode user interface requires Urwid to be installed on your system.", RNS.LOG_ERROR)
            RNS.log("You can install it with the command: pip3 install urwid", RNS.LOG_ERROR)
            nomadnet.panic()

        urwid.set_encoding("UTF-8")

        intro_timeout = self.app.config["textui"]["intro_time"]
        colormode     = self.app.config["textui"]["colormode"]
        theme         = self.app.config["textui"]["theme"]

        palette       = nomadnet.ui.THEMES[theme]

        self.screen = urwid.raw_display.Screen()
        self.screen.register_palette(palette)
        
        #self.main_display = nomadnet.ui.textui.Extras.DemoDisplay(self, self.app)
        self.main_display = nomadnet.ui.textui.Main.MainDisplay(self, self.app)
        
        if intro_timeout > 0:
            self.intro_display = nomadnet.ui.textui.Extras.IntroDisplay(self.app)
            initial_widget = self.intro_display.widget
        else:
            initial_widget = self.main_display.widget

        self.loop = urwid.MainLoop(initial_widget, screen=self.screen)

        if intro_timeout > 0:
            self.loop.set_alarm_in(intro_timeout, self.display_main)
        
        self.set_colormode(colormode)

        self.loop.run()

    def set_colormode(self, colormode):
        self.screen.set_terminal_properties(colormode)
        self.screen.reset_default_terminal_palette()

    def display_main(self, loop, user_data):
        self.loop.widget = self.main_display.widget
