class MapDisplayShortcuts():
    def __init__(self, app):
        import urwid
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("Map Display Shortcuts"), "shortcutbar")

class MapDisplay():
    def __init__(self, app):
        import urwid
        self.app = app

        pile = urwid.Pile([
            urwid.Text(("body_text", "Map Display \U0001F332")),
        ])

        self.shortcuts_display = MapDisplayShortcuts(self.app)
        self.widget = urwid.Filler(pile, 'top')

    def shortcuts(self):
        return self.shortcuts_display