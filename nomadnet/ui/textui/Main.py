import RNS

from .Network import *
from .Conversations import *
from .Directory import *
from .Map import *

class SubDisplays():
    def __init__(self, app):
        import urwid
        self.app = app
        self.network_display = NetworkDisplay(self.app)
        self.conversations_display = ConversationsDisplay(self.app)
        self.directory_display = DirectoryDisplay(self.app)
        self.map_display = MapDisplay(self.app)

        self.active_display = self.network_display

    def active(self):
        return self.active_display


class MainDisplay():
    def __init__(self, ui, app):
        import urwid
        self.ui = ui
        self.app = app

        self.menu_display = MenuDisplay(self.app, self)
        self.sub_displays = SubDisplays(self.app)

        self.frame = urwid.Frame(self.sub_displays.active().widget, header=self.menu_display.widget, footer=self.sub_displays.active().shortcuts().widget)
        self.widget = self.frame

    def show_network(self, user_data):
        self.sub_displays.active_display = self.sub_displays.network_display
        self.update_active_sub_display()

    def show_conversations(self, user_data):
        self.sub_displays.active_display = self.sub_displays.conversations_display
        self.update_active_sub_display()

    def show_directory(self, user_data):
        self.sub_displays.active_display = self.sub_displays.directory_display
        self.update_active_sub_display()

    def show_map(self, user_data):
        self.sub_displays.active_display = self.sub_displays.map_display
        self.update_active_sub_display()

    def update_active_sub_display(self):
        self.frame.contents["body"] = (self.sub_displays.active().widget, None)
        self.frame.contents["footer"] = (self.sub_displays.active().shortcuts().widget, None)


class MenuDisplay():
    def __init__(self, app, handler):
        import urwid

        class MenuButton(urwid.Button):
            button_left = urwid.Text('[')
            button_right = urwid.Text(']')

        self.app = app

        menu_text            = ("pack", urwid.Text(" \U00002638"))
        button_network       = (11, MenuButton("Network", on_press=handler.show_network))
        button_conversations = (17, MenuButton("Conversations", on_press=handler.show_conversations))
        button_directory     = (13, MenuButton("Directory", on_press=handler.show_directory))
        button_map           = (7, MenuButton("Map", on_press=handler.show_map))

        buttons = [menu_text, button_network, button_conversations, button_directory, button_map]
        columns = urwid.Columns(buttons, dividechars=1)

        self.widget = urwid.AttrMap(columns, "menubar")
