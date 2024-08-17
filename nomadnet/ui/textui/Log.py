import os
import sys
import itertools
import mmap
import urwid
import nomadnet


class LogDisplayShortcuts():
    def __init__(self, app):
        import urwid
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text(""), "shortcutbar")


class LogDisplay():
    def __init__(self, app):
        self.app = app

        self.shortcuts_display = LogDisplayShortcuts(self.app)
        self.widget = None

    @property
    def log_term(self):
        return self.widget

    def show(self):
        if self.widget is None:
            self.widget = log_widget(self.app)

    def kill(self):
        if self.widget is not None:
            self.widget.terminate()
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
        self.widget = urwid.LineBox(self.log_term)
        super().__init__(self.widget)

    def terminate(self):
        self.log_term.terminate()


    def keypress(self, size, key):
        if key == "up":
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.focus_position = "header"
            
        return super(LogTerminal, self).keypress(size, key)


class LogTail(urwid.WidgetWrap):
    def __init__(self, app):
        self.app = app
        self.log_tail = urwid.Text(tail(self.app.logfilepath, 50))
        self.log = urwid.Scrollable(self.log_tail)
        self.log.set_scrollpos(-1)
        self.log_scrollbar = urwid.ScrollBar(self.log)
        # We have this here because ui.textui.Main depends on this field to kill it
        self.log_term = None

        super().__init__(self.log_scrollbar)

    def terminate(self):
        pass


def log_widget(app, platform=sys.platform):
    if platform == "win32":
        return LogTail(app)
    else:
        return LogTerminal(app)

# https://stackoverflow.com/a/34029605/3713120
def _tail(f_name, n, offset=0):
    def skip_back_lines(mm: mmap.mmap, numlines: int, startidx: int) -> int:
        '''Factored out to simplify handling of n and offset'''
        for _ in itertools.repeat(None, numlines):
            startidx = mm.rfind(b'\n', 0, startidx)
            if startidx < 0:
                break
        return startidx

    # Open file in binary mode
    with open(f_name, 'rb') as binf, mmap.mmap(binf.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        # len(mm) - 1 handles files ending w/newline by getting the prior line
        startofline = skip_back_lines(mm, offset, len(mm) - 1)
        if startofline < 0:
            return []  # Offset lines consumed whole file, nothing to return
            # If using a generator function (yield-ing, see below),
            # this should be a plain return, no empty list

        endoflines = startofline + 1  # Slice end to omit offset lines

        # Find start of lines to capture (add 1 to move from newline to beginning of following line)
        startofline = skip_back_lines(mm, n, startofline) + 1

        # Passing True to splitlines makes it return the list of lines without
        # removing the trailing newline (if any), so list mimics f.readlines()
        # return mm[startofline:endoflines].splitlines(True)
        # If Windows style \r\n newlines need to be normalized to \n
        return mm[startofline:endoflines].replace(os.linesep.encode(sys.getdefaultencoding()), b'\n').splitlines(True)


def tail(f_name, n):
    """
    Return the last n lines of a given file name, f_name.
    Akin to `tail -<n> <f_name>`
    """
    def decode(b):
        return b.decode(encoding)

    encoding = sys.getdefaultencoding()
    lines = map(decode, _tail(f_name=f_name, n=n))
    return ''.join(lines)
