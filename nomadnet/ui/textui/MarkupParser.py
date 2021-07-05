import nomadnet
import urwid
import re

URWID_THEME = [
    # Style name       16-color style                    Monochrome style          # 88, 256 and true-color style
    ('plain',          'light gray', 'default',          'default',                '#ddd', 'default'),
    ('heading1',       'black', 'light gray',            'standout',               '#222', '#bbb'),
    ('heading2',       'black', 'light gray',            'standout',               '#111', '#999'),
    ('heading3',       'black', 'light gray',            'standout',               '#000', '#777'),
    ('f_underline',    'default,underline', 'default',   'default,underline',      'default,underline', 'default'),
    ('f_bold',         'default,bold', 'default',        'default,bold',           'default,bold', 'default'),
    ('f_italic',       'default,italics', 'default',     'default,italics',        'default,italics', 'default'),
]

SYNTH_STYLES = []

SECTION_INDENT = 2
INDENT_RIGHT   = 1

def markup_to_attrmaps(markup):
    attrmaps = []

    state = {
        "depth": 0,
        "fg_color": "default",
        "bg_color": "default",
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
            display_widget = parse_line(line, state)
        else:
            display_widget = urwid.Text("")
        
        if display_widget != None:
            attrmap = urwid.AttrMap(display_widget, make_style(state))
            attrmaps.append(attrmap)

    return attrmaps


def parse_line(line, state):
    first_char = line[0]

    # Check if the command is an escape
    if first_char == "\\":
        line = line[1:]

    # Check for section heading reset
    elif first_char == "<":
        state["depth"] = 0
        return parse_line(line[1:], state)

    # Check for section headings
    elif first_char == ">":
        i = 0
        while i < len(line) and line[i] == ">":
            i += 1
            state["depth"] = i
        
            for j in range(1, i+1):
                wanted_style = "heading"+str(i)
                if any(s[0]==wanted_style for s in URWID_THEME):
                    style = wanted_style

        line = line[state["depth"]:]
        if len(line) > 0:
            line = " "*left_indent(state)+line
            return urwid.AttrMap(urwid.Text(line), style)
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

    output = make_output(state, line)

    if output != None:
        if state["depth"] == 0:
            return urwid.Text(output, align=state["align"])
        else:
            return urwid.Padding(urwid.Text(output, align=state["align"]), left=left_indent(state), right=right_indent(state))
    else:
        return None

def left_indent(state):
    return (state["depth"]-1)*SECTION_INDENT

def right_indent(state):
    return (state["depth"]-1)*SECTION_INDENT

def make_part(state, part):
    return (make_style(state), part)

def make_style(state):
    def mono_color(fg, bg):
        return "default"
    def low_color(color):
        # TODO: Implement
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
        SYNTH_STYLES.append(name)

    return name

def make_output(state, line):
    output = []
    part = ""
    mode = "text"
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
                    if len(line) > i+4:
                        color = line[i+1:i+4]
                        state["fg_color"] = color
                        skip = 3
                elif c == "f":
                    state["fg_color"] = "default"
                elif c == "B":
                    if len(line) >= i+4:
                        color = line[i+1:i+4]
                        state["bg_color"] = color
                        skip = 3
                elif c == "b":
                    state["bg_color"] = "default"
                elif c == "`":
                    state["formatting"]["bold"]      = False 
                    state["formatting"]["underline"] = False
                    state["formatting"]["italic"]    = False
                    state["fg_color"] = "default"
                    state["bg_color"] = "default"
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

                mode = "text"
                if len(part) > 0:
                    output.append(make_part(state, part))

            elif mode == "text":
                if c == "`":
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