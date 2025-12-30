import nomadnet
import urwid
import random
import time
import RNS
from urwid.util import is_mouse_press
from urwid.text_layout import calc_coords

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

def default_state(fg=None, bg=None):
    if fg == None: fg = SELECTED_STYLES["plain"]["fg"]
    if bg == None: bg = DEFAULT_BG
    state = {
        "literal": False,
        "depth": 0,
        "fg_color": fg,
        "bg_color": bg,
        "formatting": {
            "bold": False,
            "underline": False,
            "italic": False,
            "strikethrough": False,
            "blink": False,
        },
        "default_align": "left",
        "align": "left",
        "default_fg": fg,
        "default_bg": bg,
    }
    return state

def markup_to_attrmaps(markup, url_delegate = None, fg_color=None, bg_color=None):
    global SELECTED_STYLES
    if nomadnet.NomadNetworkApp.get_shared_instance().config["textui"]["theme"] == nomadnet.ui.TextUI.THEME_DARK:
        SELECTED_STYLES = STYLES_DARK
    else:
        SELECTED_STYLES = STYLES_LIGHT

    attrmaps = []

    fgc = None; bgc = DEFAULT_BG
    if bg_color != None: bgc = bg_color
    if fg_color != None: fgc = fg_color

    state = default_state(fgc, bgc)

    # Split entire document into lines for
    # processing.
    lines = markup.split("\n");

    for line in lines:
        if len(line) > 0:
            display_widgets = parse_line(line, state, url_delegate)
        else:
            display_widgets = [urwid.Text("")]
        
        if display_widgets != None and len(display_widgets) != 0:
            for display_widget in display_widgets:
                attrmap = urwid.AttrMap(display_widget, make_style(state))
                attrmaps.append(attrmap)

    return attrmaps

def parse_partial(line):
    try:
        endpos = line.find("}")
        if endpos == -1: return None
        else:
            partial_data = line[0:endpos]

            partial_id = None
            partial_components = partial_data.split("`")
            if len(partial_components) == 1:
                partial_url = partial_components[0]
                partial_refresh = None
                partial_fields = ""
            elif len(partial_components) == 2:
                partial_url = partial_components[0]
                partial_refresh = float(partial_components[1])
                partial_fields = ""
            elif len(partial_components) == 3:
                partial_url = partial_components[0]
                partial_refresh = float(partial_components[1])
                partial_fields = partial_components[2]
            else:
                partial_url = ""
                partial_fields = ""
                partial_refresh = None

            if partial_refresh != None and partial_refresh < 1: partial_refresh = None

            pf = partial_fields.split("|")
            if len(pf) > 0:
                partial_fields = pf
                for f in pf:
                    if f.startswith("pid="):
                        pcs = f.split("=")
                        partial_id = pcs[1]

            if len(partial_url):
                pile = urwid.Pile([urwid.Text(f"⧖")])
                partial_descriptor = "|".join(partial_components)
                pile.partial_id = partial_id
                pile.partial_hash = RNS.hexrep(RNS.Identity.full_hash(partial_descriptor.encode("utf-8")), delimit=False)
                pile.partial_url = partial_url
                pile.partial_fields = partial_fields
                pile.partial_refresh = partial_refresh
                return [pile]

    except Exception as e: return None

