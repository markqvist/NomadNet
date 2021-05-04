class NetworkDisplayShortcuts():
    def __init__(self, app):
        import urwid
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("Network Display Shortcuts"), "shortcutbar")

class NetworkDisplay():
    def __init__(self, app):
        import urwid
        self.app = app

        pile = urwid.Pile([
            urwid.Text(("body_text", "Network Display \U0001F332")),
        ])

        self.shortcuts_display = NetworkDisplayShortcuts(self.app)
        self.widget = urwid.Filler(pile, 'top')

    def shortcuts(self):
        return self.shortcuts_display
