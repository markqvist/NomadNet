import os
import nomadnet
import urwid

class FileBrowserEntry(urwid.WidgetWrap):
    signals = ["click"]

    def __init__(self, name, full_path, is_dir=False, is_parent=False, selected=False):
        self.full_path = full_path
        self.name = name
        self.is_dir = is_dir
        self.is_parent = is_parent
        self.selected = selected
        g = nomadnet.NomadNetworkApp.get_shared_instance().ui.glyphs
        if is_parent:
            display = g["arrow_l"]+" .."
        elif is_dir:
            display = g["arrow_r"]+" "+name+"/"
        elif selected:
            display = g["check"]+" "+name
        else:
            display = "  "+name
        self.text_widget = urwid.SelectableIcon(display, 0)
        if is_dir or is_parent:
            style = "list_trusted"
            focus_style = "list_focus"
        elif selected:
            style = "list_trusted"
            focus_style = "list_focus_trusted"
        else:
            style = "list_unknown"
            focus_style = "list_focus"
        display_widget = urwid.AttrMap(self.text_widget, style, focus_style)
        super().__init__(display_widget)

    def keypress(self, size, key):
        if key == "enter":
            self._emit("click")
        else:
            return key

    def mouse_event(self, size, event, button, x, y, focus):
        if button == 1 and urwid.util.is_mouse_press(event):
            self._emit("click")
            return True
        return False

