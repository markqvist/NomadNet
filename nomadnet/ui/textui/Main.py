import RNS
import time

from .Network import *
from .Conversations import *
from .Directory import *
from .Map import *
import urwid

class SubDisplays():
    def __init__(self, app):
        self.app = app
        self.network_display = NetworkDisplay(self.app)
        self.conversations_display = ConversationsDisplay(self.app)
        self.directory_display = DirectoryDisplay(self.app)
        self.map_display = MapDisplay(self.app)

        self.active_display = self.conversations_display

    def active(self):
        return self.active_display

class MenuButton(urwid.Button):
    button_left = urwid.Text('[')
    button_right = urwid.Text(']')

class MainFrame(urwid.Frame):
    FOCUS_CHECK_TIMEOUT = 0.25

    def __init__(self, body, header=None, footer=None, delegate=None):
        self.delegate = delegate
        self.current_focus = None
        super().__init__(body, header, footer)

    def keypress_focus_check(self, deferred=False):
        current_focus = self.delegate.widget.get_focus_widgets()[-1]

        if deferred:
            if current_focus != self.current_focus:
                self.focus_changed()
        else:
            def deferred_focus_check(loop, user_data):
                self.keypress_focus_check(deferred=True)
            self.delegate.app.ui.loop.set_alarm_in(MainFrame.FOCUS_CHECK_TIMEOUT, deferred_focus_check)

        self.current_focus = current_focus

    def focus_changed(self):
        current_focus = self.delegate.widget.get_focus_widgets()[-1]
        current_focus_path = self.delegate.widget.get_focus_path()
        
        if len(current_focus_path) > 1:
            if current_focus_path[0] == "body":
                self.delegate.update_active_shortcuts()

        if self.delegate.sub_displays.active() == self.delegate.sub_displays.conversations_display:
            # Needed to refresh indicativelistbox styles on mouse focus change
            self.delegate.sub_displays.conversations_display.focus_change_event()

    def mouse_event(self, size, event, button, col, row, focus):
        current_focus = self.delegate.widget.get_focus_widgets()[-1]
        if current_focus != self.current_focus:
            self.focus_changed()

        self.current_focus = current_focus
        return super(MainFrame, self).mouse_event(size, event, button, col, row, focus)

    def keypress(self, size, key):
        self.keypress_focus_check()
        
        if key == "ctrl q":
            raise urwid.ExitMainLoop

        return super(MainFrame, self).keypress(size, key)

class MainDisplay():
    def __init__(self, ui, app):
        self.ui = ui
        self.app = app

        self.menu_display = MenuDisplay(self.app, self)
        self.sub_displays = SubDisplays(self.app)

        self.frame = MainFrame(self.sub_displays.active().widget, header=self.menu_display.widget, footer=self.sub_displays.active().shortcuts().widget, delegate=self)
        self.widget = self.frame

    def show_network(self, user_data):
        self.sub_displays.active_display = self.sub_displays.network_display
        self.update_active_sub_display()
        self.sub_displays.network_display.start()

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
        self.update_active_shortcuts()

    def update_active_shortcuts(self):
        self.frame.contents["footer"] = (self.sub_displays.active().shortcuts().widget, None)

    def quit(self, sender=None):
        raise urwid.ExitMainLoop


class MenuColumns(urwid.Columns):
    def keypress(self, size, key):
        if key == "tab" or key == "down":
            self.handler.frame.set_focus("body")

        return super(MenuColumns, self).keypress(size, key)

class MenuDisplay():
    def __init__(self, app, handler):
        self.app = app

        menu_text            = ("pack", urwid.Text(" \U00002638"))
        button_network       = (11, MenuButton("Network", on_press=handler.show_network))
        button_conversations = (17, MenuButton("Conversations", on_press=handler.show_conversations))
        button_directory     = (13, MenuButton("Directory", on_press=handler.show_directory))
        button_map           = (7, MenuButton("Map", on_press=handler.show_map))
        button_quit          = (8, MenuButton("Quit", on_press=handler.quit))

        # buttons = [menu_text, button_conversations, button_node, button_directory, button_map]
        buttons = [menu_text, button_conversations, button_network, button_quit]
        columns = MenuColumns(buttons, dividechars=1)
        columns.handler = handler

        self.widget = urwid.AttrMap(columns, "menubar")
