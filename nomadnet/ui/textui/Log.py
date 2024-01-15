import urwid
import nomadnet

class LogDisplayShortcuts():
    def __init__(self, app):
        import urwid
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text(""), "shortcutbar")

class LogDisplay():
    def __init__(self, app):
        import urwid
        self.app = app
        self.log_term = None

        self.shortcuts_display = LogDisplayShortcuts(self.app)
        self.widget = None

    def show(self):
        if self.log_term == None:
            self.log_term = LogTerminal(self.app)
            self.widget = urwid.LineBox(self.log_term)

    def kill(self):
        if self.log_term != None:
            self.log_term.terminate()
            self.log_term = None
            self.widget = None
        
    def shortcuts(self):
        return self.shortcuts_display

class LogTerminal(urwid.WidgetWrap):
    def __init__(self, app):
        self.app = app
        self.log_term = urwid.Terminal(
            ("tail", "-fn50", self.app.logfilepath),
            encoding='utf-8',
            escape_sequence="up",
            main_loop=self.app.ui.loop,
        )
        urwid.WidgetWrap.__init__(self, self.log_term)

    def terminate(self):
        self.log_term.terminate()


    def keypress(self, size, key):
        if key == "up":
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.set_focus("header")
            
        return super(LogTerminal, self).keypress(size, key)