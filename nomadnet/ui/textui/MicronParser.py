import nomadnet
import urwid
import time
from urwid.util import is_mouse_press
from urwid.text_layout import calc_coords
import re

DEFAULT_FG_DARK  = "ddd"
DEFAULT_FG_LIGHT = "222"
DEFAULT_BG = "default"

SELECTED_STYLES = None

STYLES_DARK = {
    "plain":    { "fg": DEFAULT_FG_DARK, "bg": DEFAULT_BG, "bold": False, "underline": False, "italic": False },
    "heading1": { "fg": "222", "bg": "bbb", "bold": False, "underline": False, "italic": False },
    "heading2": { "fg": "111", "bg": "999", "bold": False, "underline": False, "italic": False },
    "heading3": { "fg": "000", "bg": "777", "bold": False, "underline": False, "italic": False },
}

STYLES_LIGHT = {
    "plain":    { "fg": DEFAULT_FG_LIGHT, "bg": DEFAULT_BG, "bold": False, "underline": False, "italic": False },
    "heading1": { "fg": "000", "bg": "777", "bold": False, "underline": False, "italic": False },
    "heading2": { "fg": "111", "bg": "aaa", "bold": False, "underline": False, "italic": False },
    "heading3": { "fg": "222", "bg": "ccc", "bold": False, "underline": False, "italic": False },
}

SYNTH_STYLES = []
SYNTH_SPECS  = {}

SECTION_INDENT = 2
INDENT_RIGHT   = 1

def markup_to_attrmaps(markup, url_delegate = None):
    global SELECTED_STYLES
    if nomadnet.NomadNetworkApp.get_shared_instance().config["textui"]["theme"] == nomadnet.ui.TextUI.THEME_DARK:
        SELECTED_STYLES = STYLES_DARK
    else:
        SELECTED_STYLES = STYLES_LIGHT

    attrmaps = []

    state = {
        "literal": False,
        "depth": 0,
        "fg_color": SELECTED_STYLES["plain"]["fg"],
        "bg_color": DEFAULT_BG,
        "formatting": {
            "bold": False,
            "underline": False,
            "italic": False,
            "strikethrough": False,
            "blink": False,
        },
        "default_align": "left",
        "align": "left",
    }

    # Split entire document into lines for
    # processing.
    lines = markup.split("\n");

    for line in lines:
        if len(line) > 0:
            display_widget = parse_line(line, state, url_delegate)
        else:
            display_widget = urwid.Text("")
        
        if display_widget != None:
            attrmap = urwid.AttrMap(display_widget, make_style(state))
            attrmaps.append(attrmap)

    return attrmaps


def parse_line(line, state, url_delegate):
    if len(line) > 0:
        first_char = line[0]

        # Check for literals
        if len(line) == 2 and line == "`=":
            state["literal"] ^= True
            return None

        # Only parse content if not in literal state
        if not state["literal"]:
            # Check if the command is an escape
            if first_char == "\\":
                line = line[1:]

            # Check for comments
            elif first_char == "#":
                return None

            # Check for section heading reset
            elif first_char == "<":
                state["depth"] = 0
                return parse_line(line[1:], state, url_delegate)

            # Check for section headings
            elif first_char == ">":
                i = 0
                while i < len(line) and line[i] == ">":
                    i += 1
                    state["depth"] = i
                
                    for j in range(1, i+1):
                        wanted_style = "heading"+str(i)
                        if wanted_style in SELECTED_STYLES:
                            style = SELECTED_STYLES[wanted_style]

                line = line[state["depth"]:]
                if len(line) > 0:
                    latched_style = state_to_style(state)
                    style_to_state(style, state)

                    heading_style = make_style(state)
                    output = make_output(state, line, url_delegate)
                    
                    style_to_state(latched_style, state)

                    if len(output) > 0:
                        first_style = output[0][0]

                        heading_style = first_style
                        output.insert(0, " "*left_indent(state))
                        return urwid.AttrMap(urwid.Text(output, align=state["align"]), heading_style)
                    else:
                        return None
                else:
                    return None

            # Check for horizontal dividers
            elif first_char == "-":
                if len(line) == 2:
                    divider_char = line[1]
                else:
                    divider_char = "\u2500"
                if state["depth"] == 0:
                    return urwid.Divider(divider_char)
                else:
                    return urwid.Padding(urwid.Divider(divider_char), left=left_indent(state), right=right_indent(state))

        output = make_output(state, line, url_delegate)

        if output != None:
            if url_delegate != None:
                text_widget = LinkableText(output, align=state["align"], delegate=url_delegate)
            else:
                text_widget = urwid.Text(output, align=state["align"])

            if state["depth"] == 0:
                return text_widget
            else:
                return urwid.Padding(text_widget, left=left_indent(state), right=right_indent(state))
        else:
            return None
    else:
        return None

