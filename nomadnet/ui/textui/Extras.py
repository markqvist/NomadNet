class IntroDisplay():
    def __init__(self, app):
        import urwid
        self.app = app

        font = urwid.font.HalfBlock5x4Font()

        big_text = urwid.BigText(("intro_title", self.app.config["textui"]["intro_text"]), font)
        big_text = urwid.Padding(big_text, align="center", width="clip")

        intro = urwid.Pile([
            big_text,
            urwid.Text(("Version %s" % (str(self.app.version))), align="center"),
            urwid.Divider(),
            urwid.Text(("-= Starting =- "), align="center"),
        ])

        self.widget = urwid.Filler(intro)

