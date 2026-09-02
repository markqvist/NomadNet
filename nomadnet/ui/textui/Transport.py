import RNS
import time
import urwid

def _fmt_secs(secs):
    secs = int(secs)
    if secs < 0:
        secs = 0
    if secs < 60:
        return "%ds" % secs
    if secs < 3600:
        return "%dm" % (secs // 60)
    if secs < 86400:
        return "%dh" % (secs // 3600)
    return "%dd" % (secs // 86400)

def _rel_future(ts):
    if not ts:
        return "-"
    remaining = ts - time.time()
    if remaining <= 0:
        return "expired"
    return _fmt_secs(remaining)

def _rel_past(ts):
    if not ts:
        return "-"
    return _fmt_secs(time.time() - ts) + " ago"

def _fmt_duration(secs):
    if not secs:
        return "n/a"
    secs = int(secs)
    if secs < 0:
        secs = 0
    days = secs // 86400
    hours = (secs % 86400) // 3600
    minutes = (secs % 3600) // 60
    if days:
        return "%dd %dh" % (days, hours)
    if hours:
        return "%dh %dm" % (hours, minutes)
    if minutes:
        return "%dm" % minutes
    return "%ds" % secs

def _fmt_rate(hz):
    try:
        hz = float(hz or 0)
    except Exception:
        return "0"
    if hz <= 0:
        return "0"
    per_hour = hz * 3600
    if per_hour >= 1:
        return "%.0f/h" % per_hour
    return "%.1f/d" % (hz * 86400)

def _mode_str(mode):
    return {1: "Full", 2: "Point-to-Point", 3: "Access Point", 4: "Roaming", 5: "Boundary", 6: "Gateway"}.get(mode, "Full")

class TransportRow(urwid.WidgetWrap):
    def __init__(self, columns):
        self._selectable = True
        super().__init__(urwid.AttrMap(columns, "list_normal", focus_map="list_focus"))

    def selectable(self):
        return True

    def keypress(self, size, key):
        return key

class LazyTableWalker(urwid.ListWalker):
    def __init__(self):
        self.items = []
        self.factory = None
        self.empty_widget = None
        self.focus = 0

    def configure(self, items, factory, empty_widget=None):
        self.items = items or []
        self.factory = factory
        self.empty_widget = empty_widget
        if self.focus >= len(self.items):
            self.focus = max(0, len(self.items) - 1)
        self._modified()

    def _build(self, position):
        return self.factory(self.items[position], position)

    def get_focus(self):
        if not self.items:
            if self.empty_widget is not None:
                return (self.empty_widget, 0)
            return (None, None)
        if self.focus >= len(self.items):
            self.focus = len(self.items) - 1
        if self.focus < 0:
            self.focus = 0
        return (self._build(self.focus), self.focus)

    def set_focus(self, position):
        self.focus = position
        self._modified()

    def get_next(self, position):
        n = position + 1
        if not self.items or n >= len(self.items):
            return (None, None)
        return (self._build(n), n)

    def get_prev(self, position):
        p = position - 1
        if not self.items or p < 0:
            return (None, None)
        return (self._build(p), p)

    def positions(self, reverse=False):
        count = len(self.items)
        if count == 0:
            return [0] if self.empty_widget is not None else []
        if reverse:
            return range(count - 1, -1, -1)
        return range(count)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, position):
        if not self.items:
            if position == 0 and self.empty_widget is not None:
                return self.empty_widget
            raise IndexError(position)
        if position < 0 or position >= len(self.items):
            raise IndexError(position)
        return self._build(position)

class TransportFiller(urwid.WidgetWrap):
    def __init__(self, widget, display):
        self.display = display
        super().__init__(widget)

    def keypress(self, size, key):
        if key == "tab":
            self.display.cycle_tab()
            return None
        if key == "ctrl r" or key == "f5":
            self.display.refresh()
            return None
        if key == "esc":
            self.display.go_back()
            return None
        result = super().keypress(size, key)
        if key == "up" and result == "up":
            self.display.go_back_to_header()
            return None
        return result

class TransportDisplayShortcuts:
    def __init__(self, app):
        self.app = app
        self.widget = urwid.AttrMap(
            urwid.Text("[Tab] Switch Table  [Up] Filter  [C-r] Refresh  [Esc] Back"),
            "shortcutbar"
        )

class TransportDisplay:
    POLL_INTERVAL = 5

    HASH_W = 34
    HOPS_W = 6
    VIA_W = 34
    EXP_W = 12
    LAST_W = 16
    VIOL_W = 11
    STATUS_W = 10
    PATHS_W = 8
    HELD_W = 8
    QUEUE_W = 8
    RATE_W = 10
    MODE_W = 12

    def __init__(self, app, parent=None):
        self.app = app
        self.parent = parent
        self.started = False
        self.poll_scheduler = False
        self.glyphset = self.app.config["textui"]["glyphs"]
        self.g = self.app.ui.glyphs

        self.active_tab = "paths"
        self.paths = []
        self.rates = []
        self.interfaces = []
        self.paths_per_interface = {}
        self.link_count = 0
        self.transport_id = None
        self.network_id = None
        self.transport_uptime = None
        self.held_announces = 0
        self.filter_text = ""

        self.summary_text = urwid.Text("")
        self.list_walker = LazyTableWalker()
        self.list_box = urwid.ListBox(self.list_walker)

        self.filter_edit = urwid.Edit("", "")
        urwid.connect_signal(self.filter_edit, "change", self._on_filter_change)
        self.filter_row = urwid.Columns([
            (9, urwid.Text(("key", "Filter:"))),
            urwid.AttrMap(self.filter_edit, "list_normal", focus_map="list_focus"),
        ], dividechars=1)

        self.pile = urwid.Pile([
            ('pack', self.summary_text),
            ('pack', self._tab_bar()),
            ('pack', self.filter_row),
            ('pack', self._header_row()),
            ('pack', urwid.Divider("─")),
            ('weight', 1, self.list_box),
        ])

        self.transport_view = TransportFiller(self.pile, self)
        self.shortcuts_display = TransportDisplayShortcuts(self.app)
        self.widget = self.transport_view

        self._refresh_data()
        self._rebuild()

    def shortcuts(self):
        return self.shortcuts_display

    def _tab_bar(self):
        def tab(label, key):
            attr = "list_focus" if self.active_tab == key else "list_normal"
            return (urwid.PACK, urwid.Text((attr, " %s " % label)))

        return urwid.Columns([
            tab("Paths", "paths"),
            tab("Announce Rates", "rates"),
            tab("Interfaces", "interfaces"),
            (urwid.WEIGHT, 1, urwid.Text("")),
        ], dividechars=1)

    def _header_row(self):
        if self.active_tab == "paths":
            cols = [
                (self.HASH_W, urwid.Text(("key", "Destination"), wrap="clip")),
                (self.HOPS_W, urwid.Text(("key", "Hops"), wrap="clip")),
                (urwid.WEIGHT, 1, urwid.Text(("key", "Interface"), wrap="clip")),
                (self.VIA_W, urwid.Text(("key", "Via"), wrap="clip")),
                (self.EXP_W, urwid.Text(("key", "Expires"), wrap="clip")),
            ]
        elif self.active_tab == "interfaces":
            cols = [
                (urwid.WEIGHT, 1, urwid.Text(("key", "Interface"), wrap="clip")),
                (self.STATUS_W, urwid.Text(("key", "Status"), wrap="clip")),
                (self.PATHS_W, urwid.Text(("key", "Paths"), wrap="clip")),
                (self.HELD_W, urwid.Text(("key", "Held"), wrap="clip")),
                (self.QUEUE_W, urwid.Text(("key", "Queue"), wrap="clip")),
                (self.RATE_W, urwid.Text(("key", "Ann in"), wrap="clip")),
                (self.MODE_W, urwid.Text(("key", "Mode"), wrap="clip")),
            ]
        else:
            cols = [
                (self.HASH_W, urwid.Text(("key", "Destination"), wrap="clip")),
                (self.LAST_W, urwid.Text(("key", "Last announce"), wrap="clip")),
                (self.VIOL_W, urwid.Text(("key", "Violations"), wrap="clip")),
                (urwid.WEIGHT, 1, urwid.Text(("key", "Blocked"), wrap="clip")),
            ]
        return urwid.Columns(cols, dividechars=1)

    def _refresh_data(self):
        try:
            self.paths = self.app.rns.get_path_table() or []
        except Exception:
            self.paths = []
        try:
            self.rates = self.app.rns.get_rate_table() or []
        except Exception:
            self.rates = []
        try:
            self.link_count = self.app.rns.get_link_count()
        except Exception:
            self.link_count = 0

        try:
            stats = self.app.rns.get_interface_stats() or {}
        except Exception:
            stats = {}
        self.transport_id = stats.get("transport_id")
        self.network_id = stats.get("network_id")
        self.transport_uptime = stats.get("transport_uptime")
        self.interfaces = stats.get("interfaces", []) or []
        try:
            self.held_announces = sum(int(i.get("held_announces", 0) or 0) for i in self.interfaces)
        except Exception:
            self.held_announces = 0

        self.paths_per_interface = {}
        for entry in self.paths:
            iface = entry.get("interface", "")
            self.paths_per_interface[iface] = self.paths_per_interface.get(iface, 0) + 1

        try:
            self.interfaces.sort(key=lambda i: self.paths_per_interface.get(i.get("name", ""), 0), reverse=True)
        except Exception:
            pass

        try:
            self.paths.sort(key=lambda e: (e.get("interface", ""), e.get("hops", 0)))
        except Exception:
            pass
        try:
            self.rates.sort(key=lambda e: e.get("last", 0), reverse=True)
        except Exception:
            pass

    def _make_path_row(self, entry, position):
        dest = RNS.prettyhexrep(entry["hash"]) if entry.get("hash") else "?"
        via = RNS.prettyhexrep(entry["via"]) if entry.get("via") else "?"
        hops = entry.get("hops", 0)
        iface = entry.get("interface", "")
        expires = _rel_future(entry.get("expires", 0))

        columns = urwid.Columns([
            (self.HASH_W, urwid.Text(("list_normal", dest), wrap="clip")),
            (self.HOPS_W, urwid.Text(str(hops), wrap="clip")),
            (urwid.WEIGHT, 1, urwid.Text(iface, wrap="clip")),
            (self.VIA_W, urwid.Text(via, wrap="clip")),
            (self.EXP_W, urwid.Text(expires, wrap="clip")),
        ], dividechars=1)
        return TransportRow(columns)

    def _make_rate_row(self, entry, position):
        now = time.time()
        dest = RNS.prettyhexrep(entry["hash"]) if entry.get("hash") else "?"
        last = _rel_past(entry.get("last", 0))
        violations = str(entry.get("rate_violations", 0))
        blocked_until = entry.get("blocked_until", 0) or 0
        if blocked_until > now:
            blocked = ("disconnected_status", "blocked %s" % _rel_future(blocked_until))
        else:
            blocked = ("connected_status", "no")

        columns = urwid.Columns([
            (self.HASH_W, urwid.Text(("list_normal", dest), wrap="clip")),
            (self.LAST_W, urwid.Text(last, wrap="clip")),
            (self.VIOL_W, urwid.Text(violations, wrap="clip")),
            (urwid.WEIGHT, 1, urwid.Text(blocked, wrap="clip")),
        ], dividechars=1)
        return TransportRow(columns)

    def _make_iface_row(self, entry, position):
        short_name = entry.get("short_name")
        if short_name == "None": short_name = None
        name = short_name or entry.get("name") or "?"
        RNS.log(name)
        name = name.replace("\x00", "")
        paths = self.paths_per_interface.get(entry.get("name", ""), 0)
        held = entry.get("held_announces", 0) or 0
        queue = entry.get("announce_queue")
        queue_str = "-" if queue is None else str(queue)
        rate = _fmt_rate(entry.get("incoming_announce_frequency", 0))
        mode = _mode_str(entry.get("mode"))

        if entry.get("status"):
            status = ("connected_status", "up")
        else:
            status = ("disconnected_status", "down")

        columns = urwid.Columns([
            (urwid.WEIGHT, 1, urwid.Text(("list_normal", name), wrap="clip")),
            (self.STATUS_W, urwid.Text(status, wrap="clip")),
            (self.PATHS_W, urwid.Text(str(paths), wrap="clip")),
            (self.HELD_W, urwid.Text(str(held), wrap="clip")),
            (self.QUEUE_W, urwid.Text(queue_str, wrap="clip")),
            (self.RATE_W, urwid.Text(rate, wrap="clip")),
            (self.MODE_W, urwid.Text(mode, wrap="clip")),
        ], dividechars=1)
        return TransportRow(columns)

    def _rebuild(self):
        blocked_now = 0
        try:
            now = time.time()
            blocked_now = sum(1 for r in self.rates if (r.get("blocked_until", 0) or 0) > now)
        except Exception:
            pass

        transport_id = RNS.prettyhexrep(self.transport_id) if self.transport_id else "n/a"
        network_id = RNS.prettyhexrep(self.network_id) if self.network_id else "n/a"
        uptime = _fmt_duration(self.transport_uptime)

        summary = [
            ("key", "Transport ID: "), ("value", transport_id),
            ("key", "   Network ID: "), ("value", network_id),
            ("key", "   Uptime: "), ("value", uptime), "\n",
            ("key", "Active links: "), ("value", str(self.link_count)),
            ("key", "   Known paths: "), ("value", str(len(self.paths))),
            ("key", "   Held announces: "), ("value", str(self.held_announces)),
            ("key", "   Announce sources: "), ("value", str(len(self.rates))),
            ("key", "   Rate-limited: "), ("value", str(blocked_now)),
        ]

        if self.active_tab == "paths":
            data = self._filtered(self.paths)
            factory = self._make_path_row
            empty_msg = "No paths in the routing table yet."
        elif self.active_tab == "interfaces":
            data = self._filtered(self.interfaces)
            factory = self._make_iface_row
            empty_msg = "No interface statistics available."
        else:
            data = self._filtered(self.rates)
            factory = self._make_rate_row
            empty_msg = "No announce rate data available."

        if self.filter_text.strip():
            summary.append(("inactive_text", "   [filter: %d shown]" % len(data)))
        self.summary_text.set_text(summary)

        self.pile.contents[1] = (self._tab_bar(), self.pile.options('pack'))
        self.pile.contents[3] = (self._header_row(), self.pile.options('pack'))

        empty = urwid.Text(("inactive_text", empty_msg), align=urwid.CENTER)
        self.list_walker.configure(data, factory, empty)

    def cycle_tab(self):
        order = ["paths", "rates", "interfaces"]
        i = order.index(self.active_tab) if self.active_tab in order else 0
        self.active_tab = order[(i + 1) % len(order)]
        self._rebuild()

    def _on_filter_change(self, widget, new_text):
        self.filter_text = new_text
        self._rebuild()

    def _haystack(self, entry):
        parts = []
        for key in ("hash", "via"):
            value = entry.get(key)
            if value:
                parts.append(RNS.prettyhexrep(value))
        for key in ("interface", "name", "short_name"):
            value = entry.get(key)
            if value:
                parts.append(str(value))
        return " ".join(parts).lower()

    def _filtered(self, items):
        needle = self.filter_text.strip().lower()
        if not needle:
            return items
        return [entry for entry in items if needle in self._haystack(entry)]

    def go_back(self):
        if self.parent is not None:
            self.parent.show_landing()

    def go_back_to_header(self):
        try:
            self.app.ui.main_display.frame.focus_position = "header"
        except Exception:
            pass

    def _is_visible(self):
        md = self.app.ui.main_display
        if self.parent is not None:
            return md.sub_displays.active_display is self.parent and getattr(self.parent, "active", None) == "transport"
        return md.sub_displays.active_display is self

    def refresh(self):
        self._refresh_data()
        self._rebuild()

    def start(self):
        self.started = True
        self._refresh_data()
        self._rebuild()
        if not self.poll_scheduler and self.app.ui.loop is not None:
            self.poll_scheduler = True
            self.app.ui.loop.set_alarm_in(self.POLL_INTERVAL, self._poll)

    def _poll(self, loop, user_data):
        if not self.started or not self._is_visible():
            self.poll_scheduler = False
            return
        self._refresh_data()
        self._rebuild()
        try:
            loop.draw_screen()
        except Exception:
            pass
        loop.set_alarm_in(self.POLL_INTERVAL, self._poll)
