class IntroDisplay():
    def __init__(self, app):
        import urwid
        self.app = app

        font = urwid.font.HalfBlock5x4Font()

        big_text = urwid.BigText(("intro_title", "Nomad Network"), font)
        big_text = urwid.Padding(big_text, align="center", width="clip")

        intro = urwid.Pile([
            big_text,
            urwid.Text(("Version %s" % (str(self.app.version))), align="center"),
            urwid.Divider(),
            urwid.Text(("-= Starting =- "), align="center"),
        ])

        self.widget = urwid.Filler(intro)


class DemoDisplay():
    def __init__(self, ui, app):
        import urwid

        def color_mono(btn):
            ui.set_colormode(nomadnet.ui.COLORMODE_MONO)

        def color_16(btn):
            ui.set_colormode(nomadnet.ui.COLORMODE_16)

        def color_88(btn):
            ui.set_colormode(nomadnet.ui.COLORMODE_88)

        def color_8bit(btn):
            ui.set_colormode(nomadnet.ui.COLORMODE_256)

        def color_true(btn):
            ui.set_colormode(nomadnet.ui.COLORMODE_TRUE)

        # pile = urwid.Pile([
        #     urwid.Text(("heading", "This is a heading")),
        #     urwid.Text(("body_text", "Hello World \U0001F332")),
        #     urwid.Button(("buttons", "Monochrome"), color_mono),
        #     urwid.Button(("buttons", "16 color"), color_16),
        #     urwid.Button(("buttons", "88 color"), color_88),
        #     urwid.Button(("buttons", "256 color"), color_8bit),
        #     urwid.Button(("buttons", "True color"), color_true),
        # ])

        gf = urwid.GridFlow([
            urwid.Text(("heading", "This is a heading")),
            urwid.Text(("body_text", "Hello World \U0001F332")),
            urwid.Button(("buttons", "Monochrome"), color_mono),
            urwid.Button(("buttons", "16 color"), color_16),
            urwid.Button(("buttons", "88 color"), color_88),
            urwid.Button(("buttons", "256 color"), color_8bit),
            urwid.Button(("buttons", "True color"), color_true),
        ], cell_width=20, h_sep=0, v_sep=0, align="left")

        self.widget = urwid.Filler(urwid.Padding((urwid.Text("Test"),urwid.Text("Test 2"))), 'top')
        #self.widget = urwid.Filler(pile, 'top')