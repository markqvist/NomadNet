import nomadnet
import urwid
import platform

class ConfigDisplayShortcuts():
    def __init__(self, app):
        import urwid
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text(""), "shortcutbar")

class ConfigFiller(urwid.WidgetWrap):
    def __init__(self, widget, app):
        self.app = app
        self.filler = urwid.Filler(widget, "top")
        urwid.WidgetWrap.__init__(self, self.filler)


    def keypress(self, size, key):
        if key == "up":
            self.app.ui.main_display.frame.set_focus("header")
            
        return super(ConfigFiller, self).keypress(size, key)

class ConfigDisplay():
    def __init__(self, app):
        import urwid
        self.app = app

        def open_editor(sender):
            self.editor_term = EditorTerminal(self.app, self)
            self.widget = urwid.LineBox(self.editor_term)
            self.app.ui.main_display.update_active_sub_display()
            self.app.ui.main_display.frame.set_focus("body")
            self.editor_term.term.change_focus(True)

        pile = urwid.Pile([
            urwid.Text(("body_text", "\nTo change the configuration, edit the config file located at:\n\n"+self.app.configpath+"\n\nRestart Nomad Network for changes to take effect\n"), align="center"),
            urwid.Padding(urwid.Button("Open Editor", on_press=open_editor), width=15, align="center"),
        ])

        self.config_explainer = ConfigFiller(pile, self.app)
        self.shortcuts_display = ConfigDisplayShortcuts(self.app)
        self.widget = self.config_explainer

    def shortcuts(self):
        return self.shortcuts_display

class EditorTerminal(urwid.WidgetWrap):
    def __init__(self, app, parent):
        self.app = app
        self.parent = parent
        editor_cmd = self.app.config["textui"]["editor"]

        # The "editor" alias is unavailable on Darwin,
        # so we replace it with nano.
        if platform.system() == "Darwin" and editor_cmd == "editor":
            editor_cmd = "nano"

        self.term = urwid.Terminal(
            (editor_cmd, self.app.configpath),
            encoding='utf-8',
            main_loop=self.app.ui.loop,
        )

        def quit_term(*args, **kwargs):
            self.parent.widget = self.parent.config_explainer
            self.app.ui.main_display.update_active_sub_display()
            self.app.ui.main_display.show_config(None)
            self.app.ui.main_display.request_redraw()

        urwid.connect_signal(self.term, 'closed', quit_term)

        urwid.WidgetWrap.__init__(self, self.term)


    def keypress(self, size, key):
        # TODO: Decide whether there should be a way to get out while editing
        #if key == "up":
        #    nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.set_focus("header")   
        return super(EditorTerminal, self).keypress(size, key)