def parse_line(line, state, url_delegate):
    pre_escape = False
    if len(line) > 0:
        first_char = line[0]

        # Check for literals
        if len(line) == 2 and line == "`=":
            state["literal"] ^= True
            return None

        # Only parse content if not in literal state
        if not state["literal"]:
            # Apply markup sanitization
            if first_char == ">" and "`<" in line:
                # Remove heading status from lines containing fields
                line = line.lstrip(">")
                first_char = line[0]

            # Check if the command is an escape
            if first_char == "\\":
                line = line[1:]
                pre_escape = True

            # Check for comments
            elif first_char == "#":
                return None

            # Check for partials
            elif line.startswith("`{"):
                return parse_partial(line[2:])

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
                        return [urwid.AttrMap(urwid.Text(output, align=state["align"]), heading_style)]
                    else:
                        return None
                else:
                    return None

            # Check for horizontal dividers
            elif first_char == "-":
                if len(line) == 2:
                    divider_char = line[1]
                    # Control characters don't make sense here and otherwise crash nomadnet
                    if ord(divider_char) < 32:
                        divider_char = "\u2500"
                else:
                    divider_char = "\u2500"
                if state["depth"] == 0:
                    return [urwid.Divider(divider_char)]
                else:
                    return [urwid.Padding(urwid.Divider(divider_char), left=left_indent(state), right=right_indent(state))]

        output = make_output(state, line, url_delegate, pre_escape)

        if output != None:
            text_only = True
            for o in output:
                if not isinstance(o, tuple):
                    text_only = False
                    break

            if not text_only:
                widgets = []
                for o in output:
                    if isinstance(o, tuple):
                        if url_delegate != None:
                            tw = LinkableText(o, align=state["align"], delegate=url_delegate)
                            tw.in_columns = True
                        else:
                            tw = urwid.Text(o, align=state["align"])
                        widgets.append((urwid.PACK, tw))
                    else:
                        if o["type"] == "field":
                            fw = o["width"]
                            fd = o["data"]
                            fn = o["name"]
                            fs = o["style"]
                            fmask = "*" if o["masked"] else None
                            f = urwid.Edit(caption="", edit_text=fd, align=state["align"], multiline=True, mask=fmask)
                            f.field_name = fn
                            fa = urwid.AttrMap(f, fs)
                            widgets.append((fw, fa))
                        elif o["type"] == "checkbox":
                            fn = o["name"]
                            fv = o["value"]
                            flabel = o["label"]
                            fs = o["style"]
                            fprechecked = o.get("prechecked", False)  
                            f = urwid.CheckBox(flabel, state=fprechecked)
                            f.field_name = fn
                            f.field_value = fv
                            fa = urwid.AttrMap(f, fs)
                            widgets.append((urwid.PACK, fa))
                        elif o["type"] == "radio":
                            fn = o["name"]
                            fv = o["value"]
                            flabel = o["label"]
                            fs = o["style"]
                            fprechecked = o.get("prechecked", False)  
                            if "radio_groups" not in state:
                                state["radio_groups"] = {}
                            if fn not in state["radio_groups"]:
                                state["radio_groups"][fn] = []
                            group = state["radio_groups"][fn]
                            f = urwid.RadioButton(group, flabel, state=fprechecked, user_data=fv)
                            f.field_name = fn
                            f.field_value = fv
                            fa = urwid.AttrMap(f, fs)
                            widgets.append((urwid.PACK, fa))




                columns_widget = urwid.Columns(widgets, dividechars=0)
                text_widget = columns_widget
                # text_widget = urwid.Text("<"+output+">", align=state["align"])

            else:
                if url_delegate != None:
                    text_widget = LinkableText(output, align=state["align"], delegate=url_delegate)
                else:
                    text_widget = urwid.Text(output, align=state["align"])

            if state["depth"] == 0:
                return [text_widget]
            else:
                return [urwid.Padding(text_widget, left=left_indent(state), right=right_indent(state))]
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
        try:
            result = "default"
            if color == "default":
                result = "default"

            elif len(color) == 6:
                r = str(color[0])
                g = str(color[2])
                b = str(color[4])
                color = r+g+b

            if len(color) == 3:
                t = 7

                if color[0] == "g":
                    val = int(color[1:2])
                    if val < 25:   result = "black"
                    elif val < 50: result = "dark gray"
                    elif val < 75: result = "light gray"
                    else:          result = "white"
                
                else:
                    r = int(color[0], 16)
                    g = int(color[1], 16)
                    b = int(color[2], 16)

                    if r == g == b:
                        val = int(color[0], 16)*6
                        if val < 12:   result = "black"
                        elif val < 50: result = "dark gray"
                        elif val < 80: result = "light gray"
                        else:          result = "white"

                    else:
                        if r == b:
                            if r > g:
                                if r > t: result = "light magenta"
                                else:     result = "dark magenta"
                            else:
                                if g > t: result = "light green"
                                else:     result = "dark green"
                        if b == g:
                            if b > r:
                                if b > t: result = "light cyan"
                                else:     result = "dark cyan"
                            else:
                                if r > t: result = "light red"
                                else:     result = "dark red"
                        if g == r:
                            if g > b:
                                if g > t: result = "yellow"
                                else:     result = "brown"
                            else:
                                if b > t: result = "light blue"
                                else:     result = "dark blue"

                        if r > g and r > b:
                            if r > t: result = "light red"
                            else:     result = "dark red"
                        if g > r and g > b:
                            if g > t: result = "light green"
                            else:     result = "dark green"
                        if b > g and b > r:
                            if b > t: result = "light blue"
                            else:     result = "dark blue"

        except Exception as e:
            result = "default"

        return result

    def high_color(color):
        def parseval_hex(char):
            return hex(max(0,min(int(char, 16),16)))[2:]

        def parseval_dec(char):
            return str(max(0,min(int(char), 9)))

        if color == "default":
            return "default"
        else:
            if len(color) == 6:
                try:
                    v1 = parseval_hex(color[0])
                    v2 = parseval_hex(color[1])
                    v3 = parseval_hex(color[2])
                    v4 = parseval_hex(color[3])
                    v5 = parseval_hex(color[4])
                    v6 = parseval_hex(color[5])
                    color = "#"+v1+v2+v3+v4+v5+v6

                except Exception as e:
                    return "default"

                return color

            elif len(color) == 3:
                if color[0] == "g":
                    try:
                        v1 = parseval_dec(color[1])
                        v2 = parseval_dec(color[2])

                    except Exception as e:
                        return "default"

                    return "g"+v1+v2
                
                else:
                    try:
                        v1 = parseval_hex(color[0])
                        v2 = parseval_hex(color[1])
                        v3 = parseval_hex(color[2])
                        color = v1+v2+v3
                        
                    except Exception as e:
                        return "default"

                    r = color[0]
                    g = color[1]
                    b = color[2]
                    return "#"+r+r+g+g+b+b


    bold      = state["formatting"]["bold"]
    underline = state["formatting"]["underline"]
    italic    = state["formatting"]["italic"]
    fg        = state["fg_color"]
    bg        = state["bg_color"]

    format_string = ""
    if bold:      format_string += ",bold"
    if underline: format_string += ",underline"
    if italic:    format_string += ",italics"

    name = "micron_"+fg+"_"+bg+"_"+format_string
    if not name in SYNTH_STYLES:
        screen = nomadnet.NomadNetworkApp.get_shared_instance().ui.screen
        screen.register_palette_entry(name, low_color(fg)+format_string,low_color(bg),mono_color(fg, bg)+format_string,high_color(fg)+format_string,high_color(bg))
        
        synth_spec = screen._palette[name]
        SYNTH_STYLES.append(name)
        if not name in SYNTH_SPECS:
            SYNTH_SPECS[name] = synth_spec

    return name

