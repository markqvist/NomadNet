import os
import json
import shutil
import urwid
import RNS
import nomadnet

from .ReadlineEdit import ReadlineEdit
from .Browser import Browser
from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox

PREVIEW_DELAY = 0.4
PANE_WEIGHTS  = {"files": 0.22, "editor": 0.40, "preview": 0.38}
PANE_ORDER    = ["files", "editor", "preview"]
MAX_HIGHLIGHT_CHARS = 50000
MAX_PREVIEW_CHARS    = 100000




SNIPPETS = [
    ("Heading",        ">Heading\n"),
    ("Sub-heading",    ">>Sub heading\n"),
    ("Collapsible",    "`+>Section\nbody\n<\n"),
    ("Bold",           "`!bold`!"),
    ("Italic",         "`*italic`*"),
    ("Underline",      "`_underline`_"),
    ("Foreground col", "`F00ftext`f"),
    ("Background col", "`B400text`b"),
    ("Link",           "`[label`:/page/index.mu]"),
    ("Anchor",         "`:anchor-name"),
    ("Anchor link",    "`[label`#anchor-name]"),
    ("Input field",    "`<24|name`>"),
    ("Masked field",   "`<!24|name`>"),
    ("Checkbox",       "`<?|name|value`>"),
    ("Radio",          "`<^|name|value`>"),
    ("Divider",        "-\n"),
    ("Table",          "`t\n| A | B |\n| 1 | 2 |\n`t\n"),
    ("Literal block",  "`=\nliteral text\n`=\n"),
]







EDITOR_STYLES = [
    ("editor_comment", "dark gray",          "default", None, "#888", "default"),
    ("editor_heading", "light cyan,bold",    "default", None, "#0cc", "default"),
    ("editor_tag",     "light magenta",      "default", None, "#c6c", "default"),
    ("editor_field",   "yellow",             "default", None, "#cc0", "default"),
    ("editor_link",    "light green",        "default", None, "#0c6", "default"),
    ("editor_dir",     "light blue,bold",    "default", None, "#39f", "default"),
    ("editor_exec",    "dark gray",          "default", None, "#666", "default"),
    ("editor_lineno",  "dark gray",          "default", None, "#555", "default"),
]


def is_executable(path):
    try:
        return (not RNS.vendor.platformutils.is_windows()) and os.path.isfile(path) and os.access(path, os.X_OK)
    except Exception:
        return False


def _scan_tag(text, i, n):
    # text[i] == "`"; return (end_index, attr)
    if i + 1 >= n:
        return i + 1, "editor_tag"
    c = text[i + 1]
    if c == "<":
        j = text.find(">", i + 2); return (n if j < 0 else j + 1), "editor_field"
    if c == "[":
        j = text.find("]", i + 2); return (n if j < 0 else j + 1), "editor_link"
    if c == "{":
        j = text.find("}", i + 2); return (n if j < 0 else j + 1), "editor_link"
    if c in "FB":
        if i + 2 < n and text[i + 2] == "T":
            return min(i + 9, n), "editor_tag"
        return min(i + 5, n), "editor_tag"
    if c == ":":
        j = i + 2
        while j < n and (text[j].isalnum() or text[j] in "_-"):
            j += 1
        return j, "editor_tag"
    return i + 2, "editor_tag"


def highlight_micron(text):
    n = len(text)
    attrs = [None] * n
    i = 0
    line_start = True
    while i < n:
        c = text[i]
        if line_start and c == "#":
            j = text.find("\n", i); j = n if j < 0 else j
            for k in range(i, j): attrs[k] = "editor_comment"
            i = j; continue
        if line_start and c == ">":
            j = i
            while j < n and text[j] == ">": j += 1
            for k in range(i, j): attrs[k] = "editor_heading"
            i = j; line_start = False; continue
        if line_start and c == "`" and i + 2 < n and text[i + 1] in "+-" and text[i + 2] == ">":
            j = i + 2
            while j < n and text[j] == ">": j += 1
            for k in range(i, j): attrs[k] = "editor_heading"
            i = j; line_start = False; continue
        if c == "\n":
            i += 1; line_start = True; continue
        if c == "\\" and i + 1 < n:
            i += 2; line_start = False; continue
        if c == "`":
            j, attr = _scan_tag(text, i, n)
            for k in range(i, min(j, n)): attrs[k] = attr
            i = j; line_start = False; continue
        i += 1; line_start = False

    out = []
    run_attr = attrs[0] if n else None
    run_len = 0
    for a in attrs:
        if a == run_attr:
            run_len += 1
        else:

            out.append((run_attr, run_len)); run_attr = a; run_len = 1
    if run_len:
        out.append((run_attr, run_len))
    return out


