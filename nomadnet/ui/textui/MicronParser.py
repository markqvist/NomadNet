import nomadnet
import urwid
import re

STYLES = {
    "plain":    { "fg": "bbb", "bg": "default", "bold": False, "underline": False, "italic": False },
    "heading1": { "fg": "222", "bg": "bbb", "bold": False, "underline": False, "italic": False },
    "heading2": { "fg": "111", "bg": "999", "bold": False, "underline": False, "italic": False },
    "heading3": { "fg": "000", "bg": "777", "bold": False, "underline": False, "italic": False },
}

SYNTH_STYLES = []

SECTION_INDENT = 2
INDENT_RIGHT   = 1

def markup_to_attrmaps(markup):
    attrmaps = []

    state = {
        "literal": False,
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
                        if wanted_style in STYLES:
                            style = STYLES[wanted_style]

                line = line[state["depth"]:]
                if len(line) > 0:
                    latched_style = state_to_style(state)
                    style_to_state(style, state)

                    heading_style = make_style(state)
                    output = make_output(state, line)
                    
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

        output = make_output(state, line)

        if output != None:
            if state["depth"] == 0:
                return urwid.Text(output, align=state["align"])
            else:
                return urwid.Padding(urwid.Text(output, align=state["align"]), left=left_indent(state), right=right_indent(state))
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