def left_indent(state):
    return (state["depth"]-1)*SECTION_INDENT

def right_indent(state):
    return (state["depth"]-1)*SECTION_INDENT

def make_part(state, part):
    return (make_style(state), part)

def state_to_style(state):
    return { "fg": state["fg_color"], "bg": state["bg_color"], "bold": state["formatting"]["bold"], "underline": state["formatting"]["underline"], "italic": state["formatting"]["italic"] }

def style_to_state(style, state):
    if style["fg"] != None:
        state["fg_color"] = style["fg"]
    if style["bg"] != None:
        state["bg_color"] = style["bg"]
    if style["bold"] != None:
        state["formatting"]["bold"] = style["bold"]
    if style["underline"] != None:
        state["formatting"]["underline"] = style["underline"]
    if style["italic"] != None:
        state["formatting"]["italic"] = style["italic"]

def make_style(state):
    def mono_color(fg, bg):
        return "default"
    def low_color(color):
        # TODO: Implement low-color mapper
        return "default"
    def high_color(color):
        if color == "default":
            return color
        else:
            return "#"+color

    bold      = state["formatting"]["bold"]
    underline = state["formatting"]["underline"]
    italic    = state["formatting"]["italic"]
    fg        = state["fg_color"]
    bg        = state["bg_color"]

    format_string = ""
    if bold:
        format_string += ",bold"
    if underline:
        format_string += ",underline"
    if italic:
        format_string += ",italics"

    name = "micron_"+fg+"_"+bg+"_"+format_string
    if not name in SYNTH_STYLES:
        screen = nomadnet.NomadNetworkApp.get_shared_instance().ui.screen
        screen.register_palette_entry(name, low_color(fg)+format_string,low_color(bg),mono_color(fg, bg)+format_string,high_color(fg)+format_string,high_color(bg))
        
        synth_spec = screen._palette[name]
        SYNTH_STYLES.append(name)
        if not name in SYNTH_SPECS:
            SYNTH_SPECS[name] = synth_spec

    return name

def make_output(state, line, url_delegate):
    output = []
    if state["literal"]:
        if line == "\\`=":
            line = "`="
        output.append(make_part(state, line))
    else:
        part = ""
        mode = "text"
        escape = False
        skip = 0
        for i in range(0, len(line)):
            c = line[i]
            if skip > 0:
                skip -= 1
            else:
                if mode == "formatting":
                    if c == "_":
                        state["formatting"]["underline"] ^= True
                    elif c == "!":
                        state["formatting"]["bold"] ^= True
                    elif c == "*":
                        state["formatting"]["italic"] ^= True
                    elif c == "F":
                        if len(line) >= i+4:
                            color = line[i+1:i+4]
                            state["fg_color"] = color
                            skip = 3
                    elif c == "f":
                        state["fg_color"] = SELECTED_STYLES["plain"]["fg"]
                    elif c == "B":
                        if len(line) >= i+4:
                            color = line[i+1:i+4]
                            state["bg_color"] = color
                            skip = 3
                    elif c == "b":
                        state["bg_color"] = DEFAULT_BG
                    elif c == "`":
                        state["formatting"]["bold"]      = False 
                        state["formatting"]["underline"] = False
                        state["formatting"]["italic"]    = False
                        state["fg_color"] = SELECTED_STYLES["plain"]["fg"]
                        state["bg_color"] = DEFAULT_BG
                        state["align"] = state["default_align"]
                    elif c == "c":
                        if state["align"] != "center":
                            state["align"] = "center"
                        else:
                            state["align"] = state["default_align"]
                    elif c == "l":
                        if state["align"] != "left":
                            state["align"] = "left"
                        else:
                            state["align"] = state["default_align"]
                    elif c == "r":
                        if state["align"] != "right":
                            state["align"] = "right"
                        else:
                            state["align"] = state["default_align"]
                    elif c == "a":
                        state["align"] = state["default_align"]

                    elif c == "[":
                        endpos = line[i:].find("]")
                        if endpos == -1:
                            pass
                        else:
                            link_data = line[i+1:i+endpos]
                            skip = endpos

                            link_components = link_data.split("`")
                            if len(link_components) == 1:
                                link_label = ""
                                link_url = link_data
                            elif len(link_components) == 2:
                                link_label = link_components[0]
                                link_url = link_components[1]
                            else:
                                link_url = ""
                                link_label = ""

                            if len(link_url) != 0:
                                if link_label == "":
                                    link_label = link_url

                                # First generate output until now
                                if len(part) > 0:
                                    output.append(make_part(state, part))

                                cm = nomadnet.NomadNetworkApp.get_shared_instance().ui.colormode

                                specname = make_style(state)
                                speclist = SYNTH_SPECS[specname]

                                if cm == 1:
                                    orig_spec = speclist[0]
                                elif cm == 16:
                                    orig_spec = speclist[1]
                                elif cm == 88:
                                    orig_spec = speclist[2]
                                elif cm == 256:
                                    orig_spec = speclist[3]
                                elif cm == 2**24:
                                    orig_spec = speclist[4]

                                if url_delegate != None:
                                    linkspec = LinkSpec(link_url, orig_spec)
                                    output.append((linkspec, link_label))
                                else:
                                    output.append(make_part(state, link_label)) 

                                

                    mode = "text"
                    if len(part) > 0:
                        output.append(make_part(state, part))

                elif mode == "text":
                    if c == "\\":
                        escape = True
                    elif c == "`":
                        if escape:
                            part += c
                            escape = False
                        else:
                            mode = "formatting"
                            if len(part) > 0:
                                output.append(make_part(state, part))
                                part = ""
                    else:
                        part += c

            if i == len(line)-1:
                if len(part) > 0:
                    output.append(make_part(state, part))

    if len(output) > 0:
        return output
    else:
        return None