class MicronEdit(ReadlineEdit):
    def __init__(self, *args, **kwargs):
        self._hl_text = None
        self._hl_attrib = []
        super().__init__(*args, **kwargs)

    def get_text(self):
        text = self.caption + self.edit_text
        if text != self._hl_text:
            self._hl_text = text
            self._hl_attrib = [] if len(text) > MAX_HIGHLIGHT_CHARS else highlight_micron(text)
        return text, self._hl_attrib


class GutterEdit(MicronEdit):
    # MicronEdit with a wrap-aware line-number gutter on the left
    def _gutter_width(self, maxcol):
        gw = max(3, len(str(self.edit_text.count("\n") + 1)) + 2)
        if maxcol - gw < 1:
            return 0
        return gw

    def rows(self, size, focus=False):
        gw = self._gutter_width(size[0])
        return super().rows((max(1, size[0] - gw),), focus)

    def get_cursor_coords(self, size):
        gw = self._gutter_width(size[0])
        coords = super().get_cursor_coords((max(1, size[0] - gw),))
        if coords is None:
            return None
        return coords[0] + gw, coords[1]

    def move_cursor_to_coords(self, size, x, y):
        gw = self._gutter_width(size[0])
        if isinstance(x, int):
            x = max(0, x - gw)
        return super().move_cursor_to_coords((max(1, size[0] - gw),), x, y)

    def render(self, size, focus=False):
        maxcol = size[0]
        gw = self._gutter_width(maxcol)
        if gw == 0:
            return super().render(size, focus)
        tw = max(1, maxcol - gw)

        cheap = len(self.edit_text) > MAX_HIGHLIGHT_CHARS
        wrap = "any" if cheap else "space"
        if self.wrap != wrap:
            self.set_wrap_mode(wrap)

        edit_canv = super().render((tw,), focus=False)
        h = edit_canv.rows()
        rows = []
        for i, line in enumerate(self.edit_text.split("\n"), 1):
            rows.append(str(i).rjust(gw - 1) + " ")
            if cheap:
                wrapped = max(1, (len(line) + tw - 1) // tw)
            else:
                wrapped = max(1, urwid.Text(line).rows((tw,)))
            rows.extend([""] * (wrapped - 1))
        rows = (rows + [""] * h)[:h]




        gutter_canv = urwid.Text([("editor_lineno", "\n".join(r.ljust(gw) for r in rows))], wrap="clip").render((gw,))
        joined = urwid.CanvasJoin([(gutter_canv, None, False, gw), (edit_canv, None, focus, tw)])
        if focus:
            coords = super().get_cursor_coords((tw,))
            if coords is not None:
                joined.cursor = (coords[0] + gw, coords[1])
        return joined

    def mouse_event(self, size, event, button, x, y, focus):
        gw = self._gutter_width(size[0])
        if x < gw:
            return True
        return super().mouse_event((max(1, size[0] - gw),), event, button, x - gw, y, focus)


class FileEntry(urwid.WidgetWrap):
    signals = ["click"]

    def __init__(self, label, path, depth, executable=False):
        self.path = path
        self.executable = executable
        text = ("  " * depth) + "· " + label + (" *" if executable else "")
        style = "editor_exec" if executable else None
        super().__init__(urwid.AttrMap(urwid.Text(text), style, focus_map="list_focus"))

    def selectable(self):
        return True

    def keypress(self, size, key):
        if self._command_map[key] == urwid.ACTIVATE:
            self._emit("click")
            return None
        return key

    def mouse_event(self, size, event, button, x, y, focus):
        if button == 1 and urwid.util.is_mouse_press(event):
            self._emit("click")
            return True
        return False


class FolderEntry(urwid.WidgetWrap):
    signals = ["click"]

    def __init__(self, label, path, depth, expanded, glyphs):
        self.path = path
        icon = glyphs.get("folder_open" if expanded else "folder", "[-]" if expanded else "[+]")
        text = ("  " * depth) + icon + " " + label + "/"
        super().__init__(urwid.AttrMap(urwid.Text(text), "editor_dir", focus_map="list_focus"))

    def selectable(self):
        return True

    def keypress(self, size, key):
        if self._command_map[key] == urwid.ACTIVATE:
            self._emit("click")
            return None
        return key

    def mouse_event(self, size, event, button, x, y, focus):
        if button == 1 and urwid.util.is_mouse_press(event):
            self._emit("click")
            return True
        return False


class PathDialog(urwid.WidgetWrap):
    def __init__(self, title, default, on_ok, on_cancel):
        self.on_ok = on_ok
        self.on_cancel = on_cancel
        self.edit = ReadlineEdit(caption="", edit_text=default)
        pile = urwid.Pile([
            urwid.Text(title),
            urwid.Divider(),
            urwid.AttrMap(self.edit, "list_off_focus", "list_focus"),
            urwid.Divider(),
            urwid.Columns([
                urwid.Button("OK", on_press=lambda b: self.on_ok(self.edit.edit_text)),
                urwid.Button("Cancel", on_press=lambda b: self.on_cancel()),
            ], dividechars=2),
        ])
        super().__init__(urwid.LineBox(urwid.Filler(pile, valign="top"), title=title))

    def keypress(self, size, key):
        if key == "esc":
            self.on_cancel(); return None
        if key == "enter" and self._w.original_widget.original_widget.focus_position == 2:
            self.on_ok(self.edit.edit_text); return None
        return super().keypress(size, key)


class InfoDialog(urwid.WidgetWrap):
    def __init__(self, title, message, on_ok):
        self.on_ok = on_ok
        pile = urwid.Pile([
            urwid.Text(message),
            urwid.Divider(),
            urwid.Button("OK", on_press=lambda b: on_ok()),
        ])
        super().__init__(urwid.LineBox(urwid.Filler(pile, valign="top"), title=title))

    def keypress(self, size, key):
        if key in ("esc", "enter"):
            self.on_ok(); return None
        return super().keypress(size, key)


class ConfirmDialog(urwid.WidgetWrap):
    def __init__(self, title, message, buttons, on_cancel=None):
        self.on_cancel = on_cancel
        cols = [urwid.Button(label, on_press=lambda b, c=cb: c()) for label, cb in buttons]
        pile = urwid.Pile([urwid.Text(message), urwid.Divider(), urwid.Columns(cols, dividechars=2)])
        super().__init__(urwid.LineBox(urwid.Filler(pile, valign="top"), title=title))

    def keypress(self, size, key):
        if key == "esc" and self.on_cancel:
            self.on_cancel(); return None
        return super().keypress(size, key)


class SnippetDialog(urwid.WidgetWrap):
    def __init__(self, on_pick, on_cancel):
        self.on_cancel = on_cancel
        items = [urwid.AttrMap(urwid.Button(name, on_press=lambda b, t=text: on_pick(t)), None, focus_map="list_focus")
                 for name, text in SNIPPETS]
        super().__init__(urwid.LineBox(urwid.ListBox(urwid.SimpleFocusListWalker(items)), title="Insert Micron snippet"))

    def keypress(self, size, key):
        if key == "esc":
            self.on_cancel(); return None
        return super().keypress(size, key)


class FindDialog(urwid.WidgetWrap):
    def __init__(self, ed, on_close):
        self.ed = ed
        self.on_close = on_close
        self.find_edit = ReadlineEdit(caption="Find:    ")
        self.repl_edit = ReadlineEdit(caption="Replace: ")
        pile = urwid.Pile([
            urwid.AttrMap(self.find_edit, "list_off_focus", "list_focus"),
            urwid.AttrMap(self.repl_edit, "list_off_focus", "list_focus"),
            urwid.Divider(),
            urwid.Columns([
                urwid.Button("Next", on_press=lambda b: ed.find_next(self.find_edit.edit_text)),
                urwid.Button("Replace", on_press=lambda b: ed.replace_one(self.find_edit.edit_text, self.repl_edit.edit_text)),
                urwid.Button("All", on_press=lambda b: ed.replace_all(self.find_edit.edit_text, self.repl_edit.edit_text)),
                urwid.Button("Close", on_press=lambda b: on_close()),
            ], dividechars=1),
        ])
        super().__init__(urwid.LineBox(urwid.Filler(pile, valign="top"), title="Find / Replace"))

    def keypress(self, size, key):
        if key == "esc":
            self.on_close(); return None
        return super().keypress(size, key)


class PermissionsDialog(urwid.WidgetWrap):
    def __init__(self, title, note, content, on_ok, on_cancel):
        self.on_ok = on_ok
        self.on_cancel = on_cancel
        self.edit = ReadlineEdit(caption="", edit_text=content, multiline=True)
        pile = urwid.Pile([
            urwid.Text(note),
            urwid.Divider(),
            urwid.BoxAdapter(urwid.AttrMap(urwid.ListBox(urwid.SimpleListWalker([self.edit])), "list_off_focus", "list_focus"), 7),
            urwid.Divider(),
            urwid.Columns([
                urwid.Button("Save", on_press=lambda b: self.on_ok(self.edit.edit_text)),
                urwid.Button("Cancel", on_press=lambda b: self.on_cancel()),
            ], dividechars=2),
        ])
        super().__init__(urwid.LineBox(urwid.Filler(pile, valign="top"), title=title))

    def keypress(self, size, key):
        if key == "esc":
            self.on_cancel(); return None
        return super().keypress(size, key)


class EditorColumns(urwid.Columns):
    def keypress(self, size, key):
        ed = self.editor_display
        if key == "ctrl s":
            ed.save_or_saveas(); return None
        if key == "ctrl n":
            ed.new_file_dialog(); return None
        if key == "ctrl f":
            ed.find_dialog(); return None
        if key == "ctrl g":
            ed.snippet_dialog(); return None
        if key == "ctrl p":
            ed.permissions_dialog(); return None
        if key == "f2" and ed.files_focused():
            ed.rename_dialog(); return None
        if key == "delete" and ed.files_focused():
            ed.delete_dialog(); return None
        if key == "ctrl t":
            ed.toggle_pane("files"); return None
        if key == "ctrl b":
            ed.toggle_pane("editor"); return None
        if key == "ctrl r":
            ed.toggle_pane("preview"); return None
        if key == "tab":
            self.focus_position = (self.focus_position + 1) % len(self.contents); return None
        if key == "shift tab":
            self.focus_position = (self.focus_position - 1) % len(self.contents); return None
        if key == "esc":
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.focus_position = "header"
            return None
        result = super().keypress(size, key)
        if key == "up" and result == "up":
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.focus_position = "header"
            return None
        return result


class PageEditorShortcuts():
    def __init__(self, app):
        self.app = app
        self.status = urwid.Text("", align=urwid.RIGHT)
        base = "[C-n]New [C-s]Save [C-f]Find [C-g]Snippet [C-p]Perms [F2]Rename [Del]Delete [Tab]Pane [C-t/b/r]Toggle [Esc]Menu"
        self.widget = urwid.AttrMap(urwid.Columns([urwid.Text(base), self.status], dividechars=2), "shortcutbar")

    def set_status(self, msg):
        self.status.set_text(msg)


class PageEditorDisplay():
    def __init__(self, app):
        self.app = app
        self.current_path = None
        self.editable = False
        self.is_exec = False
        self.dirty = False
        self.preview_alarm = None
        self._loading = False
        self._find = None
        self._last_file = None
        self.expanded = set(p for p in (app.pagespath, app.filespath) if p)
        self.filter_mu = False
        self.pane_visible = {"files": True, "editor": True, "preview": True}
        self.load_state()
        self.register_styles()

        self.preview_browser = Browser(self.app, "nomadnetwork", "node", delegate=None)
        self.preview_browser.handle_link = self._preview_handle_link
        self.preview_browser.marked_link = lambda *a, **k: None
        self.preview_browser._content_cols = self._preview_cols
        # don't fetch partials in the preview
        self.preview_browser.detect_partials = lambda: None

        self.editor = GutterEdit(caption="", edit_text="", multiline=True)
        urwid.connect_signal(self.editor, "postchange", self.on_edit_change)

        self.filter_checkbox = urwid.CheckBox("Show only .mu", state=self.filter_mu, on_state_change=self.on_filter_change)
        self.tree_walker = urwid.SimpleFocusListWalker(self.build_entries())
        self.tree_listbox = IndicativeListBox(self.tree_walker, initialization_is_selection_change=False, highlight_offFocus="list_off_focus")
        self.files_pile = urwid.Pile([
            (urwid.PACK, urwid.AttrMap(self.filter_checkbox, None, focus_map="list_focus")),
            (urwid.WEIGHT, 1, self.tree_listbox),
        ])
        try: self.files_pile.focus_position = 1
        except Exception: pass

        self.pane_widgets = {
            "files": urwid.LineBox(self.files_pile, title="Files"),
            "editor": urwid.LineBox(urwid.ListBox(urwid.SimpleListWalker([self.editor])), title="Editor"),
            "preview": urwid.LineBox(urwid.SolidFill(" "), title="Preview"),
        }

        self.columns = EditorColumns([], dividechars=0)
        self.columns.editor_display = self
        self._visible = []
        self.rebuild_columns()

        self.shortcuts_display = PageEditorShortcuts(self.app)
        self.body = urwid.WidgetPlaceholder(self.columns)
        self.widget = self.body

    def register_styles(self):
        screen = self.app.ui.screen
        for entry in EDITOR_STYLES:
            try: screen.register_palette_entry(*entry)
            except Exception: pass

    def _preview_handle_link(self, target, link_data=None):
        # in the preview follow in page anchors but ignore external navigation
        # TODO

        if isinstance(target, str) and target.startswith("#"):
            name = target[1:]
            self.app.ui.loop.set_alarm_in(0.0, lambda l, d: self.preview_browser._jump_to_anchor(name))

    def _preview_cols(self):
        try:
            cols = self.app.ui.loop.screen.get_cols_rows()[0]
            visible = self.visible_panes()
            total = sum(PANE_WEIGHTS[n] for n in visible)
            frac = PANE_WEIGHTS["preview"] / total if "preview" in visible else PANE_WEIGHTS["preview"]
            return max(20, int(cols * frac) - 3)
        except Exception:
            return 80

    def shortcuts(self):
        return self.shortcuts_display

    def start(self):
        self.refresh_tree()
        if self._last_file and os.path.isfile(self._last_file) and self.current_path is None:
            self.load_file(self._last_file)
        self._last_file = None

    def files_focused(self):
        try: return self.visible_panes()[self.columns.focus_position] == "files"
        except Exception: return False

    def _state_file(self):
        d = getattr(self.app, "configdir", None)
        return os.path.join(d, "editor_state.json") if d else None

    def load_state(self):
        p = self._state_file()
        if not p or not os.path.isfile(p):
            return
        try:
            with open(p) as f:
                st = json.load(f)
            self.filter_mu = bool(st.get("filter_mu", self.filter_mu))
            if isinstance(st.get("expanded"), list):
                self.expanded = set(st["expanded"])
            pv = st.get("pane_visible")
            if isinstance(pv, dict):
                for k in self.pane_visible:
                    if k in pv: self.pane_visible[k] = bool(pv[k])
            self._last_file = st.get("last_file")
        except Exception:
            pass

    def save_state(self):
        p = self._state_file()
        if not p:
            return
        try:
            self._atomic_write(p, json.dumps({"filter_mu": self.filter_mu, "expanded": sorted(self.expanded),
                                              "pane_visible": self.pane_visible, "last_file": self.current_path}))
        except Exception:
            pass

    def _selected_tree(self):
        try:
            sel = self.tree_listbox.get_selected_item()
            return sel.original_widget if sel else None
        except Exception:
            return None

    def _roots(self):
        return [r for r in (self.app.pagespath, self.app.filespath) if r]

    def _is_root(self, path):
        try:
            rp = os.path.realpath(path)
        except Exception:
            return False
        return any(rp == os.path.realpath(r) for r in self._roots())

    def _confine(self, path, base=None):
        # Never save outside of the Nomad storage directory
        path = (path or "").strip()
        if not path:
            return None
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            base = base or self.app.pagespath or self.app.filespath
            if not base:
                return None
            path = os.path.join(base, path)
        norm = os.path.normpath(path)
        for root in self._roots():
            rp = os.path.normpath(root)
            if norm == rp or norm.startswith(rp + os.sep):
                return norm
        return None

    def _atomic_write(self, path, text):
        d = os.path.dirname(path) or "."
        tmp = os.path.join(d, "." + os.path.basename(path) + ".tmp")
        try:
            existing_mode = None
            try:
                existing_mode = os.stat(path).st_mode
            except OSError:
                existing_mode = None
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                try: os.fsync(f.fileno())
                except Exception: pass
            if existing_mode is not None:
                try: os.chmod(tmp, existing_mode)
                except Exception: pass
            os.replace(tmp, path)
        except Exception:
            try: os.remove(tmp)
            except Exception: pass
            raise

    def _confirm_overwrite(self, dest, proceed):
        self.show_dialog(ConfirmDialog("Overwrite",
            "%s already exists.\nOverwrite it?" % os.path.basename(dest),
            [("Overwrite", proceed), ("Cancel", self.close_dialog)],
            on_cancel=self.close_dialog))

    def visible_panes(self):
        return [n for n in PANE_ORDER if self.pane_visible[n]] or ["editor"]

    def rebuild_columns(self):
        focused = None
        try: focused = self._visible[self.columns.focus_position]
        except Exception: pass
        visible = self.visible_panes()
        self.columns.contents = [
            (self.pane_widgets[n], self.columns.options(urwid.WEIGHT, PANE_WEIGHTS[n], box_widget=True))
            for n in visible
        ]
        self._visible = visible
        # the rpeview starts non-selectable
        target = focused if focused in visible else ("files" if "files" in visible else visible[0])
        try: self.columns.focus_position = visible.index(target)
        except Exception: pass

    def toggle_pane(self, name):
        visible = self.visible_panes()
        if self.pane_visible[name] and len(visible) <= 1:
            return
        self.pane_visible[name] = not self.pane_visible[name]
        self.rebuild_columns()
        self.save_state()

    def refresh_tree(self):
        focus_path = None
        try:
            sel = self.tree_listbox.get_selected_item()
            if sel is not None:
                focus_path = getattr(sel.original_widget, "path", None)
        except Exception:
            pass
        entries = self.build_entries()
        # indicativelistbox wraps items in attrmap for highlighting
        self.tree_walker[:] = [urwid.AttrMap(e, None) for e in entries]
        if focus_path is not None:
            for i, e in enumerate(entries):
                if getattr(e, "path", None) == focus_path:
                    try: self.tree_listbox.select_item(i)
                    except Exception: pass
                    break

    def build_entries(self):
        entries = []
        for label, root in (("pages", self.app.pagespath), ("files", self.app.filespath)):
            if not root or not os.path.isdir(root):
                continue
            entries.extend(self.walk_dir(label, root, 0))
        if not entries:
            entries = [urwid.Text("no files")]
        return entries

    def walk_dir(self, name, path, depth):
        out = []
        expanded = path in self.expanded
        folder = FolderEntry(name, path, depth, expanded, self.app.ui.glyphs)
        urwid.connect_signal(folder, "click", self.on_folder_click)
        out.append(folder)
        if not expanded:
            return out
        try:
            names = sorted(os.listdir(path), key=str.lower)
        except Exception:
            return out
        dirs = [n for n in names if os.path.isdir(os.path.join(path, n)) and not n.startswith(".") and n != "__pycache__"]
        files = [n for n in names if not os.path.isdir(os.path.join(path, n)) and not n.startswith(".")]
        if self.filter_mu:
            files = [n for n in files if n.endswith(".mu")]
            dirs = [d for d in dirs if self._dir_has_mu(os.path.join(path, d))]
        for d in dirs:
            out.extend(self.walk_dir(d, os.path.join(path, d), depth + 1))
        for fn in files:
            full = os.path.join(path, fn)
            entry = FileEntry(fn, full, depth + 1, executable=is_executable(full))
            urwid.connect_signal(entry, "click", self.on_file_click)
            out.append(entry)
        return out

    def _dir_has_mu(self, path):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            if any(f.endswith(".mu") for f in files):
                return True
        return False

    def on_filter_change(self, checkbox, state):
        self.filter_mu = state
        self.refresh_tree()
        self.save_state()

    def on_folder_click(self, folder):
        if folder.path in self.expanded:
            self.expanded.discard(folder.path)
        else:
            self.expanded.add(folder.path)
        self.refresh_tree()
        self.save_state()

    def on_file_click(self, entry):
        self.open_path(entry.path)

    def open_path(self, path):
        if self.dirty:
            self.confirm_discard(lambda: self._do_open(path))
        else:
            self._do_open(path)

    def _do_open(self, path):
        self.load_file(path)
        if self.pane_visible["editor"]:
            try: self.columns.focus_position = self.visible_panes().index("editor")
            except Exception: pass

    def confirm_discard(self, proceed):
        def save_then():
            self.close_dialog()
            if self.current_path and self.editable:
                self.save_file(self.current_path)
            proceed()
        name = os.path.basename(self.current_path) if self.current_path else "this buffer"
        if self.current_path and self.editable:
            buttons = [("Save", save_then), ("Discard", lambda: (self.close_dialog(), proceed())), ("Cancel", self.close_dialog)]
        else:
            buttons = [("Discard", lambda: (self.close_dialog(), proceed())), ("Cancel", self.close_dialog)]
        self.show_dialog(ConfirmDialog("Unsaved changes", "Discard unsaved changes to %s?" % name,
            buttons, on_cancel=self.close_dialog))

    def load_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.editable = True
        except UnicodeDecodeError:
            content = ""
            self.editable = False
        except Exception as e:
            self.set_status("open failed: %s" % e); return

        self.current_path = path
        self.is_exec = is_executable(path)
        self.dirty = False
        self._loading = True
        self.editor.set_edit_text(content)
        self.editor.set_edit_pos(0)
        self._loading = False

        name = os.path.basename(path)
        self.update_title()
        self.save_state()
        if not self.editable:
            self.set_status("binary file (not editable)")
        elif self.is_exec:
            self.set_preview_note(name + " is an executable page. the node runs it and serves its output.")
            self.set_status("executable page")
            self.show_info_dialog("Executable page", name + " is marked executable (chmod +x). NomadNet runs it and serves its output as the page, so the preview shows the source rather than the rendered output.")
        else:
            self.render_preview()
            self.set_status("opened " + name)

    def update_title(self, modified=False):



        if self.current_path is None:
            self.pane_widgets["editor"].set_title("Editor"); return
        suffix = " (binary)" if not self.editable else (" (executable)" if self.is_exec else "")
        if modified:
            suffix += " *"
        self.pane_widgets["editor"].set_title("Editor: " + os.path.basename(self.current_path) + suffix)

    def set_preview_note(self, msg):
        self.pane_widgets["preview"].original_widget = urwid.Filler(urwid.Text(msg), urwid.TOP)

    def show_info_dialog(self, title, message):
        self.show_dialog(InfoDialog(title, message, self.close_dialog))

    def save_or_saveas(self):
        if self.current_path is None:
            self.save_as_dialog(); return
        self.save_file(self.current_path)

    def save_file(self, path):
        if not self.editable and self.current_path is not None:
            self.set_status("cannot save binary file"); return
        try:
            self._atomic_write(path, self.editor.edit_text)
            self.current_path = path
            self.editable = True
            self.dirty = False
            self.set_modified(False)
            self.set_status("saved " + os.path.basename(path))
            self.refresh_tree()
            self.save_state()
        except Exception as e:
            self.set_status("save failed: %s" % e)

    def new_file_dialog(self):
        default = (self.app.pagespath or "") + os.sep
        self.show_dialog(PathDialog("New (end with / for a folder)", default, self._do_new, self.close_dialog))

    def _do_new(self, path):
        self.close_dialog()
        raw = (path or "").strip()
        if not raw:
            return
        is_folder = raw.endswith("/") or raw.endswith(os.sep)
        target = self._confine(raw)
        if target is None:
            self.set_status("path must be inside pages/ or files/"); return
        try:
            if is_folder:
                os.makedirs(target, exist_ok=True)
                self.expanded.add(target)
                self.refresh_tree(); self.save_state()
                self.set_status("created folder " + os.path.basename(target))
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if not os.path.exists(target):
                    self._atomic_write(target, "")
                self.refresh_tree()
                self.open_path(target)
        except Exception as e:
            self.set_status("new failed: %s" % e)

    def rename_dialog(self):
        w = self._selected_tree()
        if not w or not getattr(w, "path", None):
            self.set_status("select a file/folder to rename"); return
        if self._is_root(w.path):
            self.set_status("cannot rename the pages/files root"); return
        self.show_dialog(PathDialog("Rename", w.path, lambda p, old=w.path: self._do_rename(old, p), self.close_dialog))

    def _do_rename(self, old, new):
        self.close_dialog()
        target = self._confine(new, base=os.path.dirname(old))
        if target is None:
            self.set_status("path must be inside pages/ or files/"); return
        if target == os.path.normpath(old):
            return

        def proceed():
            self.close_dialog()
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.rename(old, target)
                if os.path.isfile(old + ".allowed"):
                    try: os.replace(old + ".allowed", target + ".allowed")
                    except Exception: pass
                old_prefix = old + os.sep
                if self.current_path == old:
                    self.current_path = target; self.update_title()
                elif self.current_path and self.current_path.startswith(old_prefix):
                    self.current_path = target + self.current_path[len(old):]; self.update_title()
                self.expanded = set(
                    target if p == old else (target + p[len(old):] if p.startswith(old_prefix) else p)
                    for p in self.expanded
                )
                self.refresh_tree(); self.save_state()
                self.set_status("renamed to " + os.path.basename(target))
            except Exception as e:
                self.set_status("rename failed: %s" % e)

        if os.path.exists(target) and os.path.realpath(target) != os.path.realpath(old):
            self._confirm_overwrite(target, proceed)
        else:
            proceed()

    def delete_dialog(self):
        w = self._selected_tree()
        if not w or not getattr(w, "path", None):
            self.set_status("select a file/folder to delete"); return
        path = w.path
        if self._is_root(path):
            self.set_status("cannot delete the pages/files root"); return
        self.show_dialog(ConfirmDialog("Delete", "Delete %s?" % os.path.basename(path),
            [("Delete", lambda: self._do_delete(path)), ("Cancel", self.close_dialog)], on_cancel=self.close_dialog))

    def _do_delete(self, path):
        self.close_dialog()
        try:
            prefix = path + os.sep
            if os.path.isdir(path):
                shutil.rmtree(path)
                self.expanded = set(p for p in self.expanded if p != path and not p.startswith(prefix))
            else:
                os.remove(path)
                if os.path.isfile(path + ".allowed"):
                    try: os.remove(path + ".allowed")
                    except Exception: pass
            if self.current_path is not None and (self.current_path == path or self.current_path.startswith(prefix)):
                self.current_path = None; self.editable = False; self.is_exec = False; self.dirty = False
                self._loading = True; self.editor.set_edit_text(""); self._loading = False
                self.update_title(); self.set_preview_note("")
            self.refresh_tree(); self.save_state()
            self.set_status("deleted " + os.path.basename(path))
        except Exception as e:
            self.set_status("delete failed: %s" % e)

    def permissions_dialog(self):
        w = self._selected_tree()
        if not w or not getattr(w, "path", None):
            self.set_status("select a file/folder for permissions"); return
        path = w.path
        is_dir = os.path.isdir(path)
        content = ""
        if not is_dir and os.path.isfile(path + ".allowed"):
            try: content = open(path + ".allowed", encoding="utf-8").read()
            except Exception: content = ""
        note = ("Allowed identity hashes per line. Empty = public.\n"
                + ("Applies to every page in this folder." if is_dir else "Applys to this page."))
        title = "Permissions: " + os.path.basename(path) + ("/" if is_dir else "")
        self.show_dialog(PermissionsDialog(title, note, content,
            lambda txt: self._save_permissions(path, is_dir, txt), self.close_dialog))

    def _save_permissions(self, path, is_dir, text):
        self.close_dialog()
        body = "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())
        try:
            if is_dir:
                count = 0
                for root, dirs, files in os.walk(path):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                    for fn in files:
                        if fn.endswith(".allowed"):
                            continue
                        self._write_allowed(os.path.join(root, fn), body)
                        count += 1
                self.set_status("permissions applied to %d files" % count)
            else:
                self._write_allowed(path, body)
                self.set_status("permissions saved" if body else "permissions cleared (public)")
            self.refresh_tree()
        except Exception as e:
            self.set_status("permissions failed: %s" % e)

    def _write_allowed(self, path, body):
        ap = path + ".allowed"
        if body:
            self._atomic_write(ap, body + "\n")
        elif os.path.exists(ap):
            os.remove(ap)

    def snippet_dialog(self):
        self.show_dialog(SnippetDialog(self._insert_snippet, self.close_dialog))

    def _insert_snippet(self, text):
        self.close_dialog()
        if self.pane_visible["editor"]:
            try: self.columns.focus_position = self.visible_panes().index("editor")
            except Exception: pass
        pos = self.editor.edit_pos
        t = self.editor.edit_text
        self.editor.set_edit_text(t[:pos] + text + t[pos:])
        self.editor.set_edit_pos(pos + len(text))

    def find_dialog(self):
        if self._find is None:
            self._find = FindDialog(self, self.close_dialog)
        self.show_dialog(self._find)

    def find_next(self, term):
        if not term:
            return
        t = self.editor.edit_text
        idx = t.find(term, self.editor.edit_pos)
        if idx < 0:
            idx = t.find(term, 0)
        if idx < 0:
            self.set_status("'%s' not found" % term); return
        self.editor.set_edit_pos(idx + len(term))
        self.set_status("found at %d" % idx)

    def replace_one(self, term, repl):
        if not term:
            return
        t = self.editor.edit_text
        end = self.editor.edit_pos
        start = end - len(term)
        if start >= 0 and t[start:end] == term:
            self.editor.set_edit_text(t[:start] + repl + t[end:])
            self.editor.set_edit_pos(start + len(repl))
            self.set_status("replaced")
        else:
            self.find_next(term)

    def replace_all(self, term, repl):
        if not term:
            return
        cnt = self.editor.edit_text.count(term)
        if cnt:
            self.editor.set_edit_text(self.editor.edit_text.replace(term, repl))
            self.set_status("replaced %d" % cnt)
        else:
            self.set_status("'%s' not found" % term)

    def save_as_dialog(self):
        default = self.current_path or ((self.app.pagespath or "") + os.sep)
        self.show_dialog(PathDialog("Save as", default, self._do_saveas, self.close_dialog))

    def _do_saveas(self, path):
        self.close_dialog()
        target = self._confine(path)
        if target is None:
            self.set_status("path must be inside pages/ or files/"); return

        def proceed():
            self.close_dialog()
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
            except Exception:
                pass
            self.editable = True
            self.save_file(target)

        already = self.current_path is None or os.path.realpath(target) != os.path.realpath(self.current_path)
        if os.path.exists(target) and already:
            self._confirm_overwrite(target, proceed)
        else:
            proceed()

    def show_dialog(self, dialog):
        self.dialog = dialog
        overlay = urwid.Overlay(
            dialog, self.columns,
            align=urwid.CENTER, width=(urwid.RELATIVE, 60),
            valign=urwid.MIDDLE, height=(urwid.RELATIVE, 40),
            min_width=30, min_height=8,
        )
        self.body.original_widget = overlay

    def close_dialog(self):
        self.dialog = None
        self.body.original_widget = self.columns

    def on_edit_change(self, widget, old_text):
        if self._loading or (self.current_path is not None and not self.editable):
            return
        self.dirty = True
        self.set_modified(True)
        if self.is_exec:
            return
        if self.preview_alarm is not None:
            try: self.app.ui.loop.remove_alarm(self.preview_alarm)
            except Exception: pass
        self.preview_alarm = self.app.ui.loop.set_alarm_in(PREVIEW_DELAY, self._render_preview_alarm)

    def _render_preview_alarm(self, loop, user_data):
        self.preview_alarm = None
        self.render_preview()

    def render_preview(self):
        if len(self.editor.edit_text) > MAX_PREVIEW_CHARS:
            self.set_preview_note("File too large to preview (%d KB). Editing still works." % (len(self.editor.edit_text) // 1000))
            return
        pos = self._preview_scrollpos()
        try:
            body = self.preview_browser.render_markup_buffer(self.editor.edit_text)
        except Exception as e:
            body = urwid.Filler(urwid.Text("preview error: %s" % e), urwid.TOP)
        self.pane_widgets["preview"].original_widget = body
        self._set_preview_scrollpos(pos)

    def _preview_scrollable(self):
        try:
            return self.preview_browser.browser_body.original_widget.original_widget
        except Exception:
            return None

    def _preview_scrollpos(self):
        s = self._preview_scrollable()
        try: return s.get_scrollpos()
        except Exception: return None

    def _set_preview_scrollpos(self, pos):
        if pos is None: return
        s = self._preview_scrollable()
        try: s.set_scrollpos(pos)
        except Exception: pass

    def set_modified(self, modified):
        self.update_title(modified)

    def set_status(self, msg):
        self.shortcuts_display.set_status(msg)
