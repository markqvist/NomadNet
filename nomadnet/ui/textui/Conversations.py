class ConversationsDisplayShortcuts():
    def __init__(self, app):
        import urwid
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("Conversations Display Shortcuts"), "shortcutbar")

class ConversationsDisplay():
    def __init__(self, app):
        import urwid
        self.app = app

        pile = urwid.Pile([
            urwid.Text(("body_text", "Conversations Display \U0001F332")),
        ])

        self.shortcuts_display = ConversationsDisplayShortcuts(self.app)
        self.widget = urwid.Filler(pile, 'top')

    def shortcuts(self):
        return self.shortcuts_display