def make_output(state, line, url_delegate, pre_escape=False):
    output = []
    if state["literal"]:
        if line == "\\`=":
            line = "`="
        output.append(make_part(state, line))
    else:
        part = ""
        mode = "text"
        escape = pre_escape
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
                        state["fg_color"] = state["default_fg"]
                    elif c == "B":
                        if len(line) >= i+4:
                            color = line[i+1:i+4]
                            state["bg_color"] = color
                            skip = 3
                    elif c == "b":
                        state["bg_color"] = state["default_bg"]
                    elif c == "`":
                        state["formatting"]["bold"]      = False 
                        state["formatting"]["underline"] = False
                        state["formatting"]["italic"]    = False
                        state["fg_color"] = state["default_fg"]
                        state["bg_color"] = state["default_bg"]
                        state["align"] = state["default_align"]
                    elif c == "c":
                        if state["align"] != "center": state["align"] = "center"
                    elif c == "l":
                        if state["align"] != "left": state["align"] = "left"
                    elif c == "r":
                        if state["align"] != "right": state["align"] = "right"
                    elif c == "a":
                        state["align"] = state["default_align"]

                    elif c == '<':
                        if len(part) > 0:
                            output.append(make_part(state, part))
                            part = ""
                        try:
                            field_start = i + 1  # position after '<'
                            backtick_pos = line.find('`', field_start)
                            if backtick_pos == -1:
                                pass  # No '`', invalid field
                            else:
                                field_content = line[field_start:backtick_pos]
                                field_masked = False
                                field_width = 24
                                field_type = "field"
                                field_name = field_content
                                field_value = ""
                                field_data = ""
                                field_prechecked = False  

                                # check if field_content contains '|'
                                if '|' in field_content:
                                    f_components = field_content.split('|')
                                    field_flags = f_components[0]
                                    field_name = f_components[1]

                                    # handle field type indicators
                                    if '^' in field_flags:
                                        field_type = "radio"
                                        field_flags = field_flags.replace("^", "")
                                    elif '?' in field_flags:
                                        field_type = "checkbox"
                                        field_flags = field_flags.replace("?", "")
                                    elif '!' in field_flags:
                                        field_flags = field_flags.replace("!", "")
                                        field_masked = True

                                    # Handle field width
                                    if len(field_flags) > 0:
                                        try:
                                            field_width = min(int(field_flags), 256)
                                        except ValueError:
                                            pass  # Ignore invalid width

                                    # Check for value and pre-checked flag
                                    if len(f_components) > 2:
                                        field_value = f_components[2]
                                    else:
                                        field_value = ""
                                    if len(f_components) > 3:
                                        if f_components[3] == '*':
                                            field_prechecked = True

                                else:
                                    # No '|', so field_name is field_content
                                    field_name = field_content
                                    field_type = "field"
                                    field_masked = False
                                    field_width = 24
                                    field_value = ""
                                    field_prechecked = False

                                # Find the closing '>' character
                                field_end = line.find('>', backtick_pos)
                                if field_end == -1:
                                    pass  # No closing '>', invalid field
                                else:
                                    field_data = line[backtick_pos+1:field_end]

                                    # Now, we have all field data
                                    if field_type in ["checkbox", "radio"]:
                                        # for checkboxes and radios, field_data is the label
                                        output.append({
                                            "type": field_type,
                                            "name": field_name,
                                            "value": field_value if field_value else field_data,
                                            "label": field_data,
                                            "prechecked": field_prechecked,
                                            "style": make_style(state)
                                        })
                                    else:
                                        # For text fields field_data is the initial text
                                        output.append({
                                            "type": "field",
                                            "name": field_name,
                                            "width": field_width,
                                            "masked": field_masked,
                                            "data": field_data,
                                            "style": make_style(state)
                                        })
                                    skip = field_end - i
                        except Exception as e:
                            pass

                    
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
                                link_fields = ""
                                link_url = link_data
                            elif len(link_components) == 2:
                                link_label = link_components[0]
                                link_url = link_components[1]
                                link_fields = ""
                            elif len(link_components) == 3:
                                link_label = link_components[0]
                                link_url = link_components[1]
                                link_fields = link_components[2]
                            else:
                                link_url = ""
                                link_label = ""
                                link_fields = ""

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
                                    linkspec = LinkSpec(link_url, orig_spec, cm=cm)
                                    if link_fields != "":
                                        lf = link_fields.split("|")
                                        if len(lf) > 0:
                                            linkspec.link_fields = lf

                                    output.append((linkspec, link_label))
                                else:
                                    output.append(make_part(state, link_label))

                    mode = "text"
                    if len(part) > 0:
                        output.append(make_part(state, part))

                elif mode == "text":
                    if c == "\\":
                        if escape:
                            part += c
                            escape = False
                        else:
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
                        escape = False

            if i == len(line)-1:
                if len(part) > 0:
                    output.append(make_part(state, part))

    if len(output) > 0:
        return output
    else:
        return None


