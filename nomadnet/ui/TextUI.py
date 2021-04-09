import RNS
import importlib
import time

from nomadnet import NomadNetworkApp
from nomadnet.ui import *

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
        
        self.main_display = DemoDisplay(self, self.app)
        
        if intro_timeout > 0:
            self.intro_display = IntroDisplay(self.app)
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


class DemoDisplay():
    def __init__(self, ui, app):
        import urwid

        def color_mono(btn):
            ui.set_colormode(nomadnet.ui.COLORMODE_MONO)

        def color_16(btn):
            ui.set_colormode(nomadnet.ui.COLORMODE_16)

        def color_88(btn):
            ui.set_colormode(nomadnet.ui.COLORMODE_88)

        def color_8bit(btn):
            ui.set_colormode(nomadnet.ui.COLORMODE_256)

        def color_true(btn):
            ui.set_colormode(nomadnet.ui.COLORMODE_TRUE)

        pile = urwid.Pile([
            urwid.Text(("heading", "This is a heading")),
            urwid.Text(("body_text", "Hello World \U0001F332")),
            urwid.Button(("buttons", "Monochrome"), color_mono),
            urwid.Button(("buttons", "16 color"), color_16),
            urwid.Button(("buttons", "88 color"), color_88),
            urwid.Button(("buttons", "256 color"), color_8bit),
            urwid.Button(("buttons", "True color"), color_true),
        ])

        self.widget = urwid.Filler(pile, 'top')

class MainDisplay():
    def __init__(self, app):
        import urwid

        pile = urwid.Pile([
            urwid.Text(("body_text", "Hello World \U0001F332")),
        ])

        self.widget = urwid.Filler(pile, 'top')

class IntroDisplay():
    def __init__(self, app):
        import urwid
        self.app = app

        font = urwid.font.HalfBlock5x4Font()

        big_text = urwid.BigText(("intro_title", "Nomad Network"), font)
        big_text = urwid.Padding(big_text, align="center", width="clip")

        intro = urwid.Pile([
            big_text,
            urwid.Text(("Version %s" % (str(self.app.version))), align="center"),
            urwid.Divider(),
            urwid.Text(("-= Starting =- "), align="center"),
        ])

        self.widget = urwid.Filler(intro) 