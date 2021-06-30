class ConfigDisplayShortcuts():
    def __init__(self, app):
        import urwid
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("Config Display Shortcuts"), "shortcutbar")

class ConfigDisplay():
    def __init__(self, app):
        import urwid
        self.app = app

        pile = urwid.Pile([
            urwid.Text(("body_text", "Config Display \U0001F332")),
        ])

        self.shortcuts_display = ConfigDisplayShortcuts(self.app)
        self.widget = urwid.Filler(pile, 'top')

    def shortcuts(self):
        return self.shortcuts_display