class LinkSpec(urwid.AttrSpec):
    def __init__(self, link_target, orig_spec, cm=256):
        self.link_target = link_target
        self.link_fields = None

        super().__init__(orig_spec.foreground, orig_spec.background, colors=cm)


class LinkableText(urwid.Text):
    ignore_focus = False
    _selectable = True

    signals = ["click", "change"]

    def __init__(self, text, align=None, cursor_position=0, delegate=None):
        super().__init__(text, align=align)
        self.delegate = delegate
        self._cursor_position = 0
        self.key_timeout = 3
        self.in_columns = False
        if self.delegate != None:
            self.delegate.last_keypress = 0

    def handle_link(self, link_target, link_fields):
        if self.delegate != None:
            self.delegate.handle_link(link_target, link_fields)

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
                    self.handle_link(item.link_target, item.link_fields)

        elif key == "up":
            self._cursor_position = 0
            return key
        
        elif key == "down":
            self._cursor_position = 0
            return key
        
        elif key == "right":
            old = self._cursor_position
            self._cursor_position = self.find_next_part_pos(self._cursor_position, part_positions)

            if self._cursor_position == old:
                if self.in_columns:
                    return "right"
                else:
                    self._cursor_position = 0
                    return "down"

            self._invalidate()
        
        elif key == "left":
            if self._cursor_position > 0:
                if self.in_columns:
                    return "left"
                else:
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
        c = super().render(size, focus)

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
        try:
            if button != 1 or not is_mouse_press(event):
                return False
            else:
                (maxcol,) = size
                translation = self.get_line_translation(maxcol)
                line_offset = 0

                if self.align == "center":
                    line_offset = translation[y][1][1]-translation[y][0][0]
                    if x < translation[y][0][0]:
                        x = translation[y][0][0]

                    if x > translation[y][1][0]+translation[y][0][0]:
                        x = translation[y][1][0]+translation[y][0][0]

                elif self.align == "right":
                    line_offset = translation[y][1][1]-translation[y][0][0]
                    if x < translation[y][0][0]:
                        x = translation[y][0][0]

                else:
                    line_offset = translation[y][0][1]
                    if x > translation[y][0][0]:
                        x = translation[y][0][0]

                pos = line_offset+x

                self._cursor_position = pos
                item = self.find_item_at_pos(self._cursor_position)

                if item != None:
                    if isinstance(item, LinkSpec):
                        self.handle_link(item.link_target, item.link_fields)

                self._invalidate()
                self._emit("change")
                
                return True
            
        except Exception as e:
            return False