class FileBrowser(urwid.WidgetWrap):
    def __init__(self, on_done=None, on_cancel=None, on_change=None, title="Select File", multi_select=True, start_path=None, selected=None, max_file_size=None):
        self.on_done_cb = on_done
        self.on_cancel_cb = on_cancel
        self.on_change_cb = on_change
        self.multi_select = multi_select
        self.max_file_size = max_file_size
        self.selected = list(selected) if selected else []

        app = nomadnet.NomadNetworkApp.get_shared_instance()
        self.g = app.ui.glyphs
        self.current_path = os.path.expanduser(start_path) if start_path else os.path.expanduser("~")

        self.path_label = urwid.Text("")
        self.status_label = urwid.Text("")
        self.file_walker = urwid.SimpleFocusListWalker([])
        self.file_listbox = urwid.ListBox(self.file_walker)

        self.button_columns = urwid.Columns([
            (urwid.WEIGHT, 0.45, urwid.Button("Done", on_press=self._dismiss)),
            (urwid.WEIGHT, 0.1, urwid.Text("")),
            (urwid.WEIGHT, 0.45, urwid.Button("Cancel", on_press=self._cancel)),
        ])

        header_pile = urwid.Pile([
            self.path_label,
            self.status_label,
            urwid.Divider(self.g["divider1"]),
        ])
        footer_pile = urwid.Pile([
            urwid.Divider(self.g["divider1"]),
            self.button_columns,
        ])

        self._populate()

        self.browser_frame = urwid.Frame(self.file_listbox, header=header_pile, footer=footer_pile)
        self._main_widget = urwid.LineBox(self.browser_frame, title=title)
        self._notice_open = False
        super().__init__(self._main_widget)

    def _show_notice(self, message, title="Notice"):
        def dismiss(_b=None):
            self._notice_open = False
            self._w = self._main_widget

        box = urwid.LineBox(urwid.Pile([
            urwid.Text(message, align=urwid.CENTER),
            urwid.Divider(),
            urwid.Padding(urwid.Button("OK", on_press=dismiss), align=urwid.CENTER, width=8),
        ]), title=title)
        self._notice_open = True
        self._w = urwid.Overlay(box, self._main_widget, align=urwid.CENTER, width=("relative", 75), valign=urwid.MIDDLE, height=urwid.PACK)

    def _dismiss_notice(self):
        self._notice_open = False
        self._w = self._main_widget

    def _update_status(self):
        if self.selected:
            names = [os.path.basename(p) for p in self.selected]
            self.status_label.set_text("  "+self.g["file"]+" "+str(len(self.selected))+" selected: "+", ".join(names))
        elif self.multi_select:
            self.status_label.set_text("  No files selected")
        else:
            self.status_label.set_text("  Select a file")

    def _populate(self):
        self.path_label.set_text("  "+self.current_path)
        self._update_status()

        focus_pos = None
        try:
            focus_pos = self.file_listbox.focus_position
        except Exception:
            pass

        entries = []
        parent = os.path.dirname(self.current_path)
        if parent != self.current_path:
            entry = FileBrowserEntry("..", parent, is_parent=True)
            urwid.connect_signal(entry, "click", self._entry_clicked, entry)
            entries.append(entry)

        try:
            items = sorted(os.listdir(self.current_path))
        except PermissionError:
            entries.append(urwid.Text(("error_text", "  Permission denied")))
            self.file_walker[:] = entries
            return
        except Exception:
            entries.append(urwid.Text(("error_text", "  Cannot read directory")))
            self.file_walker[:] = entries
            return

        dirs = []
        files = []
        for item in items:
            if item.startswith("."):
                continue
            full = os.path.join(self.current_path, item)
            if os.path.isdir(full):
                dirs.append((item, full))
            elif os.path.isfile(full):
                files.append((item, full))

        for name, full in dirs:
            entry = FileBrowserEntry(name, full, is_dir=True)
            urwid.connect_signal(entry, "click", self._entry_clicked, entry)
            entries.append(entry)

        for name, full in files:
            entry = FileBrowserEntry(name, full, selected=(full in self.selected))
            urwid.connect_signal(entry, "click", self._entry_clicked, entry)
            entries.append(entry)

        if not dirs and not files:
            entries.append(urwid.Text(("inactive_text", "  (empty)")))

        self.file_walker[:] = entries
        if focus_pos is not None and focus_pos < len(entries):
            self.file_listbox.set_focus(focus_pos)
        elif entries:
            self.file_listbox.set_focus(0)

    def _entry_clicked(self, entry_widget, user_data=None):
        entry = user_data if user_data else entry_widget
        if entry.is_dir or entry.is_parent:
            self.current_path = entry.full_path
            self._populate()
            return

        if self.max_file_size is not None and entry.full_path not in self.selected:
            try:
                file_size = os.path.getsize(entry.full_path)
            except Exception:
                file_size = 0
            if file_size > self.max_file_size:
                limit_mb = self.max_file_size / (1024 * 1024)
                size_mb = file_size / (1024 * 1024)
                self._show_notice(
                    "%s is %.1f MB.\nAttachments are limited to %.0f MB." % (entry.name, size_mb, limit_mb),
                    title="File too large",
                )
                return

        if self.multi_select:
            if entry.full_path in self.selected:
                self.selected.remove(entry.full_path)
            else:
                self.selected.append(entry.full_path)
            if self.on_change_cb is not None:
                self.on_change_cb(list(self.selected))
            self._populate()
        else:
            self.selected = [entry.full_path]
            if self.on_change_cb is not None:
                self.on_change_cb(list(self.selected))
            if self.on_done_cb is not None:
                self.on_done_cb(list(self.selected))

    def _dismiss(self, sender):
        if self.on_done_cb is not None:
            self.on_done_cb(list(self.selected))

    def _cancel(self, sender):
        self.selected = []
        if self.on_cancel_cb is not None:
            self.on_cancel_cb()

    def keypress(self, size, key):
        if self._notice_open:
            if key in ("esc", "enter"):
                self._dismiss_notice()
                return None
            return super().keypress(size, key)
        if key == "esc":
            self._cancel(None)
            return None
        result = super().keypress(size, key)
        if result == "down" and self.browser_frame.focus_position == "body":
            self.browser_frame.focus_position = "footer"
            return None
        elif result == "up" and self.browser_frame.focus_position == "footer":
            self.browser_frame.focus_position = "body"
            return None
        return result
