class DirectoryDisplayShortcuts():
    def __init__(self, app):
        import urwid
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("Directory Display Shortcuts"), "shortcutbar")

class DirectoryDisplay():
    def __init__(self, app):
        import urwid
        self.app = app

        pile = urwid.Pile([
            urwid.Text(("body_text", "Directory Display \U0001F332")),
        ])

        self.shortcuts_display = DirectoryDisplayShortcuts(self.app)
        self.widget = urwid.Filler(pile, 'top')

    def shortcuts(self):
        return self.shortcuts_display