class LinkSpec(urwid.AttrSpec):
    def __init__(self, link_target, orig_spec):
        self.link_target = link_target

        urwid.AttrSpec.__init__(self, orig_spec.foreground, orig_spec.background)


class LinkableText(urwid.Text):
    ignore_focus = False
    _selectable = True

    signals = ["click", "change"]

    def __init__(self, text, align=None, cursor_position=0, delegate=None):
        self.__super.__init__(text, align=align)
        self.delegate = delegate
        self._cursor_position = 0
        self.key_timeout = 3
        if self.delegate != None:
            self.delegate.last_keypress = 0

    def handle_link(self, link_target):
        if self.delegate != None:
            self.delegate.handle_link(link_target)


    def find_next_part_pos(self, pos, part_positions):
        for position in part_positions:
            if position > pos:
                return position
        return pos

    def find_prev_part_pos(self, pos, part_positions):
        nextpos = pos
        for position in part_positions:
            if position < pos:
                nextpos = position
        return nextpos

    def find_item_at_pos(self, pos):
        total = 0
        text, parts = self.get_text()
        for i, info in enumerate(parts):
            style, length = info
            if total <= pos < length+total:
                return style

            total += length

        return None

    def peek_link(self):
        item = self.find_item_at_pos(self._cursor_position)
        if item != None:
            if isinstance(item, LinkSpec):
                if self.delegate != None:
                    self.delegate.marked_link(item.link_target)
            else:
                if self.delegate != None:
                    self.delegate.marked_link(None)


    def keypress(self, size, key):
        part_positions = [0]
        parts = []
        total = 0
        text, parts = self.get_text()
        for i, info in enumerate(parts):
            style_name, length = info
            part_positions.append(length+total)
            total += length


        if self.delegate != None:
            self.delegate.last_keypress = time.time()
            self._invalidate()
            nomadnet.NomadNetworkApp.get_shared_instance().ui.loop.set_alarm_in(self.key_timeout, self.kt_event)

        if self._command_map[key] == urwid.ACTIVATE:
            item = self.find_item_at_pos(self._cursor_position)
            if item != None:
                if isinstance(item, LinkSpec):
                    self.handle_link(item.link_target)

        elif key == "up":
            self._cursor_position = 0
            return key
        
        elif key == "down":
            self._cursor_position = 0
            return key
        
        elif key == "right":
            self._cursor_position = self.find_next_part_pos(self._cursor_position, part_positions)
            self._invalidate()
        
        elif key == "left":
            if self._cursor_position > 0:
                self._cursor_position = self.find_prev_part_pos(self._cursor_position, part_positions)
                self._invalidate()

            else:
                if self.delegate != None:
                    self.delegate.micron_released_focus()

        else:
            return key

    def kt_event(self, loop, user_data):
        self._invalidate()

    def render(self, size, focus=False):
        now = time.time()
        c = self.__super.render(size, focus)

        if focus and (self.delegate == None or now < self.delegate.last_keypress+self.key_timeout):
            c = urwid.CompositeCanvas(c)
            c.cursor = self.get_cursor_coords(size)
            if self.delegate != None:
                self.peek_link()

        return c

    def get_cursor_coords(self, size):
            if self._cursor_position > len(self.text):
                return None

            (maxcol,) = size
            trans = self.get_line_translation(maxcol)
            x, y = calc_coords(self.text, trans, self._cursor_position)
            if maxcol <= x:
                return None
            return x, y

    def mouse_event(self, size, event, button, x, y, focus):
        if button != 1 or not is_mouse_press(event):
            return False
        else:
            pos = (y * size[0]) + x
            self._cursor_position = pos
            item = self.find_item_at_pos(self._cursor_position)
            if item != None:
                if isinstance(item, LinkSpec):
                    self.handle_link(item.link_target)

            self._invalidate()
            self._emit("change")
            
            return True