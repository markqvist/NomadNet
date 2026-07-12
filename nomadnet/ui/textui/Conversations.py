import RNS
import RNS.vendor.umsgpack as msgpack
import collections
import os
import shutil
import time
import nomadnet
import LXMF

import urwid

from datetime import datetime, timedelta
from nomadnet.Directory import DirectoryEntry
from LXMF import pn_announce_data_is_valid, PN_META_NAME
from nomadnet.Conversation import ConversationMessage
from .FileBrowser import FileBrowser

from nomadnet.util import strip_modifiers
from nomadnet.util import sanitize_name

from RNS.Utilities.rngit.util import MarkdownToMicron
from RNS.Utilities.rngit.highlight import SyntaxHighlighter
from .MicronParser import markup_to_attrmaps
from .Helpers import ClickableIcon, osc52_copy, qr_ascii
from .ReadlineEdit import ReadlineMixin, ReadlineEdit
from nomadnet.util import strip_modifiers, strip_micron, strip_escaped_micron, unescape_micron, strip_non_formatting_tags
from nomadnet.ui import THEME_DARK, THEME_LIGHT

def relative_time(timestamp):
    now = time.time()
    delta = now - timestamp
    if delta < 0:
        return "just now"
    elif delta < 60:
        return "just now"
    elif delta < 3600:
        m = int(delta / 60)
        return str(m)+"m ago"
    elif delta < 86400:
        h = int(delta / 3600)
        return str(h)+"h ago"
    elif delta < 172800:
        return "yesterday"
    elif delta < 604800:
        d = int(delta / 86400)
        return str(d)+"d ago"
    elif delta < 2592000:
        w = int(delta / 604800)
        return str(w)+"w ago"
    else:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


def _format_size(size):
    if size < 1024:
        return str(size)+" B"
    elif size < 1048576:
        return str(round(size/1024, 1))+" KB"
    else:
        return str(round(size/1048576, 1))+" MB"


from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox

class ConversationListDisplayShortcuts():
    def __init__(self, app):
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("[C-e] Peer Info  [C-x] Delete  [C-r] Sync  [C-n] New  [C-u] Ingest URI  [C-o] Sort  [C-p] My LXMF  [C-g] Fullscreen"), "shortcutbar")

class ConversationDisplayShortcuts():
    def __init__(self, app):
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("[C-d] Send  [C-p] Paper Msg  [C-t] Title  [C-f] Attach  [C-v] Delivery  [C-r] Details  [C-s] Save  [Tab] ↑ Messages"), "shortcutbar")

class ConversationBodyShortcuts():
    def __init__(self, app):
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("[C-r] Details  [C-v] Delivery  [C-o] Sort  [C-s] Save  [C-u] Purge  [C-k] Cancel Send  [C-x] Clear History  [C-g] Fullscreen  [C-w] Close  [Tab] ↓ Editor"), "shortcutbar")

class TabButton(urwid.Button):
    button_left  = urwid.Text("[")
    button_right = urwid.Text("]")


class ConversationsArea(urwid.LineBox):
    def keypress(self, size, key):
        if key == "ctrl e":
            self.delegate.edit_selected_in_directory()
        elif key == "ctrl x":
            self.delegate.delete_selected_conversation()
        elif key == "ctrl n":
            self.delegate.new_conversation()
        elif key == "ctrl u":
            self.delegate.ingest_lxm_uri()
        elif key == "ctrl r":
            self.delegate.sync_conversations()
        elif key == "ctrl g":
            self.delegate.toggle_fullscreen()
        elif key == "ctrl o":
            self.delegate.toggle_list_sort()
        elif key == "ctrl p":
            self.delegate.show_my_qr()
        elif key == "tab":
            self.delegate.app.ui.main_display.frame.focus_position = "header"
        elif key == "up":
            if self.delegate.ilb.body_is_empty():
                self.delegate.app.ui.main_display.frame.focus_position = "header"
                return None
            result = super(ConversationsArea, self).keypress(size, key)
            if result == "up":
                self.delegate.app.ui.main_display.frame.focus_position = "header"
                return None
            return result
        else:
            return super(ConversationsArea, self).keypress(size, key)

class PropNodePicker(urwid.WidgetWrap):
    def __init__(self, options, current_hash, on_change):
        self._options = list(options)
        self._current = current_hash
        self._on_change = on_change
        self._pile = urwid.Pile([])
        super().__init__(self._pile)
        self._show_collapsed()

    def _label_for(self, h):
        for ph, label in self._options:
            if ph == h:
                return label
        if h is not None:
            return "<"+RNS.hexrep(h, delimit=False)+">"
        return "(select propagation node)"

    def _show_collapsed(self):
        btn = urwid.Button("▾  "+self._label_for(self._current))
        urwid.connect_signal(btn, "click", self._on_expand_click)
        self._pile.contents = [
            (urwid.AttrMap(btn, None, focus_map="list_focus"), self._pile.options()),
        ]

    def _on_expand_click(self, _btn):
        self._show_expanded()

    def _on_back_click(self, _btn):
        self._show_collapsed()

    def _make_row_click(self, picked_hash):
        def _click(_btn):
            try:
                self._current = picked_hash
                self._on_change(picked_hash)
            except Exception as e:
                RNS.log("Propagation node change handler failed: "+str(e), RNS.LOG_ERROR)
            self._show_collapsed()
        return _click

    def _show_expanded(self):
        rows = []
        for ph, label in self._options:
            marker = "● " if ph == self._current else "○ "
            row = urwid.Button(marker+label)
            urwid.connect_signal(row, "click", self._make_row_click(ph))
            rows.append(urwid.AttrMap(row, None, focus_map="list_focus"))

        if not rows:
            rows.append(urwid.Text(" (no propagation nodes seen yet)"))

        list_height = min(10, max(3, len(rows)))
        listbox = urwid.ListBox(urwid.SimpleFocusListWalker(rows))
        boxed = urwid.BoxAdapter(listbox, list_height)

        back = urwid.Button("◀  Back")
        urwid.connect_signal(back, "click", self._on_back_click)

        self._pile.contents = [
            (urwid.AttrMap(back, None, focus_map="list_focus"), self._pile.options()),
            (boxed, self._pile.options()),
        ]


class DialogLineBox(urwid.LineBox):
    def keypress(self, size, key):
        if key == "esc":
            if hasattr(self.delegate, "update_conversation_list"):
                self.delegate.update_conversation_list()
            elif hasattr(self.delegate, "dialog_active"):
                self.delegate.dialog_active = False
                self.delegate.conversation_changed(None)
        else:
            return super(DialogLineBox, self).keypress(size, key)

class ConversationsDisplay():
    list_width = 0.33
    given_list_width = 52
    cached_conversation_widgets = {}

    SORT_RECENT = 0
    SORT_NAME   = 1

    LIST_FILTER_TRUSTED   = "trusted"
    LIST_FILTER_UNTRUSTED = "untrusted"

    def __init__(self, app):
        self.app = app
        self.dialog_open = False
        self.sync_dialog = None
        self.currently_displayed_conversation = None
        self.list_sort_mode = ConversationsDisplay.SORT_RECENT
        self.list_filter = ConversationsDisplay.LIST_FILTER_TRUSTED
        self.show_blocked = False

        def disp_list_shortcuts(sender, arg1, arg2):
            self.shortcuts_display = self.list_shortcuts
            self.app.ui.main_display.update_active_shortcuts()

        self._build_persistent_listbox()
        self.update_listbox()

        self.columns_widget = urwid.Columns(
            [
                # (urwid.WEIGHT, ConversationsDisplay.list_width, self.listbox),
                # (urwid.WEIGHT, 1-ConversationsDisplay.list_width, self.make_conversation_widget(None))
                (ConversationsDisplay.given_list_width, self.listbox),
                (urwid.WEIGHT, 1, self.make_conversation_widget(None))
            ],
            dividechars=0, focus_column=0, box_columns=[0]
        )

        self.list_shortcuts = ConversationListDisplayShortcuts(self.app)
        self.editor_shortcuts = ConversationDisplayShortcuts(self.app)
        self.body_shortcuts = ConversationBodyShortcuts(self.app)

        self.shortcuts_display = self.list_shortcuts
        self.widget = urwid.WidgetPlaceholder(self.columns_widget)

        self._pending_actions = collections.deque()
        self._wake_fd = None
        try:
            self._wake_fd = self.app.ui.loop.watch_pipe(self._process_pending)
        except Exception:
            pass

        nomadnet.Conversation.created_callback = lambda: self._wake(self.update_conversation_list)

        try:
            self.app.ui.loop.set_alarm_in(30.0, self._refresh_sync_status)
        except Exception:
            pass

    def _process_pending(self, data):
        while True:
            try:
                action = self._pending_actions.popleft()
            except IndexError:
                break
            try:
                action()
            except Exception as e:
                RNS.log("Conversations UI action failed: "+str(e), RNS.LOG_ERROR)
        return True

    def _wake(self, action):
        self._pending_actions.append(action)
        if self._wake_fd is not None:
            try:
                os.write(self._wake_fd, b".")
                return
            except Exception:
                pass
        try:
            self.app.ui.loop.set_alarm_in(0.0, lambda l, d: self._process_pending(None))
        except Exception:
            pass

    def focus_change_event(self):
        if not self.dialog_open:
            self.update_conversation_list()

    def toggle_list_sort(self):
        if self.list_sort_mode == ConversationsDisplay.SORT_RECENT:
            self.list_sort_mode = ConversationsDisplay.SORT_NAME
        else:
            self.list_sort_mode = ConversationsDisplay.SORT_RECENT
        self.update_conversation_list()

    def _conversation_filter_predicate(self, conversation):
        try:
            trust_level = conversation[2]
        except Exception:
            return False
        if self.list_filter == ConversationsDisplay.LIST_FILTER_UNTRUSTED:
            return trust_level in (DirectoryEntry.UNTRUSTED, DirectoryEntry.WARNING, DirectoryEntry.UNKNOWN)
        return trust_level == DirectoryEntry.TRUSTED

    def _set_filter(self, key):
        if self.list_filter == key:
            return
        self.list_filter = key
        try:
            self.update_conversation_list()
        except Exception as e:
            RNS.log("Failed to apply conversation filter: "+str(e), RNS.LOG_ERROR)

    def _on_show_blocked_change(self, _cb, new_state):
        self.show_blocked = new_state
        try:
            self.update_conversation_list()
        except Exception as e:
            RNS.log("Failed to toggle show-blocked: "+str(e), RNS.LOG_ERROR)

    def _apply_pile_layout(self):
        pack_opts   = self.pile.options('pack')
        weight_opts = self.pile.options('weight', 1)
        items = [(self.tab_bar, pack_opts)]
        if self.list_filter == ConversationsDisplay.LIST_FILTER_UNTRUSTED:
            items.append((self.show_blocked_checkbox, pack_opts))
        items.append((self.ilb, weight_opts))
        items.append((self.sync_status_text, pack_opts))
        try:
            prev_focus = self.pile.focus_position
        except Exception:
            prev_focus = None
        self.pile.contents = items
        try:
            if prev_focus is not None and prev_focus < len(items):
                self.pile.focus_position = prev_focus
        except Exception:
            pass

    def _blocked_row_widget(self, dest_hash):
        g = self.app.ui.glyphs
        entry = self.app.directory.find(dest_hash)
        display_name = None
        if entry is not None and getattr(entry, "display_name", None):
            display_name = strip_modifiers(entry.display_name)
        if not display_name:
            display_name = RNS.prettyhexrep(dest_hash)
        label = " "+g["cross"]+" [blocked] "+display_name+"  <"+RNS.hexrep(dest_hash, delimit=False)+">"
        widget = ListEntry(label)
        urwid.connect_signal(widget, "click", self._unblock_dialog, dest_hash)
        attr = urwid.AttrMap(widget, "list_untrusted", "list_focus_untrusted")
        attr.blocked_dest_hash = dest_hash
        return attr

    def _unblock_dialog(self, _sender, dest_hash):
        self.dialog_open = True

        def dismiss(_b):
            self.dialog_open = False
            self.update_conversation_list()

        def confirmed(_b):
            self.dialog_open = False
            try:
                self.app.unblock_destination(dest_hash)
            except Exception as e:
                RNS.log("Unblock failed: "+str(e), RNS.LOG_ERROR)
            self.update_conversation_list()

        try:
            who = self.app.directory.simplest_display_str(dest_hash)
        except Exception:
            who = RNS.hexrep(dest_hash, delimit=False)

        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text(""),
                urwid.Text("Unblock "+str(who)+"?\n\nThis lifts the RNS blackhole on the peer's identity\nand removes them from your ignored list.\n", align=urwid.CENTER),
                urwid.Columns([
                    (urwid.WEIGHT, 0.45, urwid.Button("Yes, unblock", on_press=confirmed)),
                    (urwid.WEIGHT, 0.10, urwid.Text("")),
                    (urwid.WEIGHT, 0.45, urwid.Button("Cancel",       on_press=dismiss)),
                ]),
            ]), title="Confirm unblock"
        )
        dialog.delegate = self

        bottom = self.listbox
        overlay = urwid.Overlay(dialog, bottom, align=urwid.CENTER, width=urwid.RELATIVE_100, valign=urwid.MIDDLE, height=urwid.PACK, left=2, right=2)
        try:
            self.columns_widget.contents[0] = (
                overlay,
                self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width),
            )
            self.columns_widget.focus_position = 0
        except Exception:
            pass

    def _build_persistent_listbox(self):
        self.tab_trusted   = TabButton("Trusted (0)",   on_press=lambda _b: self._set_filter(ConversationsDisplay.LIST_FILTER_TRUSTED))
        self.tab_untrusted = TabButton("Untrusted (0)", on_press=lambda _b: self._set_filter(ConversationsDisplay.LIST_FILTER_UNTRUSTED))

        self.tab_bar = urwid.Columns([
            ('weight', 1, self.tab_trusted),
            ('weight', 1, self.tab_untrusted),
        ], dividechars=1)

        self.show_blocked_checkbox = urwid.CheckBox("Show blocked (0)", state=self.show_blocked)
        urwid.connect_signal(self.show_blocked_checkbox, "change", self._on_show_blocked_change)

        self.ilb = IndicativeListBox(
            [urwid.Text("")],
            on_selection_change=self.conversation_list_selection,
            initialization_is_selection_change=False,
            highlight_offFocus="list_off_focus",
        )

        self.sync_status_text = urwid.AttrMap(urwid.Text(self._sync_status_line(), align=urwid.LEFT), "shortcutbar")

        self.pile = urwid.Pile([
            ('pack', self.tab_bar),
            ('weight', 1, self.ilb),
            ('pack', self.sync_status_text),
        ])
        try: self.pile.focus_position = 1
        except Exception: pass

        self.listbox = ConversationsArea(self.pile, title="Conversations")
        self.listbox.delegate = self

    def update_listbox(self):
        if not hasattr(self, "pile"):
            self._build_persistent_listbox()

        try:
            conversations = self.app.conversations()
        except Exception as e:
            RNS.log("Failed to enumerate conversations: "+str(e), RNS.LOG_ERROR)
            conversations = []

        try:
            if self.list_sort_mode == ConversationsDisplay.SORT_NAME:
                conversations.sort(key=lambda e: (e[3].lower(), e[0]))
        except Exception:
            pass

        def _is_pinned(c):
            try:
                entry = self.app.directory.find(bytes.fromhex(c[0]))
                return entry is not None and entry.sort_rank is not None
            except Exception:
                return False
        try:
            conversations = sorted(conversations, key=lambda c: 0 if _is_pinned(c) else 1)
        except Exception:
            pass

        glyphs = self.app.ui.glyphs
        def _alerts(c):
            return bool(c[4]) or (len(c) > 6 and bool(c[6]))
        trusted_count    = sum(1 for c in conversations if c[2] == DirectoryEntry.TRUSTED)
        untrusted_count  = sum(1 for c in conversations if c[2] in (DirectoryEntry.UNTRUSTED, DirectoryEntry.WARNING, DirectoryEntry.UNKNOWN))
        trusted_unread   = sum(1 for c in conversations if c[2] == DirectoryEntry.TRUSTED and _alerts(c))
        untrusted_unread = sum(1 for c in conversations if c[2] in (DirectoryEntry.UNTRUSTED, DirectoryEntry.WARNING, DirectoryEntry.UNKNOWN) and _alerts(c))

        def _label(name, total, unread):
            if unread:
                return f"{name} ({total}) {glyphs['unread']} {unread}"
            return f"{name} ({total})"

        self.tab_trusted.set_label(_label("Trusted", trusted_count, trusted_unread))
        self.tab_untrusted.set_label(_label("Untrusted", untrusted_count, untrusted_unread))

        filtered = [c for c in conversations if self._conversation_filter_predicate(c)]

        conversation_list_widgets = []
        for conversation in filtered:
            try:
                conversation_list_widgets.append(self.conversation_list_widget(conversation))
            except Exception as e:
                try: hh = conversation[0]
                except Exception: hh = "?"
                RNS.log("Skipping conversation row for "+str(hh)+": "+str(e), RNS.LOG_ERROR)

        blocked_count = len(self.app.ignored_list) if hasattr(self.app, "ignored_list") else 0
        try:
            self.show_blocked_checkbox.set_label(f"Show blocked ({blocked_count})")
        except Exception:
            pass

        if self.list_filter == ConversationsDisplay.LIST_FILTER_UNTRUSTED and self.show_blocked:
            for blocked_hash in list(self.app.ignored_list):
                try:
                    conversation_list_widgets.append(self._blocked_row_widget(blocked_hash))
                except Exception as e:
                    RNS.log("Skipping blocked row: "+str(e), RNS.LOG_ERROR)

        empty_placeholder = False
        if not conversation_list_widgets:
            empty_label = {
                ConversationsDisplay.LIST_FILTER_TRUSTED:   "No trusted conversations",
                ConversationsDisplay.LIST_FILTER_UNTRUSTED: "No untrusted conversations",
            }.get(self.list_filter, "No conversations")
            conversation_list_widgets = [urwid.Text(empty_label, align='center')]
            empty_placeholder = True

        self.list_widgets = conversation_list_widgets

        try:
            self.ilb.set_body(conversation_list_widgets)
        except Exception as e:
            RNS.log("Failed to populate conversation list: "+str(e), RNS.LOG_ERROR)

        self._apply_pile_layout()

        if empty_placeholder:
            try: self.pile.focus_position = 0
            except Exception: pass

        try:
            self.sync_status_text.original_widget.set_text(self._sync_status_line())
        except Exception:
            pass

    def _sync_status_line(self):
        try:
            last = self.app.peer_settings.get("last_lxmf_sync")
        except Exception:
            last = None
        if not last:
            when = "never"
        else:
            try:
                when = relative_time(float(last))
            except Exception:
                when = "unknown"

        node_label = None
        try:
            pn_hash = self.app.get_default_propagation_node()
            if pn_hash is not None:
                pn_ident = RNS.Identity.recall(pn_hash)
                if pn_ident is not None:
                    node_dest = RNS.Destination.hash_from_name_and_identity("nomadnetwork.node", pn_ident)
                    entry = self.app.directory.find(node_dest)
                    if entry is not None and getattr(entry, "display_name", None):
                        node_label = strip_modifiers(str(entry.display_name)) or None
                if node_label is None:
                    node_label = "<"+RNS.hexrep(pn_hash, delimit=False)[:8]+"…>"
        except Exception:
            node_label = None

        line = " Last sync: "+when
        if node_label:
            line += "  ("+node_label+")"
        return line

    def _refresh_sync_status(self, _loop=None, _data=None):
        try:
            if hasattr(self, "sync_status_text") and self.sync_status_text is not None:
                self.sync_status_text.original_widget.set_text(self._sync_status_line())
        except Exception:
            pass
        try:
            self.app.ui.loop.set_alarm_in(30.0, self._refresh_sync_status)
        except Exception:
            pass

    def delete_selected_conversation(self):
        self.dialog_open = True
        item = self.ilb.get_selected_item()
        source_hash = getattr(item, "source_hash", None) if item is not None else None
        if source_hash is None:
            self.dialog_open = False
            return

        def dismiss_dialog(sender):
            self.dialog_open = False
            self.update_conversation_list()

        def confirmed(sender):
            self.dialog_open = False
            self.delete_conversation(source_hash)
            nomadnet.Conversation.delete_conversation(source_hash, self.app)
            self.update_conversation_list()

        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text(
                    "Delete conversation with\n"+self.app.directory.simplest_display_str(bytes.fromhex(source_hash))+"\n",
                    align=urwid.CENTER,
                ),
                urwid.Columns([
                    (urwid.WEIGHT, 0.45, urwid.Button("Yes", on_press=confirmed)),
                    (urwid.WEIGHT, 0.1, urwid.Text("")),
                    (urwid.WEIGHT, 0.45, urwid.Button("No", on_press=dismiss_dialog)),
                ])
            ]), title="?"
        )
        dialog.delegate = self
        bottom = self.listbox

        overlay = urwid.Overlay(
            dialog,
            bottom,
            align=urwid.CENTER,
            width=urwid.RELATIVE_100,
            valign=urwid.MIDDLE,
            height=urwid.PACK,
            left=2,
            right=2,
        )

        # options = self.columns_widget.options(urwid.WEIGHT, ConversationsDisplay.list_width)
        options = self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width)
        self.columns_widget.contents[0] = (overlay, options)

    def _refresh_open_conversation_widget(self, source_hash_text):
        widget = ConversationsDisplay.cached_conversation_widgets.get(source_hash_text)
        if widget is None:
            return
        try:
            widget._trust_banner_dismissed = False
        except Exception:
            pass
        try:
            widget._refresh_trust_banner()
        except Exception:
            pass
        try:
            widget._update_peer_info()
        except Exception:
            pass
        try:
            widget.update_message_widgets(replace=True)
        except Exception:
            pass

    def show_my_qr(self):
        try:
            addr = RNS.hexrep(self.app.lxmf_destination.hash, delimit=False)
        except Exception:
            return
        try:
            display = self.app.peer_settings.get("display_name") or "My LXMF"
        except Exception:
            display = "My LXMF"
        self.show_qr_dialog(addr, title=display)

    def show_qr_dialog(self, data, title=None):
        qr_text = qr_ascii(data)

        def dismiss(_b):
            self._restore_listbox_pane()

        rows = [urwid.Text("")]
        if qr_text is not None:
            rows.append(urwid.Text(qr_text, align=urwid.CENTER))
            rows.append(urwid.Text(""))
        else:
            rows.append(urwid.Text("LXMF destination address:", align=urwid.CENTER))
            rows.append(urwid.Text(""))
        rows += [
            urwid.Text("< "+data+" >", align=urwid.CENTER),
            urwid.Text(""),
            urwid.Columns([
                (urwid.WEIGHT, 1, urwid.Text("")),
                (12, urwid.Button("Close", on_press=dismiss)),
                (urwid.WEIGHT, 1, urwid.Text("")),
            ]),
            urwid.Text(""),
        ]
        dialog_title = "LXMF Address" if qr_text is None else "QR Code"
        dialog = DialogLineBox(urwid.Pile(rows), title=dialog_title)
        dialog.delegate = self
        self._overlay_dialog(dialog)

    def _overlay_dialog(self, dialog):
        overlay = urwid.Overlay(
            dialog, self.columns_widget,
            align=urwid.CENTER, width=(urwid.RELATIVE, 70),
            valign=urwid.MIDDLE, height=urwid.PACK,
            min_width=44,
        )
        try:
            self.widget.original_widget = overlay
            self.dialog_open = True
        except Exception:
            pass

    def _restore_listbox_pane(self):
        try:
            self.widget.original_widget = self.columns_widget
            self.dialog_open = False
            self.update_conversation_list()
        except Exception:
            pass

    def _ping_peer_from_dialog(self, source_hash_text, status_widget, ping_button):
        try:
            dest = bytes.fromhex(source_hash_text)
        except Exception:
            status_widget.set_text(("error_text", "Invalid address"))
            return

        identity = RNS.Identity.recall(dest)
        if identity is None:
            status_widget.set_text(("error_text", "Identity unknown; query first"))
            return

        if not RNS.Transport.has_path(dest):
            status_widget.set_text("No path; requesting…")
            try: RNS.Transport.request_path(dest)
            except Exception: pass

        status_widget.set_text("Pinging…")
        ping_button.set_label("Pinging…")
        started_at = time.time()

        def schedule_ui(fn):
            try:
                self.app.ui.loop.set_alarm_in(0, lambda *_: fn())
            except Exception:
                try: fn()
                except Exception: pass

        def on_established(link):
            elapsed_ms = int((time.time() - started_at) * 1000)
            try:
                hops = RNS.Transport.hops_to(dest)
                if hops is None or hops >= RNS.Transport.PATHFINDER_M:
                    hops_str = ""
                else:
                    hops_str = f" ({hops} hop{'s' if hops != 1 else ''})"
            except Exception:
                hops_str = ""
            def update():
                status_widget.set_text(f"Pong in {elapsed_ms} ms{hops_str}")
                ping_button.set_label("Ping")
            schedule_ui(update)
            try: link.teardown()
            except Exception: pass

        def on_closed(link):
            try:
                if getattr(link, "status", None) == RNS.Link.ACTIVE:
                    return
            except Exception:
                pass
            def update():
                if status_widget.text.strip() in ("Pinging…", ""):
                    status_widget.set_text(("error_text", "Ping failed (no link)"))
                    ping_button.set_label("Ping")
            schedule_ui(update)

        try:
            destination = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
            RNS.Link(destination, established_callback=on_established, closed_callback=on_closed)
        except Exception as e:
            status_widget.set_text(("error_text", f"Ping init failed: {e}"))
            ping_button.set_label("Ping")

    def _block_peer_from_dialog(self, source_hash_text):
        try:
            dest = bytes.fromhex(source_hash_text)
        except Exception:
            return

        def cancel_block(_b):
            self.dialog_open = False
            self.update_conversation_list()

        def confirm_block(_b):
            try:
                self.app.block_destination(dest, reason="user-blocked from peer info dialog")
            except Exception as e:
                RNS.log("Block failed: "+str(e), RNS.LOG_ERROR)
            try:
                self.delete_conversation(source_hash_text)
                nomadnet.Conversation.delete_conversation(source_hash_text, self.app)
            except Exception:
                pass
            self.dialog_open = False
            self.update_conversation_list()

        try:
            who = self.app.directory.simplest_display_str(dest)
        except Exception:
            who = source_hash_text

        confirm_dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text(""),
                urwid.Text("Block "+str(who)+"?\n\nThis blackholes the peer's identity in Reticulum,\nadds them to your ignored list, and deletes any\nconversation with them.\n", align=urwid.CENTER),
                urwid.Columns([
                    (urwid.WEIGHT, 0.45, urwid.Button("Yes, block", on_press=confirm_block)),
                    (urwid.WEIGHT, 0.10, urwid.Text("")),
                    (urwid.WEIGHT, 0.45, urwid.Button("Cancel",     on_press=cancel_block)),
                ]),
            ]), title="Confirm block"
        )
        confirm_dialog.delegate = self
        bottom = self.listbox
        overlay = urwid.Overlay(confirm_dialog, bottom, align=urwid.CENTER, width=urwid.RELATIVE_100, valign=urwid.MIDDLE, height=urwid.PACK, left=2, right=2)
        try:
            self.columns_widget.contents[0] = (
                overlay,
                self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width),
            )
            self.columns_widget.focus_position = 0
            self.dialog_open = True
        except Exception:
            pass

    def edit_selected_in_directory(self):
        g = self.app.ui.glyphs
        self.dialog_open = True
        item = self.ilb.get_selected_item()
        if item == None:
            self.dialog_open = False
            return
        source_hash_text = getattr(item, "source_hash", None)
        if source_hash_text is None:
            blocked = getattr(item, "blocked_dest_hash", None)
            if isinstance(blocked, (bytes, bytearray)):
                source_hash_text = RNS.hexrep(blocked, delimit=False)
        if source_hash_text is None:
            self.dialog_open = False
            return
        display_name = getattr(item, "display_name", None)
        if display_name is None:
            try:
                display_name = self.app.directory.display_name(bytes.fromhex(source_hash_text))
            except Exception:
                display_name = None
        if display_name is None:
            display_name = ""

        e_id = ReadlineEdit(caption="Addr : ",edit_text=source_hash_text)
        t_id = urwid.Text("Addr : "+source_hash_text)
        e_name = ReadlineEdit(caption="Name : ",edit_text=display_name)
        e_copy = ReadlineEdit(caption="Copy : ", edit_text=source_hash_text)

        selected_id_widget = t_id

        untrusted_selected  = False
        unknown_selected    = True
        trusted_selected    = False

        direct_selected        = True
        propagated_selected    = False
        opportunistic_selected = False

        pinned_initial = False
        notes_initial  = ""

        try:
            existing_entry = self.app.directory.find(bytes.fromhex(source_hash_text))
            if existing_entry:
                trust_level = self.app.directory.trust_level(bytes.fromhex(source_hash_text))
                if trust_level == DirectoryEntry.UNTRUSTED:
                    untrusted_selected = True
                    unknown_selected   = False
                    trusted_selected   = False
                elif trust_level == DirectoryEntry.UNKNOWN:
                    untrusted_selected = False
                    unknown_selected   = True
                    trusted_selected   = False
                elif trust_level == DirectoryEntry.TRUSTED:
                    untrusted_selected = False
                    unknown_selected   = False
                    trusted_selected   = True

                preferred = self.app.directory.preferred_delivery(bytes.fromhex(source_hash_text))
                if preferred == DirectoryEntry.PROPAGATED:
                    direct_selected = False
                    propagated_selected = True
                elif preferred == DirectoryEntry.OPPORTUNISTIC:
                    direct_selected = False
                    opportunistic_selected = True

                pinned_initial = existing_entry.sort_rank is not None
                notes_initial  = getattr(existing_entry, "notes", "") or ""

        except Exception as e:
            pass

        e_notes = ReadlineEdit(caption="Notes: ", edit_text=notes_initial, multiline=True)
        cb_pin  = urwid.CheckBox("Pin to top", state=pinned_initial)

        trust_button_group = []
        r_untrusted = urwid.RadioButton(trust_button_group, "Untrusted", state=untrusted_selected)
        r_unknown   = urwid.RadioButton(trust_button_group, "Unknown", state=unknown_selected)
        r_trusted   = urwid.RadioButton(trust_button_group, "Trusted", state=trusted_selected)

        method_button_group = []
        r_direct        = urwid.RadioButton(method_button_group, "Deliver over direct link", state=direct_selected)
        r_opportunistic = urwid.RadioButton(method_button_group, "Deliver opportunistically", state=opportunistic_selected)
        r_propagated    = urwid.RadioButton(method_button_group, "Use propagation nodes", state=propagated_selected)

        def dismiss_dialog(sender):
            self.dialog_open = False
            self.update_conversation_list()

        def confirmed(sender):
            try:
                display_name = e_name.get_edit_text()
                source_hash = bytes.fromhex(e_id.get_edit_text())
                trust_level = DirectoryEntry.UNTRUSTED
                if r_unknown.state == True:
                    trust_level = DirectoryEntry.UNKNOWN
                elif r_trusted.state == True:
                    trust_level = DirectoryEntry.TRUSTED

                delivery = DirectoryEntry.DIRECT
                if r_propagated.state == True:
                    delivery = DirectoryEntry.PROPAGATED
                elif r_opportunistic.state == True:
                    delivery = DirectoryEntry.OPPORTUNISTIC

                sort_rank = 0 if cb_pin.state else None
                notes_value = e_notes.get_edit_text()
                entry = DirectoryEntry(source_hash, display_name, trust_level, preferred_delivery=delivery, sort_rank=sort_rank, notes=notes_value)
                self.app.directory.remember(entry)
                self._refresh_open_conversation_widget(source_hash_text)
                self.dialog_open = False
                self.update_conversation_list()
                self.app.ui.main_display.sub_displays.network_display.directory_change_callback()
            except Exception as e:
                RNS.log("Could not save directory entry. The contained exception was: "+str(e), RNS.LOG_VERBOSE)
                if not dialog_pile.error_display:
                    dialog_pile.error_display = True
                    options = dialog_pile.options(height_type=urwid.PACK)
                    dialog_pile.contents.append((urwid.Text(""), options))
                    dialog_pile.contents.append((
                        urwid.Text(("error_text", "Could not save entry. Check your input."), align=urwid.CENTER),
                        options,)
                    )

        source_is_known = self.app.directory.is_known(bytes.fromhex(source_hash_text))
        if source_is_known:
            known_section = urwid.Divider(g["divider1"])
        else:
            def query_action(sender, user_data):
                self.close_conversation_by_hash(user_data)
                nomadnet.Conversation.query_for_peer(user_data)
                options = dialog_pile.options(height_type=urwid.PACK)
                dialog_pile.contents = [
                    (urwid.Text("Query sent"), options),
                    (urwid.Button("OK", on_press=dismiss_dialog), options)
                ]
            query_button = urwid.Button("Query network for keys", on_press=query_action, user_data=source_hash_text)
            known_section = urwid.Pile([
                urwid.Divider(g["divider1"]),
                urwid.Text(g["info"]+"\n", align=urwid.CENTER),
                urwid.Text(
                    "The identity of this peer is not known, and you cannot currently send messages to it. "
                    "You can query the network to obtain the identity.\n",
                    align=urwid.CENTER,
                ),
                query_button,
                urwid.Divider(g["divider1"]),
            ])

        action_status = urwid.Text("", align=urwid.CENTER)
        ping_button   = urwid.Button("Ping")
        block_button  = urwid.Button("Block")
        qr_button     = urwid.Button("LXMF")
        urwid.connect_signal(ping_button,  "click", lambda _b: self._ping_peer_from_dialog(source_hash_text, action_status, ping_button))
        urwid.connect_signal(block_button, "click", lambda _b: self._block_peer_from_dialog(source_hash_text))
        urwid.connect_signal(qr_button,    "click", lambda _b: self.show_qr_dialog(source_hash_text, title=display_name or source_hash_text))

        actions_row = urwid.Columns([
            (urwid.WEIGHT, 0.32, ping_button),
            (urwid.WEIGHT, 0.02, urwid.Text("")),
            (urwid.WEIGHT, 0.32, block_button),
            (urwid.WEIGHT, 0.02, urwid.Text("")),
            (urwid.WEIGHT, 0.32, qr_button),
        ])

        dialog_pile = urwid.Pile([
            selected_id_widget,
            e_name,
            e_copy,
            urwid.Divider(g["divider1"]),
            r_untrusted,
            r_unknown,
            r_trusted,
            urwid.Divider(g["divider1"]),
            r_direct,
            r_opportunistic,
            r_propagated,
            urwid.Divider(g["divider1"]),
            cb_pin,
            e_notes,
            known_section,
            actions_row,
            action_status,
            urwid.Divider(g["divider1"]),
            urwid.Columns([
                (urwid.WEIGHT, 0.45, urwid.Button("Save", on_press=confirmed)),
                (urwid.WEIGHT, 0.1, urwid.Text("")),
                (urwid.WEIGHT, 0.45, urwid.Button("Back", on_press=dismiss_dialog)),
            ])
        ])
        dialog_pile.error_display = False

        dialog = DialogLineBox(dialog_pile, title="Peer Info")
        dialog.delegate = self
        bottom = self.listbox

        overlay = urwid.Overlay(
            dialog,
            bottom,
            align=urwid.CENTER,
            width=urwid.RELATIVE_100,
            valign=urwid.MIDDLE,
            height=urwid.PACK,
            left=2,
            right=2,
        )

        # options = self.columns_widget.options(urwid.WEIGHT, ConversationsDisplay.list_width)
        options = self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width)
        self.columns_widget.contents[0] = (overlay, options)

    def new_conversation(self):
        self.dialog_open = True
        source_hash = ""
        display_name = ""

        e_id = ReadlineEdit(caption="Addr : ",edit_text=source_hash)
        e_name = ReadlineEdit(caption="Name : ",edit_text=display_name)

        trust_button_group = []
        r_untrusted = urwid.RadioButton(trust_button_group, "Untrusted")
        r_unknown   = urwid.RadioButton(trust_button_group, "Unknown", state=True)
        r_trusted   = urwid.RadioButton(trust_button_group, "Trusted")

        def dismiss_dialog(sender):
            self.dialog_open = False
            self.update_conversation_list()

        def confirmed(sender):
            try:
                existing_conversations = nomadnet.Conversation.conversation_list(self.app)
                
                display_name = e_name.get_edit_text()
                source_hash_text = e_id.get_edit_text().strip()
                source_hash = bytes.fromhex(source_hash_text)
                trust_level = DirectoryEntry.UNTRUSTED
                if r_unknown.state == True:
                    trust_level = DirectoryEntry.UNKNOWN
                elif r_trusted.state == True:
                    trust_level = DirectoryEntry.TRUSTED

                if not source_hash_text in [c[0] for c in existing_conversations]:
                    entry = DirectoryEntry(source_hash, display_name, trust_level)
                    self.app.directory.remember(entry)

                    new_conversation = nomadnet.Conversation(source_hash_text, nomadnet.NomadNetworkApp.get_shared_instance(), initiator=True)

                    self.update_conversation_list()

                if trust_level != DirectoryEntry.TRUSTED:
                    if self.list_filter != ConversationsDisplay.LIST_FILTER_UNTRUSTED:
                        self._set_filter(ConversationsDisplay.LIST_FILTER_UNTRUSTED)
                self.display_conversation(None, source_hash_text)
                self.dialog_open = False
                self.update_conversation_list()

            except Exception as e:
                RNS.log("Could not start conversation. The contained exception was: "+str(e), RNS.LOG_VERBOSE)
                if not dialog_pile.error_display:
                    dialog_pile.error_display = True
                    options = dialog_pile.options(height_type=urwid.PACK)
                    dialog_pile.contents.append((urwid.Text(""), options))
                    dialog_pile.contents.append((
                        urwid.Text(
                            ("error_text", "Could not start conversation. Check your input."),
                            align=urwid.CENTER,
                        ),
                        options,
                    ))

        dialog_pile = urwid.Pile([
            e_id,
            e_name,
            urwid.Text(""),
            r_untrusted,
            r_unknown,
            r_trusted,
            urwid.Text(""),
            urwid.Columns([
                (urwid.WEIGHT, 0.45, urwid.Button("Create", on_press=confirmed)),
                (urwid.WEIGHT, 0.1, urwid.Text("")),
                (urwid.WEIGHT, 0.45, urwid.Button("Back", on_press=dismiss_dialog)),
            ])
        ])
        dialog_pile.error_display = False

        dialog = DialogLineBox(dialog_pile, title="New Conversation")
        dialog.delegate = self
        bottom = self.listbox

        overlay = urwid.Overlay(
            dialog,
            bottom,
            align=urwid.CENTER,
            width=urwid.RELATIVE_100,
            valign=urwid.MIDDLE,
            height=urwid.PACK,
            left=2,
            right=2,
        )

        # options = self.columns_widget.options(urwid.WEIGHT, ConversationsDisplay.list_width)
        options = self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width)
        self.columns_widget.contents[0] = (overlay, options)

    def ingest_lxm_uri(self):
        self.dialog_open = True
        lxm_uri = ""
        e_uri = ReadlineEdit(caption="URI : ",edit_text=lxm_uri)

        def dismiss_dialog(sender):
            self.dialog_open = False
            self.update_conversation_list()

        def confirmed(sender):
            try:
                local_delivery_signal = "local_delivery_occurred"
                duplicate_signal = "duplicate_lxm"
                lxm_uri = e_uri.get_edit_text().strip()

                ingest_result = self.app.message_router.ingest_lxm_uri(
                    lxm_uri,
                    signal_local_delivery=local_delivery_signal,
                    signal_duplicate=duplicate_signal
                )

                if ingest_result == False:
                    raise ValueError("The URI contained no decodable messages")
                
                elif ingest_result == local_delivery_signal:
                    rdialog_pile = urwid.Pile([
                        urwid.Text("Message was decoded, decrypted successfully, and added to your conversation list."),
                        urwid.Text(""),
                        urwid.Columns([
                            (urwid.WEIGHT, 0.6, urwid.Text("")),
                            (urwid.WEIGHT, 0.4, urwid.Button("OK", on_press=dismiss_dialog)),
                        ])
                    ])
                    rdialog_pile.error_display = False

                    rdialog = DialogLineBox(rdialog_pile, title="Ingest message URI")
                    rdialog.delegate = self
                    bottom = self.listbox

                    roverlay = urwid.Overlay(
                        rdialog,
                        bottom,
                        align=urwid.CENTER,
                        width=urwid.RELATIVE_100,
                        valign=urwid.MIDDLE,
                        height=urwid.PACK,
                        left=2,
                        right=2,
                    )

                    options = self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width)
                    self.columns_widget.contents[0] = (roverlay, options)
                
                elif ingest_result == duplicate_signal:
                    rdialog_pile = urwid.Pile([
                        urwid.Text("The decoded message has already been processed by the LXMF Router, and will not be ingested again."),
                        urwid.Text(""),
                        urwid.Columns([
                            (urwid.WEIGHT, 0.6, urwid.Text("")),
                            (urwid.WEIGHT, 0.4, urwid.Button("OK", on_press=dismiss_dialog)),
                        ])
                    ])
                    rdialog_pile.error_display = False

                    rdialog = DialogLineBox(rdialog_pile, title="Ingest message URI")
                    rdialog.delegate = self
                    bottom = self.listbox

                    roverlay = urwid.Overlay(
                        rdialog,
                        bottom,
                        align=urwid.CENTER,
                        width=urwid.RELATIVE_100,
                        valign=urwid.MIDDLE,
                        height=urwid.PACK,
                        left=2,
                        right=2,
                    )

                    options = self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width)
                    self.columns_widget.contents[0] = (roverlay, options)
                
                else:
                    if self.app.enable_node:
                        propagation_text = "The decoded message was not addressed to this LXMF address, but has been added to the propagation node queues, and will be distributed on the propagation network."
                    else:
                        propagation_text = "The decoded message was not addressed to this LXMF address, and has been discarded."

                    rdialog_pile = urwid.Pile([
                        urwid.Text(propagation_text),
                        urwid.Text(""),
                        urwid.Columns([
                            (urwid.WEIGHT, 0.6, urwid.Text("")),
                            (urwid.WEIGHT, 0.4, urwid.Button("OK", on_press=dismiss_dialog)),
                        ])
                    ])
                    rdialog_pile.error_display = False

                    rdialog = DialogLineBox(rdialog_pile, title="Ingest message URI")
                    rdialog.delegate = self
                    bottom = self.listbox

                    roverlay = urwid.Overlay(
                        rdialog,
                        bottom,
                        align=urwid.CENTER,
                        width=urwid.RELATIVE_100,
                        valign=urwid.MIDDLE,
                        height=urwid.PACK,
                        left=2,
                        right=2,
                    )

                    options = self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width)
                    self.columns_widget.contents[0] = (roverlay, options)

            except Exception as e:
                RNS.log("Could not ingest LXM URI. The contained exception was: "+str(e), RNS.LOG_VERBOSE)
                if not dialog_pile.error_display:
                    dialog_pile.error_display = True
                    options = dialog_pile.options(height_type=urwid.PACK)
                    dialog_pile.contents.append((urwid.Text(""), options))
                    dialog_pile.contents.append((urwid.Text(("error_text", "Could ingest LXM from URI data. Check your input."), align=urwid.CENTER), options))

        dialog_pile = urwid.Pile([
            e_uri,
            urwid.Text(""),
            urwid.Columns([
                (urwid.WEIGHT, 0.45, urwid.Button("Ingest", on_press=confirmed)),
                (urwid.WEIGHT, 0.1, urwid.Text("")),
                (urwid.WEIGHT, 0.45, urwid.Button("Back", on_press=dismiss_dialog)),
            ])
        ])
        dialog_pile.error_display = False

        dialog = DialogLineBox(dialog_pile, title="Ingest message URI")
        dialog.delegate = self
        bottom = self.listbox

        overlay = urwid.Overlay(
            dialog,
            bottom,
            align=urwid.CENTER,
            width=urwid.RELATIVE_100,
            valign=urwid.MIDDLE,
            height=urwid.PACK,
            left=2,
            right=2,
        )

        options = self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width)
        self.columns_widget.contents[0] = (overlay, options)

    def delete_conversation(self, source_hash):
        if source_hash in ConversationsDisplay.cached_conversation_widgets:
            conversation = ConversationsDisplay.cached_conversation_widgets[source_hash]
            self.close_conversation(conversation)

    def toggle_fullscreen(self):
        if ConversationsDisplay.given_list_width != 0:
            self.saved_list_width = ConversationsDisplay.given_list_width
            ConversationsDisplay.given_list_width = 0
        else:
            ConversationsDisplay.given_list_width = self.saved_list_width

        self.update_conversation_list()

    def _decode_pn_app_data(self, app_data):
        try:
            if not pn_announce_data_is_valid(app_data):
                return None
            data = msgpack.unpackb(app_data)
            enabled = bool(data[2])
            name = None
            try:
                meta = data[6]
                if isinstance(meta, dict) and PN_META_NAME in meta:
                    raw = meta[PN_META_NAME]
                    if isinstance(raw, (bytes, bytearray)):
                        name = raw.decode("utf-8", errors="replace")
            except Exception:
                name = None
            return {"enabled": enabled, "name": name}
        except Exception:
            return None

    def _pn_dropdown_label(self, pn_hash, meta):
        name = (meta or {}).get("name")
        if name:
            label = sanitize_name(name) or ""
            label = " ".join(label.split())
        else:
            label = ""
        if not label:
            label = RNS.prettyhexrep(pn_hash)
        max_len = 40
        if len(label) > max_len:
            label = label[:max_len-1]+"…"
        tail = "<"+RNS.hexrep(pn_hash, delimit=False)+">"
        if tail not in label:
            label = label+"  "+tail
        if meta is None:
            status = "[?]"
        elif meta.get("enabled"):
            status = "[E]"
        else:
            status = "[D]"
        return status+" "+label

    def _build_pn_options(self):
        options = []
        seen = set()

        try:
            pn_announces = list(self.app.directory._pn_announces)
        except Exception:
            pn_announces = []
        for tup in pn_announces:
            if len(tup) < 3: continue
            pn_hash  = tup[1]
            app_data = tup[2]
            if pn_hash in seen: continue
            seen.add(pn_hash)
            meta = self._decode_pn_app_data(app_data)
            options.append((pn_hash, self._pn_dropdown_label(pn_hash, meta)))

        for extra in (self.app.get_user_selected_propagation_node(), self.app.get_default_propagation_node()):
            if extra is None or extra in seen:
                continue
            seen.add(extra)
            meta = None
            try:
                cached = RNS.Identity.recall_app_data(extra)
                if cached is not None:
                    meta = self._decode_pn_app_data(cached)
            except Exception:
                meta = None
            options.append((extra, self._pn_dropdown_label(extra, meta)))

        return options

    def sync_conversations(self):
        g = self.app.ui.glyphs
        self.dialog_open = True

        def dismiss_dialog(sender):
            self.dialog_open = False
            self.sync_dialog = None
            self.update_conversation_list()
            if self.app.message_router.propagation_transfer_state >= LXMF.LXMRouter.PR_COMPLETE:
                self.app.cancel_lxmf_sync()

        max_messages_group = []
        r_mall = urwid.RadioButton(max_messages_group, "Download all", state=True)
        r_mlim = urwid.RadioButton(max_messages_group, "Limit to", state=False)
        ie_lim = urwid.IntEdit("", 5)
        rbs = urwid.GridFlow([r_mlim, ie_lim], 12, 1, 0, align=urwid.LEFT)

        def sync_now(sender):
            limit = None
            if r_mlim.get_state():
                limit = ie_lim.value()
            self.app.request_lxmf_sync(limit)
            self.update_sync_dialog()

        def cancel_sync(sender):
            self.app.cancel_lxmf_sync()
            self.update_sync_dialog()

        cancel_button = urwid.Button("Close", on_press=dismiss_dialog)
        sync_progress = SyncProgressBar("progress_empty" , "progress_full", current=self.app.get_sync_progress(), done=1.0, satt=None)

        real_sync_button = urwid.Button("Sync Now", on_press=sync_now)
        hidden_sync_button = urwid.Button("Cancel Sync", on_press=cancel_sync)

        if self.app.get_sync_status() == "Idle" or self.app.message_router.propagation_transfer_state >= LXMF.LXMRouter.PR_COMPLETE:
            sync_button = real_sync_button
        else:
            sync_button = hidden_sync_button

        button_columns = urwid.Columns([
            (urwid.WEIGHT, 0.45, sync_button),
            (urwid.WEIGHT, 0.1, urwid.Text("")),
            (urwid.WEIGHT, 0.45, cancel_button),
        ])
        real_sync_button.bc = button_columns

        current_default = self.app.get_default_propagation_node()
        user_selected   = self.app.get_user_selected_propagation_node()

        pn_options = self._build_pn_options()

        selected_target = user_selected if user_selected is not None else current_default

        def on_pn_picked(picked_hash):
            try:
                self.app.set_user_selected_propagation_node(picked_hash)
            except Exception as e:
                RNS.log("Could not update propagation node: "+str(e), RNS.LOG_ERROR)

        def show_set_pn_dialog(_sender):
            current_pn = self.app.get_user_selected_propagation_node()
            current_str = RNS.hexrep(current_pn, delimit=False) if current_pn is not None else ""
            pn_edit = ReadlineEdit(caption="Hash : ", edit_text=current_str)
            status_text = urwid.Text("", align=urwid.CENTER)

            def reopen_sync(_b=None):
                self.sync_conversations()

            def save_pn(_b):
                text = pn_edit.get_edit_text().strip().replace(":", "").replace(" ", "")
                expected_len = RNS.Reticulum.TRUNCATED_HASHLENGTH // 8
                if text == "":
                    self.app.set_user_selected_propagation_node(None)
                else:
                    try:
                        node_hash = bytes.fromhex(text)
                    except ValueError:
                        status_text.set_text("Invalid hex")
                        return
                    if len(node_hash) != expected_len:
                        status_text.set_text("Must be "+str(expected_len)+" bytes ("+str(expected_len*2)+" hex chars)")
                        return
                    self.app.set_user_selected_propagation_node(node_hash)
                reopen_sync()

            def clear_pn(_b):
                pn_edit.set_edit_text("")
                self.app.set_user_selected_propagation_node(None)
                reopen_sync()

            inner = DialogLineBox(
                urwid.Pile([
                    urwid.Text("Enter an LXMF propagation\ndestination hash as hex.", align=urwid.CENTER),
                    urwid.Divider(),
                    pn_edit,
                    urwid.Divider(),
                    status_text,
                    urwid.Columns([
                        (urwid.WEIGHT, 0.3, urwid.Button("Save", on_press=save_pn)),
                        (urwid.WEIGHT, 0.05, urwid.Text("")),
                        (urwid.WEIGHT, 0.3, urwid.Button("Clear", on_press=clear_pn)),
                        (urwid.WEIGHT, 0.05, urwid.Text("")),
                        (urwid.WEIGHT, 0.3, urwid.Button("Close", on_press=reopen_sync)),
                    ])
                ]), title="Set Propagation Node",
            )
            inner.delegate = self
            self.sync_dialog = None
            overlay = urwid.Overlay(
                inner, self.listbox,
                align=urwid.CENTER, width=urwid.RELATIVE_100,
                valign=urwid.MIDDLE, height=urwid.PACK,
                left=2, right=2,
            )
            options = self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width)
            self.columns_widget.contents[0] = (overlay, options)

        set_pn_button = urwid.Button("Custom Node...", on_press=show_set_pn_dialog)

        if pn_options:
            node_picker = PropNodePicker(pn_options, selected_target, on_pn_picked)
            node_selector = urwid.Pile([
                urwid.Text("Propagation node:"),
                node_picker,
                set_pn_button,
            ])
        else:
            node_selector = None

        pn_ident = None
        if current_default is not None:
            pn_ident = RNS.Identity.recall(current_default)
            if pn_ident is None:
                RNS.log("Propagation node identity is unknown, requesting from network...", RNS.LOG_DEBUG)
                RNS.Transport.request_path(current_default)

        if pn_ident is not None or node_selector is not None:
            header_str = ""
            if pn_ident is not None:
                node_hash = RNS.Destination.hash_from_name_and_identity("nomadnetwork.node", pn_ident)
                pn_entry  = self.app.directory.find(node_hash)
                if pn_entry is not None and getattr(pn_entry, "display_name", None):
                    header_str = " "+strip_modifiers(str(pn_entry.display_name))
                else:
                    header_str = " "+RNS.prettyhexrep(current_default)
            else:
                header_str = " (no default)"

            pile_items = [
                urwid.Text(""+g["node"]+header_str, align=urwid.CENTER),
                urwid.Divider(g["divider1"]),
                sync_progress,
                urwid.Divider(g["divider1"]),
            ]
            pile_items += [button_columns, urwid.Text(""), r_mall, rbs]
            if node_selector is not None:
                pile_items += [urwid.Divider(g["divider1"]), node_selector]

            dialog = DialogLineBox(urwid.Pile(pile_items), title="Message Sync")
        else:
            button_columns = urwid.Columns([
                (urwid.WEIGHT, 0.45, urwid.Text("" )),
                (urwid.WEIGHT, 0.1, urwid.Text("")),
                (urwid.WEIGHT, 0.45, cancel_button),
            ])
            dialog = DialogLineBox(
                urwid.Pile([
                    urwid.Text(""),
                    urwid.Text("No trusted nodes found, cannot sync!\n", align=urwid.CENTER),
                    urwid.Text(
                        "To synchronise messages from the network, "
                        "one or more nodes must be marked as trusted in the Known Nodes list, "
                        "or a node must manually be selected as the default propagation node. "
                        "Nomad Network will then automatically sync from the nearest trusted node, "
                        "or the manually selected one.",
                        align=urwid.LEFT,
                    ),
                    urwid.Text(""),
                    button_columns
                ]), title="Message Sync"
            )

        dialog.delegate = self
        dialog.sync_progress = sync_progress
        dialog.cancel_button = cancel_button
        dialog.real_sync_button = real_sync_button
        dialog.hidden_sync_button = hidden_sync_button
        dialog.bc = button_columns

        self.sync_dialog = dialog
        bottom = self.listbox

        overlay = urwid.Overlay(
            dialog,
            bottom,
            align=urwid.CENTER,
            width=urwid.RELATIVE_100,
            valign=urwid.MIDDLE,
            height=urwid.PACK,
            left=2,
            right=2,
        )

        # options = self.columns_widget.options(urwid.WEIGHT, ConversationsDisplay.list_width)
        options = self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width)
        self.columns_widget.contents[0] = (overlay, options)

    def update_sync_dialog(self, loop = None, sender = None):
        if self.dialog_open and self.sync_dialog != None:
            self.sync_dialog.sync_progress.set_completion(self.app.get_sync_progress())

            if self.app.get_sync_status() == "Idle" or self.app.message_router.propagation_transfer_state >= LXMF.LXMRouter.PR_COMPLETE:
                self.sync_dialog.bc.contents[0] = (self.sync_dialog.real_sync_button, self.sync_dialog.bc.options(urwid.WEIGHT, 0.45))
            else:
                self.sync_dialog.bc.contents[0] = (self.sync_dialog.hidden_sync_button, self.sync_dialog.bc.options(urwid.WEIGHT, 0.45))

            self.app.ui.loop.set_alarm_in(0.2, self.update_sync_dialog)


    def conversation_list_selection(self, arg1, arg2):
        pass

    def update_conversation_list(self):
        selected_hash = None
        selected_item = self.ilb.get_selected_item()
        if selected_item is not None:
            if hasattr(selected_item, "source_hash"):
                selected_hash = selected_item.source_hash

        self.update_listbox()
        options = self.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width)
        if not self.dialog_open:
            self.columns_widget.contents[0] = (self.listbox, options)
        elif self.sync_dialog is not None:
            bottom = self.listbox
            overlay = urwid.Overlay(
                self.sync_dialog,
                bottom,
                align=urwid.CENTER,
                width=urwid.RELATIVE_100,
                valign=urwid.MIDDLE,
                height=urwid.PACK,
                left=2,
                right=2,
            )
            self.columns_widget.contents[0] = (overlay, options)
        # else: another dialog (peer info, new conversation, block confirm, etc.) is
        # open as an overlay in contents[0]; leave it alone so an incoming message
        # doesn't dismiss it. The underlying listbox is a persistent widget and was
        # already refreshed by update_listbox() above.

        if selected_hash is not None:
            for idx, widget in enumerate(self.list_widgets):
                if getattr(widget, "source_hash", None) == selected_hash:
                    self.ilb.select_item(idx)
                    break
        nomadnet.NomadNetworkApp.get_shared_instance().ui.loop.draw_screen()

        if self.app.ui.main_display.sub_displays.active_display == self.app.ui.main_display.sub_displays.conversations_display:
            if self.currently_displayed_conversation != None:
                if self.app.conversation_is_unread(self.currently_displayed_conversation):
                    self.app.mark_conversation_read(self.currently_displayed_conversation)
                    try:
                        if os.path.isfile(self.app.conversationpath + "/" + self.currently_displayed_conversation + "/unread"):
                            os.unlink(self.app.conversationpath + "/" + self.currently_displayed_conversation + "/unread")
                    except Exception as e:
                        raise e




    def display_conversation(self, sender=None, source_hash=None):
        if self.currently_displayed_conversation != None:
            if self.app.conversation_is_unread(self.currently_displayed_conversation):
                self.app.mark_conversation_read(self.currently_displayed_conversation)

        self.currently_displayed_conversation = source_hash
        options = self.columns_widget.options(urwid.WEIGHT, 1)
        self.columns_widget.contents[1] = (self.make_conversation_widget(source_hash), options)
        if source_hash == None:
            self.columns_widget.focus_position = 0
        else:
            if self.app.conversation_is_unread(source_hash):
                self.app.mark_conversation_read(source_hash)
                self.update_conversation_list()

            self.columns_widget.focus_position = 1
            conversation_position = None
            index = 0
            for widget in self.list_widgets:
                if getattr(widget, "source_hash", None) == source_hash:
                    conversation_position = index
                index += 1

            if conversation_position != None:
                self.ilb.select_item(conversation_position)
        

    def make_conversation_widget(self, source_hash):
        if source_hash in ConversationsDisplay.cached_conversation_widgets:
            conversation_widget = ConversationsDisplay.cached_conversation_widgets[source_hash]
            if source_hash != None:
                conversation_widget.update_message_widgets(replace=True)

            conversation_widget.check_editor_allowed()
            return conversation_widget
        else:
            widget = ConversationWidget(source_hash, delegate=self)
            ConversationsDisplay.cached_conversation_widgets[source_hash] = widget

            widget.check_editor_allowed()
            return widget

    def close_conversation_by_hash(self, conversation_hash):
        if conversation_hash in ConversationsDisplay.cached_conversation_widgets:
            ConversationsDisplay.cached_conversation_widgets.pop(conversation_hash)

        if self.currently_displayed_conversation == conversation_hash:
            self.display_conversation(sender=None, source_hash=None)

    def close_conversation(self, conversation):
        if conversation.source_hash in ConversationsDisplay.cached_conversation_widgets:
            ConversationsDisplay.cached_conversation_widgets.pop(conversation.source_hash)

        if self.currently_displayed_conversation == conversation.source_hash:
            self.display_conversation(sender=None, source_hash=None)


    def conversation_list_widget(self, conversation):
        trust_level    = conversation[2]
        display_name   = conversation[1]
        source_hash    = conversation[0]
        unread         = conversation[4]
        last_activity  = conversation[5]
        failed         = conversation[6] if len(conversation) > 6 else 0

        g = self.app.ui.glyphs

        if trust_level == DirectoryEntry.UNTRUSTED:
            symbol        = g["cross"]
            style         = "list_untrusted"
            focus_style   = "list_focus_untrusted"
        elif trust_level == DirectoryEntry.UNKNOWN:
            symbol        = "?"
            style         = "list_unknown"
            focus_style   = "list_focus"
        elif trust_level == DirectoryEntry.TRUSTED:
            symbol        = g["check"]
            style         = "list_normal"
            focus_style   = "list_focus"
        elif trust_level == DirectoryEntry.WARNING:
            symbol        = g["warning"]
            style         = "list_warning"
            focus_style   = "list_focus"
        else:
            symbol        = g["warning"]
            style         = "list_untrusted"
            focus_style   = "list_focus_untrusted"

        is_pinned = False
        try:
            entry = self.app.directory.find(bytes.fromhex(source_hash))
            is_pinned = entry is not None and entry.sort_rank is not None
        except Exception:
            is_pinned = False

        head = symbol
        if is_pinned:
            head = g.get("pin", "*") + " " + head

        if display_name != None and display_name != "":
            head += " "+display_name

        if trust_level != DirectoryEntry.TRUSTED:
            head += " <"+source_hash+">"

        markup = [head]
        if failed and source_hash != self.currently_displayed_conversation:
            badge_text = " "+g["warning"]+" ("+str(failed)+")"
            # markup.append(("msg_notice_caution", badge_text))
            markup.append(badge_text)
        elif unread and source_hash != self.currently_displayed_conversation:
            badge_text = " "+g["unread"]+" ("+str(unread)+")"
            # Good idea with having the badges here colored, but
            # using the bg color for it is a bit much, I think.
            # I set fg color attrmap styles, but that messes up
            # the bg on list focus. If there's a way to handle
            # that, we can re-enable this.
            # markup.append(("msg_notice_unread", badge_text))
            markup.append(badge_text)

        if trust_level == DirectoryEntry.TRUSTED and unread and source_hash != self.currently_displayed_conversation:
            style = "msg_notice_unread"

        if last_activity > 0:
            markup.append("\n  "+relative_time(last_activity))

        widget = ListEntry(markup)
        urwid.connect_signal(widget, "click", self.display_conversation, conversation[0])
        display_widget = urwid.AttrMap(widget, style, focus_style)
        display_widget.source_hash = source_hash
        display_widget.display_name = display_name

        return display_widget


    def shortcuts(self):
        try:
            focus_path = self.columns_widget.get_focus_path()
        except Exception:
            return self.list_shortcuts
        if not focus_path or focus_path[0] != 1:
            return self.list_shortcuts
        try:
            cw = self.columns_widget.contents[1][0]
            frame = cw.base_widget.frame
            if frame is None:
                return self.editor_shortcuts
            if frame.focus_position == "footer":
                return self.editor_shortcuts
            return self.body_shortcuts
        except Exception:
            return self.editor_shortcuts

class ListEntry(urwid.Text):
    _selectable = True

    signals = ["click"]

    def keypress(self, size, key):
        """
        Send 'click' signal on 'activate' command.
        """
        if self._command_map[key] != urwid.ACTIVATE:
            return key

        self._emit('click')

    def mouse_event(self, size, event, button, x, y, focus):
        """
        Send 'click' signal on button 1 press.
        """
        if button != 1 or not urwid.util.is_mouse_press(event):
            return False

        self._emit('click')
        return True

LXM_STATE_NAMES = {
    LXMF.LXMessage.GENERATING: "Generating",
    LXMF.LXMessage.OUTBOUND: "Outbound",
    LXMF.LXMessage.SENDING: "Sending",
    LXMF.LXMessage.SENT: "Sent",
    LXMF.LXMessage.DELIVERED: "Delivered",
    LXMF.LXMessage.REJECTED: "Rejected",
    LXMF.LXMessage.CANCELLED: "Cancelled",
    LXMF.LXMessage.FAILED: "Failed",
}

LXM_METHOD_NAMES = {
    LXMF.LXMessage.OPPORTUNISTIC: "Opportunistic",
    LXMF.LXMessage.DIRECT: "Direct link",
    LXMF.LXMessage.PROPAGATED: "Propagation node",
    LXMF.LXMessage.PAPER: "Paper",
}

class MessageEdit(ReadlineMixin, urwid.Edit):
    def keypress(self, size, key):
        if key == "ctrl d":
            self.delegate.send_message()
        elif key == "ctrl p":
            self.delegate.paper_message()
        elif key == "ctrl f":
            self.delegate.attach_file()
        elif key == "ctrl s":
            self.delegate.save_focused_attachments()
        elif key == "ctrl v":
            self.delegate.cycle_delivery_method()
        elif key == "ctrl r":
            self.delegate.toggle_message_details()
        elif key == "ctrl k":
            if not self.delegate.cancel_pending_send():
                return super(MessageEdit, self).keypress(size, key)
        elif key == "up":
            y = self.get_cursor_coords(size)[1]
            if y == 0:
                if self.delegate.full_editor_active and self.name == "title_editor":
                    self.delegate.frame.focus_position = "body"
                elif not self.delegate.full_editor_active and self.name == "content_editor":
                    self.delegate.frame.focus_position = "body"
                else:
                    return super(MessageEdit, self).keypress(size, key)
            else:
                return super(MessageEdit, self).keypress(size, key)
        else:
            return super(MessageEdit, self).keypress(size, key)


class ConversationFrame(urwid.Frame):
    @property
    def focus_position(self):
        return urwid.Frame.focus_position.fget(self)

    @focus_position.setter
    def focus_position(self, part):
        urwid.Frame.focus_position.fset(self, part)
        try:
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.update_active_shortcuts()
        except Exception:
            pass

    def keypress(self, size, key):
        if self.focus_position == "header":
            result = super(ConversationFrame, self).keypress(size, key)
            if result == "up":
                nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.focus_position = "header"
                return None
            if result == "down":
                self.focus_position = "body"
                return None
            return result
        if self.focus_position == "body":
            if getattr(self.delegate, "dialog_active", False) or getattr(self.delegate, "dialog_open", False):
                return super(ConversationFrame, self).keypress(size, key)
            elif key == "up" and self.delegate.messagelist.top_is_visible:
                if getattr(self.delegate, "has_visible_trust_banner", lambda: False)():
                    try:
                        self.delegate._header_pile.focus_position = 1
                        self.focus_position = "header"
                        return None
                    except Exception:
                        pass
                nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.focus_position = "header"
            elif key == "down" and self.delegate.messagelist.bottom_is_visible:
                self.focus_position = "footer"
            else:
                return super(ConversationFrame, self).keypress(size, key)
        else:
            return super(ConversationFrame, self).keypress(size, key)

class ConversationWidget(urwid.WidgetWrap):
    MAX_ATTACHMENT_SIZE = 100 * 1024 * 1024

    def __init__(self, source_hash, delegate):
        self.app = nomadnet.NomadNetworkApp.get_shared_instance()
        g = self.app.ui.glyphs
        self.delegate = delegate
        if source_hash == None:
            self.frame = None
            display_widget = urwid.LineBox(urwid.Filler(urwid.Text("\n  No conversation selected"), "top"))
            super().__init__(display_widget)
        else:
            if source_hash in ConversationsDisplay.cached_conversation_widgets:
                return ConversationsDisplay.cached_conversation_widgets[source_hash]
            else:
                self.source_hash = source_hash
                self.conversation = nomadnet.Conversation(source_hash, nomadnet.NomadNetworkApp.get_shared_instance())
                self.message_widgets = []
                self.sort_by_timestamp = False
                self.pending_attachments = []
                self.dialog_active = False
                self.show_message_details = False

                self.update_message_widgets()

                self.conversation.register_changed_callback(self._on_conversation_changed_from_callback)

                #title_editor  = MessageEdit(caption="\u270E", edit_text="", multiline=False)
                title_editor  = MessageEdit(caption="", edit_text="", multiline=False)
                title_editor.delegate = self
                title_editor.name = "title_editor"

                #msg_editor  = MessageEdit(caption="\u270E", edit_text="", multiline=True)
                msg_editor  = MessageEdit(caption="", edit_text="", multiline=True)
                msg_editor.delegate = self
                msg_editor.name = "content_editor"

                self.peer_info_widget = urwid.AttrMap(urwid.Text(""), "msg_header_sent")
                self._update_peer_info()

                self._trust_banner_dismissed = False
                self._header_pile = urwid.Pile([self.peer_info_widget])
                self._refresh_trust_banner()
                header = self._header_pile

                self.minimal_editor = urwid.AttrMap(msg_editor, "msg_editor")
                self.minimal_editor.name = "minimal_editor"

                title_columns = urwid.Columns([
                    (8, urwid.Text("Title")),
                    urwid.AttrMap(title_editor, "msg_editor"),
                ])

                content_columns = urwid.Columns([
                    (8, urwid.Text("Content")),
                    urwid.AttrMap(msg_editor, "msg_editor")
                ])

                self.full_editor = urwid.Pile([
                    title_columns,
                    content_columns
                ])
                self.full_editor.name = "full_editor"

                self.content_editor = msg_editor
                self.title_editor = title_editor
                self.full_editor_active = False

                self.frame = ConversationFrame(
                    self.messagelist,
                    header=header,
                    footer=self.minimal_editor,
                    focus_part="footer"
                )
                self.frame.delegate = self

                self.display_widget = urwid.LineBox(
                    self.frame
                )
                
                super().__init__(self.display_widget)

    def has_visible_trust_banner(self):
        if self._trust_banner_dismissed:
            return False
        try:
            tl = self.app.directory.trust_level(bytes.fromhex(self.source_hash))
        except Exception:
            tl = DirectoryEntry.UNKNOWN
        return tl != DirectoryEntry.TRUSTED

    def _refresh_trust_banner(self):
        contents = [(self.peer_info_widget, self._header_pile.options())]
        if self.has_visible_trust_banner():
            banner = self._build_trust_banner()
            contents.append((banner, self._header_pile.options()))
        self._header_pile.contents = contents
        if len(contents) > 1:
            try: self._header_pile.focus_position = 1
            except Exception: pass

    def _build_trust_banner(self):
        g = self.app.ui.glyphs
        msg = urwid.Text(" "+g["warning"]+" This peer isn't trusted yet.")
        btn_trust   = urwid.Button("Trust",      on_press=self._on_trust_click)
        btn_block   = urwid.Button("Block",      on_press=self._on_block_click)
        btn_nothing = urwid.Button("Do nothing", on_press=self._on_ignore_click)
        row = urwid.Columns([
            ('weight', 1, msg),
            ('pack',   btn_trust),
            (1,        urwid.Text(" ")),
            ('pack',   btn_block),
            (1,        urwid.Text(" ")),
            ('pack',   btn_nothing),
            (1,        urwid.Text(" ")),
        ], dividechars=0)
        return urwid.AttrMap(row, "msg_warning_untrusted")

    def _on_trust_click(self, _btn):
        try:
            src = bytes.fromhex(self.source_hash)
            existing = self.app.directory.find(src)
            display_name = getattr(existing, "display_name", None) if existing is not None else None
            preferred = getattr(existing, "preferred_delivery", None) if existing is not None else None
            entry = DirectoryEntry(src, display_name, DirectoryEntry.TRUSTED, preferred_delivery=preferred)
            self.app.directory.remember(entry)
        except Exception as e:
            RNS.log("Could not mark peer as trusted: "+str(e), RNS.LOG_ERROR)
        self._refresh_trust_banner()
        try:
            self.frame.focus_position = "footer"
        except Exception:
            pass
        try:
            if self.delegate.list_filter != ConversationsDisplay.LIST_FILTER_TRUSTED:
                self.delegate._set_filter(ConversationsDisplay.LIST_FILTER_TRUSTED)
            else:
                self.delegate.update_conversation_list()
        except Exception as e:
            RNS.log("Trust UI refresh failed: "+str(e), RNS.LOG_ERROR)

    def _on_ignore_click(self, _btn):
        self._trust_banner_dismissed = True
        self._refresh_trust_banner()

    def _on_block_click(self, _btn):
        def dismiss(_b):
            self.dialog_active = False
            try: self.delegate.dialog_open = False
            except Exception: pass
            try: self.delegate.update_conversation_list()
            except Exception: pass

        def confirmed(_b):
            self.dialog_active = False
            try: self.delegate.dialog_open = False
            except Exception: pass
            try:
                self._block_peer()
            except Exception as e:
                RNS.log("Block failed: "+str(e), RNS.LOG_ERROR)
            try: self.delegate.update_conversation_list()
            except Exception: pass

        try:
            who = self.app.directory.simplest_display_str(bytes.fromhex(self.source_hash))
        except Exception:
            who = self.source_hash

        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text(""),
                urwid.Text("Block "+str(who)+"?\n\nThis will blackhole the peer's identity in Reticulum,\nadd them to your ignored list, and delete this conversation.\n", align=urwid.CENTER),
                urwid.Columns([
                    (urwid.WEIGHT, 0.45, urwid.Button("Yes, block", on_press=confirmed)),
                    (urwid.WEIGHT, 0.10, urwid.Text("")),
                    (urwid.WEIGHT, 0.45, urwid.Button("Cancel",     on_press=dismiss)),
                ]),
            ]), title="Confirm block"
        )
        dialog.delegate = self.delegate

        bottom = self.delegate.listbox
        overlay = urwid.Overlay(dialog, bottom, align=urwid.CENTER, width=urwid.RELATIVE_100, valign=urwid.MIDDLE, height=urwid.PACK, left=2, right=2)
        try:
            self.delegate.columns_widget.contents[0] = (
                overlay,
                self.delegate.columns_widget.options(urwid.GIVEN, ConversationsDisplay.given_list_width),
            )
            self.delegate.columns_widget.focus_position = 0
            self.dialog_active = True
            try: self.delegate.dialog_open = True
            except Exception: pass
        except Exception:
            pass

    def _block_peer(self):
        try:
            src = bytes.fromhex(self.source_hash)
        except Exception:
            return

        try:
            self.app.block_destination(src, reason="user-blocked from nomadnet conversation")
        except Exception as e:
            RNS.log("Block failed: "+str(e), RNS.LOG_ERROR)

        try:
            self.delegate.delete_conversation(self.source_hash)
            nomadnet.Conversation.delete_conversation(self.source_hash, self.app)
        except Exception as e:
            RNS.log("Could not delete blocked conversation: "+str(e), RNS.LOG_ERROR)

    def _update_peer_info(self):
        def san(name):
            if self.app.config["textui"]["sanitize_names"]: return sanitize_name(name)
            else:                                           return strip_modifiers(name)

        g = self.app.ui.glyphs
        source_hash_bytes = bytes.fromhex(self.source_hash)

        display_name = self.app.directory.display_name(source_hash_bytes)
        app_data = None
        if display_name is None or self.app.message_router.get_outbound_stamp_cost(source_hash_bytes) is None:
            app_data = RNS.Identity.recall_app_data(source_hash_bytes)

        if display_name is None:
            if app_data:
                display_name = san(LXMF.display_name_from_app_data(app_data))
        if display_name is None:
            display_name = RNS.prettyhexrep(source_hash_bytes)

        stamp_cost = self.app.message_router.get_outbound_stamp_cost(source_hash_bytes)
        if stamp_cost is None and app_data:
            stamp_cost = LXMF.stamp_cost_from_app_data(app_data)

        hops = RNS.Transport.hops_to(source_hash_bytes)
        if hops >= RNS.Transport.PATHFINDER_M:
            hops_str = "unknown"
        else:
            hops_str = str(hops)+" hop" + ("s" if hops != 1 else "")

        preferred = self.app.directory.preferred_delivery(source_hash_bytes)
        if preferred == DirectoryEntry.PROPAGATED:
            via_str = "Propagation"
        elif preferred == DirectoryEntry.OPPORTUNISTIC:
            via_str = "Opportunistic"
        else:
            via_str = "Link"

        right_parts = []
        if stamp_cost is not None:
            right_parts.append("Stamp: "+str(stamp_cost))
        right_parts.append("Via: "+via_str)
        right_parts.append(g["speed"]+hops_str)

        left = " "+display_name
        right = "  ".join(right_parts)+" "
        self.peer_info_widget.original_widget.set_text(left+" | "+right)

    def clear_history_dialog(self):
        def dismiss_dialog(sender):
            self.dialog_open = False
            self.conversation_changed(None)

        def confirmed(sender):
            self.dialog_open = False
            self.conversation.clear_history()
            self.conversation_changed(None)


        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text("Clear conversation history\n", align=urwid.CENTER),
                urwid.Columns([
                    (urwid.WEIGHT, 0.45, urwid.Button("Yes", on_press=confirmed)),
                    (urwid.WEIGHT, 0.1, urwid.Text("")),
                    (urwid.WEIGHT, 0.45, urwid.Button("No", on_press=dismiss_dialog)),
                ])
            ]), title="?"
        )
        dialog.delegate = self
        bottom = self.messagelist

        overlay = urwid.Overlay(
            dialog,
            bottom,
            align=urwid.CENTER,
            width=34,
            valign=urwid.MIDDLE,
            height=urwid.PACK,
            left=2,
            right=2,
        )

        self.frame.contents["body"] = (overlay, self.frame.options())
        self.frame.focus_position = "body"
    
    def _build_footer(self):
        g = self.app.ui.glyphs
        if self.full_editor_active:
            editor = self.full_editor
        else:
            editor = self.minimal_editor

        if self.pending_attachments:
            attachment_texts = []
            for path in self.pending_attachments:
                attachment_texts.append(os.path.basename(path))
            indicator = urwid.AttrMap(
                urwid.Text(g["file"]+" "+str(len(self.pending_attachments))+" file(s): "+", ".join(attachment_texts)),
                "msg_header_sent",
            )
            return urwid.Pile([indicator, editor])
        else:
            return editor

    def toggle_editor(self):
        if self.full_editor_active:
            self.full_editor_active = False
        else:
            self.full_editor_active = True
        self.frame.contents["footer"] = (self._build_footer(), None)

    def check_editor_allowed(self):
        g = self.app.ui.glyphs
        if self.frame:
            allowed = nomadnet.NomadNetworkApp.get_shared_instance().directory.is_known(bytes.fromhex(self.source_hash))
            if allowed:
                self.conversation.ensure_send_destination()
                self.frame.contents["footer"] = (self._build_footer(), None)
            else:
                warning = urwid.AttrMap(
                    urwid.Padding(urwid.Text(
                        "\n"+g["info"]+"\n\nYou cannot currently message this peer, since its identity keys are not known. "
                                       "The keys have been requested from the network and should arrive shortly, if available. "
                                       "The message editor will appear here as soon as the keys arrive.\n\n"
                                       "To query the network manually, select this conversation in the conversation list, "
                                       "press Ctrl-E, and use the query button.\n",
                        align=urwid.CENTER,
                    )),
                    "msg_header_caution",
                )
                self.frame.contents["footer"] = (warning, None)
                self._schedule_editor_recheck()

    def _schedule_editor_recheck(self):
        if getattr(self, "_editor_recheck_pending", False):
            return
        try:
            loop = nomadnet.NomadNetworkApp.get_shared_instance().ui.loop
            if loop is None:
                return
            self._editor_recheck_pending = True
            loop.set_alarm_in(1.0, self._editor_recheck)
        except Exception:
            self._editor_recheck_pending = False

    def _editor_recheck(self, loop=None, user_data=None):
        self._editor_recheck_pending = False
        if not self.frame:
            return
        if getattr(self.delegate, "currently_displayed_conversation", None) != self.source_hash:
            return
        if nomadnet.NomadNetworkApp.get_shared_instance().directory.is_known(bytes.fromhex(self.source_hash)):
            self.check_editor_allowed()
            try:
                loop.draw_screen()
            except Exception:
                pass
        else:
            self._schedule_editor_recheck()

    def toggle_focus_area(self):
        name = ""
        try:
            name = self.frame.get_focus_widgets()[0].name
        except Exception as e:
            pass

        if name == "messagelist":
            self.frame.focus_position = "footer"
        elif name == "minimal_editor" or name == "full_editor":
            self.frame.focus_position = "body"

    def keypress(self, size, key):
        if key == "tab":
            self.toggle_focus_area()
            return None
        key = super(ConversationWidget, self).keypress(size, key)
        if key is None:
            return None
        if key == "ctrl w":
            self.close()
        elif key == "ctrl u":
            self.conversation.purge_failed()
            self.conversation_changed(None)
        elif key == "ctrl k":
            self.cancel_pending_send()
        elif key == "ctrl t":
            self.toggle_editor()
        elif key == "ctrl x":
            self.clear_history_dialog()
        elif key == "ctrl g":
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.sub_displays.conversations_display.toggle_fullscreen()
        elif key == "ctrl o":
            self.sort_by_timestamp ^= True
            self.conversation_changed(None)
        elif key == "ctrl a":
            self.attach_file()
        elif key == "ctrl s":
            self.save_focused_attachments()
        elif key == "ctrl v":
            self.cycle_delivery_method()
        elif key == "ctrl r":
            self.toggle_message_details()
        else:
            return key

    def toggle_message_details(self):
        self.show_message_details = not self.show_message_details
        self.update_message_widgets(replace=True)

    def _message_is_pending(self, conv_message):
        try:
            src = conv_message._cached_source_hash
            state = conv_message.get_state()
        except Exception:
            return False
        is_outbound = src is not None and self.app.lxmf_destination.hash == src
        return is_outbound and state is not None and state < LXMF.LXMessage.SENT

    def cancel_message(self, conv_message):
        if conv_message is None:
            return
        try:
            self.app.message_router.cancel_outbound(conv_message.get_hash())
            conv_message._cached_state = LXMF.LXMessage.FAILED
        except Exception as e:
            RNS.log("Could not cancel outbound message: "+str(e), RNS.LOG_ERROR)
        self.conversation_changed(None)

    def cancel_pending_send(self):
        for widget in reversed(self.message_widgets):
            conv_message = getattr(widget, "conv_message", None)
            if conv_message is not None and self._message_is_pending(conv_message):
                self.cancel_message(conv_message)
                return True
        return False

    def cycle_delivery_method(self):
        source_hash_bytes = bytes.fromhex(self.source_hash)
        order = [DirectoryEntry.DIRECT, DirectoryEntry.OPPORTUNISTIC, DirectoryEntry.PROPAGATED]
        current = self.app.directory.preferred_delivery(source_hash_bytes)
        try:
            selected = order[(order.index(current) + 1) % len(order)]
        except ValueError:
            selected = order[0]
        entry = self.app.directory.find(source_hash_bytes)
        if entry is None:
            display_name = self.app.directory.display_name(source_hash_bytes)
            entry = DirectoryEntry(source_hash_bytes, display_name, DirectoryEntry.UNKNOWN, preferred_delivery=selected)
        else:
            entry.preferred_delivery = selected
        self.app.directory.remember(entry)
        self._update_peer_info()

    def _on_conversation_changed_from_callback(self, conversation):
        self.delegate._wake(lambda: self.conversation_changed(conversation))

    def conversation_changed(self, conversation):
        if hasattr(self, "peer_info_widget"):
            self._update_peer_info()
        self.update_message_widgets(replace = True)

    def update_message_widgets(self, replace = False):
        prev_pos = None
        prev_count = len(self.message_widgets) if getattr(self, "message_widgets", None) else 0
        if getattr(self, "messagelist", None) is not None:
            try:
                prev_pos = self.messagelist.get_selected_position()
            except Exception:
                prev_pos = None

        self.message_widgets = []
        added_hashes = set()
        needs_index = []
        for message in self.conversation.messages:
            message_hash = message.get_hash()
            if not message_hash in added_hashes:
                added_hashes.add(message_hash)
                was_loaded = message.loaded
                try:
                    message_widget = LXMessageWidget(message, theme=self.app.config["textui"]["theme"], conversation_widget=self)
                except Exception as e:
                    RNS.log("Skipping message loading for "+str(message.file_path)+" due to error: "+str(e), RNS.LOG_WARNING)
                    message.unload()
                    continue
                self.message_widgets.append(message_widget)
                if not was_loaded and message.loaded:
                    needs_index.append(message)
                message.unload()

        if needs_index:
            try:
                ConversationMessage.write_index(
                    self.conversation.messages_path, needs_index)
            except Exception:
                pass

        if self.sort_by_timestamp:
            self.message_widgets.sort(key=lambda m: m.timestamp, reverse=False)
        else:
            self.message_widgets.sort(key=lambda m: m.sort_timestamp, reverse=False)

        from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox
        new_count = len(self.message_widgets)
        if prev_pos is None or prev_count == 0 or prev_pos >= prev_count - 1:
            position = max(0, new_count - 1)
        else:
            position = min(prev_pos, max(0, new_count - 1))
        self.messagelist = IndicativeListBox(self.message_widgets, position = position)
        self.messagelist.name = "messagelist"
        if replace:
            current_body = self.frame.contents["body"][0]
            if self.dialog_active and isinstance(current_body, urwid.Overlay):
                current_body.bottom_w = self.messagelist
            else:
                self.frame.contents["body"] = (self.messagelist, None)
            nomadnet.NomadNetworkApp.get_shared_instance().ui.loop.draw_screen()


    def clear_editor(self):
        self.content_editor.set_edit_text("")
        self.title_editor.set_edit_text("")
        self.pending_attachments = []
        self.frame.contents["footer"] = (self._build_footer(), None)

    def _collect_attachment_refs(self):
        g = self.app.ui.glyphs
        refs = []
        sorted_messages = sorted(self.conversation.messages, key=lambda m: m.sort_timestamp, reverse=True)
        for conv_message in sorted_messages:
            if not conv_message.has_attachments():
                continue

            cached_names = conv_message._cached_attachment_names or []
            att_file_idx = 0
            for atype, aname, *arest in cached_names:
                asize = arest[0] if arest else 0
                glyph = g["file"] if atype == "file" else g[atype]
                label = glyph+" "+aname
                if asize > 0:
                    label += " ("+_format_size(asize)+")"
                if atype == "file":
                    refs.append((label, aname, conv_message, "file", att_file_idx))
                    att_file_idx += 1
                else:
                    refs.append((label, aname, conv_message, atype, 0))

        return refs

    def save_focused_attachments(self):
        g = self.app.ui.glyphs
        self.dialog_active = True

        try:
            attachment_items = self._collect_attachment_refs()
        except Exception as e:
            RNS.log("Error collecting attachments: "+str(e), RNS.LOG_ERROR)
            attachment_items = []

        save_dir = self.app.attachment_save_path if self.app.attachment_save_path else self.app.downloads_path

        def dismiss_dialog(sender):
            self.dialog_active = False
            self.conversation_changed(None)

        if not attachment_items:
            dialog = DialogLineBox(
                urwid.Pile([
                    urwid.Text("No attachments in this conversation.\n"),
                    urwid.Columns([
                        (urwid.WEIGHT, 0.6, urwid.Text("")),
                        (urwid.WEIGHT, 0.4, urwid.Button("OK", on_press=dismiss_dialog)),
                    ])
                ]), title="Attachments"
            )
            dialog.delegate = self
            bottom = self.messagelist
            overlay = urwid.Overlay(dialog, bottom, align=urwid.CENTER, width=45, valign=urwid.MIDDLE, height=urwid.PACK, left=2, right=2)
            self.frame.contents["body"] = (overlay, self.frame.options())
            self.frame.focus_position = "body"
            return

        checkboxes = []
        for label, filename, conv_msg, field_type, field_index in attachment_items:
            cb = urwid.CheckBox(label, state=False)
            cb._attachment_filename = filename
            cb._conv_message = conv_msg
            cb._field_type = field_type
            cb._field_index = field_index
            checkboxes.append(cb)

        status_text = urwid.Text("")

        def do_save(sender):
            saved = []
            errors = []
            for cb in checkboxes:
                if cb.get_state():
                    try:
                        src_path = cb._conv_message.get_attachment_file_path(cb._field_type, cb._field_index)
                        if src_path and os.path.isfile(src_path):
                            path = _copy_attachment_to_dest(cb._attachment_filename, src_path)
                            saved.append(path)
                    except Exception as e:
                        errors.append(str(e))

            if saved:
                lines = [g["check"]+" Copied "+str(len(saved))+" file(s) to "+save_dir+":"]
                for p in saved:
                    lines.append("  "+os.path.basename(p))
                if errors:
                    lines.append(g["cross"]+" "+str(len(errors))+" failed")
                status_text.set_text("\n".join(lines))
            elif errors:
                status_text.set_text(g["cross"]+" Failed: "+errors[0])
            else:
                status_text.set_text("No files selected")

        dialog_widgets = list(checkboxes)
        dialog_widgets.append(urwid.Divider(g["divider1"]))
        dialog_widgets.append(urwid.Text("Copy to: "+save_dir))
        dialog_widgets.append(status_text)
        dialog_widgets.append(urwid.Text(""))
        dialog_widgets.append(urwid.Columns([
            (urwid.WEIGHT, 0.45, urwid.Button("Copy to Downloads", on_press=do_save)),
            (urwid.WEIGHT, 0.1, urwid.Text("")),
            (urwid.WEIGHT, 0.45, urwid.Button("Close", on_press=dismiss_dialog)),
        ]))

        dialog = DialogLineBox(urwid.ListBox(urwid.SimpleFocusListWalker(dialog_widgets)), title="Attachments")
        dialog.delegate = self
        bottom = self.messagelist

        overlay = urwid.Overlay(dialog, bottom, align=urwid.CENTER, width=("relative", 80), valign=urwid.MIDDLE, height=("relative", 80), left=2, right=2)
        self.frame.contents["body"] = (overlay, self.frame.options())
        self.frame.focus_position = "body"

    def send_message(self):
        content = self.content_editor.get_edit_text()
        title = self.title_editor.get_edit_text()
        if not content == "":
            fields = None
            if self.pending_attachments:
                file_attachments = []
                for file_path in self.pending_attachments:
                    try:
                        with open(file_path, "rb") as af:
                            file_data = af.read()
                        file_name = os.path.basename(file_path)
                        file_attachments.append([file_name, file_data])
                    except Exception as e:
                        RNS.log("Error reading attachment "+str(file_path)+": "+str(e), RNS.LOG_ERROR)

                if file_attachments:
                    fields = {LXMF.FIELD_FILE_ATTACHMENTS: file_attachments}

            if self.app.compose_markdown:
                if not fields: fields = {}
                fields[LXMF.FIELD_RENDERER] = LXMF.RENDERER_MARKDOWN

            if self.conversation.send(content, title, fields=fields):
                self.clear_editor()

    def attach_file(self):
        self.dialog_active = True
        initial_attachments = list(self.pending_attachments)

        def on_change(selected):
            self.pending_attachments[:] = selected
            self.frame.contents["footer"] = (self._build_footer(), None)

        def on_done(selected):
            self.pending_attachments[:] = selected
            self.frame.contents["footer"] = (self._build_footer(), None)
            self.file_browser_closed()

        def on_cancel():
            self.pending_attachments[:] = initial_attachments
            self.frame.contents["footer"] = (self._build_footer(), None)
            self.file_browser_closed()

        browser = FileBrowser(
            on_done=on_done,
            on_cancel=on_cancel,
            on_change=on_change,
            title="Attach File",
            multi_select=True,
            selected=self.pending_attachments,
            max_file_size=ConversationWidget.MAX_ATTACHMENT_SIZE,
        )
        bottom = self.messagelist
        overlay = urwid.Overlay(browser, bottom, align=urwid.CENTER, width=("relative", 90), valign=urwid.MIDDLE, height=("relative", 80), left=2, right=2)
        self.frame.contents["body"] = (overlay, self.frame.options())
        self.frame.focus_position = "body"

    def file_browser_closed(self):
        self.dialog_active = False
        self.frame.contents["footer"] = (self._build_footer(), None)
        self.conversation_changed(None)

    def paper_message_saved(self, path):
        g = self.app.ui.glyphs
        def dismiss_dialog(sender):
            self.dialog_open = False
            self.conversation_changed(None)

        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text("The paper message was saved to:\n\n"+str(path)+"\n", align=urwid.CENTER),
                urwid.Columns([
                    (urwid.WEIGHT, 0.6, urwid.Text("")),
                    (urwid.WEIGHT, 0.4, urwid.Button("OK", on_press=dismiss_dialog)),
                ])
            ]), title=g["papermsg"].replace(" ", "")
        )
        dialog.delegate = self
        bottom = self.messagelist

        overlay = urwid.Overlay(dialog, bottom, align=urwid.CENTER, width=60, valign=urwid.MIDDLE, height=urwid.PACK, left=2, right=2)

        self.frame.contents["body"] = (overlay, self.frame.options())
        self.frame.focus_position = "body"

    def print_paper_message_qr(self):
        content = self.content_editor.get_edit_text()
        title = self.title_editor.get_edit_text()
        if not content == "":
            if self.conversation.paper_output(content, title):
                self.clear_editor()
            else:
                self.paper_message_failed()

    def save_paper_message_qr(self):
        content = self.content_editor.get_edit_text()
        title = self.title_editor.get_edit_text()
        if not content == "":
            output_result = self.conversation.paper_output(content, title, mode="save_qr")
            if output_result != False:
                self.clear_editor()
                self.paper_message_saved(output_result)
            else:
                self.paper_message_failed()

    def save_paper_message_uri(self):
        content = self.content_editor.get_edit_text()
        title = self.title_editor.get_edit_text()
        if not content == "":
            output_result = self.conversation.paper_output(content, title, mode="save_uri")
            if output_result != False:
                self.clear_editor()
                self.paper_message_saved(output_result)
            else:
                self.paper_message_failed()

    def paper_message(self):
        def dismiss_dialog(sender):
            self.dialog_open = False
            self.conversation_changed(None)

        def print_qr(sender):
            dismiss_dialog(self)
            self.print_paper_message_qr()

        def save_qr(sender):
            dismiss_dialog(self)
            self.save_paper_message_qr()

        def save_uri(sender):
            dismiss_dialog(self)
            self.save_paper_message_uri()

        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text(
                    "Select the desired paper message output method.\nSaved files will be written to:\n\n"+str(self.app.downloads_path)+"\n",
                    align=urwid.CENTER,
                ),
                urwid.Columns([
                    (urwid.WEIGHT, 0.5, urwid.Button("Print QR", on_press=print_qr)),
                    (urwid.WEIGHT, 0.1, urwid.Text("")),
                    (urwid.WEIGHT, 0.5, urwid.Button("Save QR", on_press=save_qr)),
                    (urwid.WEIGHT, 0.1, urwid.Text("")),
                    (urwid.WEIGHT, 0.5, urwid.Button("Save URI", on_press=save_uri)),
                    (urwid.WEIGHT, 0.1, urwid.Text("")),
                    (urwid.WEIGHT, 0.5, urwid.Button("Cancel", on_press=dismiss_dialog))
                ])
            ]), title="Create Paper Message"
        )
        dialog.delegate = self
        bottom = self.messagelist

        overlay = urwid.Overlay(dialog, bottom, align=urwid.CENTER, width=60, valign=urwid.MIDDLE, height=urwid.PACK, left=2, right=2)

        self.frame.contents["body"] = (overlay, self.frame.options())
        self.frame.focus_position = "body"

    def paper_message_failed(self):
        def dismiss_dialog(sender):
            self.dialog_open = False
            self.conversation_changed(None)

        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text(
                    "Could not output paper message,\ncheck your settings. See the log\nfile for any error messages.\n",
                    align=urwid.CENTER,
                ),
                urwid.Columns([
                    (urwid.WEIGHT, 0.6, urwid.Text("")),
                    (urwid.WEIGHT, 0.4, urwid.Button("OK", on_press=dismiss_dialog)),
                ])
            ]), title="!"
        )
        dialog.delegate = self
        bottom = self.messagelist

        overlay = urwid.Overlay(dialog, bottom, align=urwid.CENTER, width=34, valign=urwid.MIDDLE, height=urwid.PACK, left=2, right=2)

        self.frame.contents["body"] = (overlay, self.frame.options())
        self.frame.focus_position = "body"

    def close(self):
        self.delegate.close_conversation(self)


class LXMessageWidget(urwid.WidgetWrap):
    mdc = MarkdownToMicron(max_width=80, syntax_highlighter=SyntaxHighlighter(), url_scope=None) 

    def __init__(self, message, theme=THEME_DARK, conversation_widget=None):
        app = nomadnet.NomadNetworkApp.get_shared_instance()
        g = app.ui.glyphs
        self._conversation_widget = conversation_widget
        self.conv_message = message
        self.timestamp = message.get_timestamp()
        self.sort_timestamp = message.sort_timestamp
        self.transfer_done = False
        self._live_lxm = None

        msg_hash = message.get_hash()
        msg_state = message.get_state()
        msg_source_hash = message._cached_source_hash
        msg_method = message._cached_method
        time_format = app.time_format
        message_time = datetime.fromtimestamp(self.timestamp)
        renderer = message.content_renderer()
        encryption_string = ""
        if message.get_transport_encrypted():
            encryption_string = " "+g["encrypted"]
        else:
            encryption_string = " "+g["plaintext"]

        title_string = relative_time(self.timestamp)+" | "+message_time.strftime(time_format)+encryption_string

        is_outbound = False
        if msg_source_hash is None:
            header_style = "msg_header_failed"
            title_string = g["warning"]+" "+title_string
        elif app.lxmf_destination.hash == msg_source_hash:
            is_outbound = True
            if msg_state == LXMF.LXMessage.DELIVERED:
                header_style = "msg_header_delivered"
                title_string = g["check"]+" "+g["arrow_r"]+" "+title_string
            elif msg_state == LXMF.LXMessage.FAILED:
                header_style = "msg_header_failed"
                title_string = g["cross"]+" "+g["arrow_r"]+" "+title_string
            elif msg_state == LXMF.LXMessage.REJECTED:
                header_style = "msg_header_failed"
                title_string = g["cross"]+" "+g["arrow_r"]+" Rejected "+title_string
            elif msg_method == LXMF.LXMessage.PROPAGATED and msg_state == LXMF.LXMessage.SENT:
                header_style = "msg_header_propagated"
                title_string = g["sent"]+" "+g["arrow_r"]+" "+title_string
            elif msg_method == LXMF.LXMessage.PAPER and msg_state == LXMF.LXMessage.PAPER:
                header_style = "msg_header_propagated"
                title_string = g["papermsg"]+" "+g["arrow_r"]+" "+title_string
            elif msg_state == LXMF.LXMessage.SENT:
                header_style = "msg_header_sent"
                title_string = g["sent"]+" "+g["arrow_r"]+" "+title_string
            else:
                header_style = "msg_header_sent"
                title_string = g["arrow_r"]+" "+title_string
        else:
            if message.signature_validated():
                header_style = "msg_header_ok"
                title_string = g["check"]+" "+g["arrow_l"]+" "+title_string
            else:
                header_style = "msg_header_caution"
                title_string = g["warning"]+" "+g["arrow_l"]+" "+message.get_signature_description() + "\n  " + title_string

        if message.get_title() != "":
            title_string += " | " + message.get_title()

        inbound_untrusted = False
        if not is_outbound and msg_source_hash is not None:
            try:
                sender_trust = app.directory.trust_level(msg_source_hash)
                if sender_trust in (DirectoryEntry.UNTRUSTED, DirectoryEntry.WARNING, DirectoryEntry.UNKNOWN):
                    inbound_untrusted = True
            except Exception:
                inbound_untrusted = False

        has_attachments = message.has_attachments()
        cached_names = message._cached_attachment_names or []

        if has_attachments and cached_names:
            attachment_strings = []
            for atype, aname, *arest in cached_names:
                attachment_strings.append(g[atype if atype != "file" else "file"]+" "+aname)
            title_string += " | " + " ".join(attachment_strings)

        content_text = message.get_content()

        if content_text and app.config["textui"]["clipboard_copy"]:
            copy_glyph = g.get("copy", "[C]")
            check_glyph = g.get("check", "v").center(len(copy_glyph))
            copy_icon = ClickableIcon(copy_glyph)

            conv_widget = self._conversation_widget
            def on_copy_click(icon=copy_icon, content=content_text, cg=copy_glyph, kg=check_glyph, cw=conv_widget):
                osc52_copy(content)
                icon.set_text(kg)
                def _restore(loop, user_data):
                    icon.set_text(cg)
                try:
                    app.ui.loop.set_alarm_in(2.0, _restore)
                except Exception:
                    icon.set_text(cg)
                if cw is not None and cw.frame is not None:
                    def _refocus(loop, user_data):
                        try:
                            cw.frame.focus_position = "footer"
                        except Exception:
                            pass
                    try:
                        app.ui.loop.set_alarm_in(0, _refocus)
                    except Exception:
                        pass
            copy_icon._on_click = on_copy_click

            copy_width = len(copy_glyph) + 2
            title_row = urwid.Columns([
                ("weight", 1, urwid.Text(title_string)),
                (copy_width, urwid.Padding(copy_icon, left=1, right=1)),
            ])
            title = urwid.AttrMap(title_row, header_style)
        else:
            title = urwid.AttrMap(urwid.Text(title_string), header_style)

        self.progress_widget = urwid.Text("")
        self.progress_attr = urwid.AttrMap(self.progress_widget, "progress_full")

        content_lines = content_text.split("\n")
        markdown = renderer == LXMF.RENDERER_MARKDOWN

        default_fg = "bbb" if theme == THEME_DARK else "444"
        if markdown:
            formatted = self.mdc.format_block(content_text)
            message_body = strip_non_formatting_tags(formatted)
            rendered = markup_to_attrmaps(strip_modifiers(message_body), url_delegate=None, fg_color=default_fg, bg_color=None)
            content_pile = urwid.Padding(urwid.Pile(rendered), left=2, right=2)

        else: indented = "\n".join("  "+line for line in content_lines)

        pile_widgets = [title]

        if conversation_widget is not None and getattr(conversation_widget, "show_message_details", False):
            def _safe(fn):
                try: return fn()
                except Exception: return None

            def _detail_row(glyph, values):
                return urwid.Columns([
                    (3, urwid.Text(("body_text", glyph), align=urwid.RIGHT)),
                    urwid.Text(("inactive_text", "  ·  ".join(values))),
                ], dividechars=1)

            detail_rows = []

            delivery = []
            if msg_method is not None:
                delivery.append(LXM_METHOD_NAMES.get(msg_method, "Unknown"))
            if is_outbound and msg_state is not None:
                delivery.append(LXM_STATE_NAMES.get(msg_state, "Unknown"))
            if delivery:
                detail_rows.append(_detail_row(g.get("sent" if is_outbound else "peer", ">"), delivery))

            signal = []
            snr = _safe(message.get_snr)
            rssi = _safe(message.get_rssi)
            q = _safe(message.get_q)
            if snr is not None:  signal.append("SNR "+str(round(snr, 1))+" dB")
            if rssi is not None: signal.append("RSSI "+str(round(rssi, 1))+" dBm")
            if q is not None:    signal.append("Q "+str(round(q))+"%")
            if signal:
                detail_rows.append(_detail_row(g.get("speed", "~"), signal))

            security = []
            sig = _safe(message.get_signature_description)
            if sig: security.append(sig)
            enc = _safe(message.get_transport_encryption)
            if enc: security.append(str(enc))
            if security:
                detail_rows.append(_detail_row(g.get("encrypted", "#"), security))

            if msg_hash is not None:
                short_hash = _safe(lambda: RNS.hexrep(msg_hash, delimit=False))
                if short_hash:
                    detail_rows.append(_detail_row(g.get("info", "i"), [short_hash]))

            if detail_rows:
                pile_widgets.append(urwid.Padding(urwid.Pile(detail_rows), left=2, right=2))

        if is_outbound and msg_state is not None and msg_state < LXMF.LXMessage.SENT and msg_hash is not None:
            try:
                for pending in app.message_router.pending_outbound:
                    if pending.hash == msg_hash:
                        self._live_lxm = pending
                        break
            except Exception:
                pass

            if self._live_lxm is not None:
                pct = int(self._live_lxm.progress * 100)
                bar_width = 20
                filled = int(bar_width * self._live_lxm.progress)
                if app.ui.colormode >= 256:
                    bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
                else:
                    bar = "#" * filled + "-" * (bar_width - filled)
                self.progress_widget.set_text("  ["+bar+"] "+str(pct)+"%")
                if conversation_widget is not None:
                    cancel_icon = ClickableIcon(" "+g["cross"]+" Cancel ",
                        on_click=lambda cw=conversation_widget, cm=message: cw.cancel_message(cm))
                    progress_row = urwid.Columns([
                        ("weight", 1, self.progress_attr),
                        ("pack", urwid.AttrMap(cancel_icon, "msg_notice_caution")),
                    ], dividechars=1)
                    pile_widgets.append(progress_row)
                else:
                    pile_widgets.append(self.progress_attr)
                self._start_progress_poll()

        if markdown: pile_widgets.append(content_pile)
        else:        pile_widgets.append(urwid.Text(indented))

        if has_attachments and cached_names:
            if inbound_untrusted:
                pile_widgets.append(urwid.AttrMap(
                    urwid.Text("  "+g["warning"]+" This attachment came from a peer that's untrusted. Be careful when opening it."),
                    "list_untrusted",
                ))

            att_file_idx = 0
            for atype, aname, *arest in cached_names:
                glyph = g["file"] if atype == "file" else g[atype]
                asize = arest[0] if arest else 0
                label = "  "+glyph+" "+aname
                if asize > 0:
                    label += " ("+_format_size(asize)+")"
                if atype == "file":
                    pile_widgets.append(ClickableAttachment(label, aname, message, "file", att_file_idx))
                    att_file_idx += 1
                else:
                    pile_widgets.append(ClickableAttachment(label, aname, message, atype))

        pile_widgets.append(urwid.Text(""))

        super().__init__(urwid.Pile(pile_widgets))

    def _start_progress_poll(self):
        try:
            loop = nomadnet.NomadNetworkApp.get_shared_instance().ui.loop
            if loop:
                loop.set_alarm_in(0.3, self._poll_progress)
        except Exception:
            pass

    def _poll_progress(self, loop=None, user_data=None):
        if self.transfer_done:
            return

        if self._live_lxm is None:
            self.transfer_done = True
            return

        app = nomadnet.NomadNetworkApp.get_shared_instance()
        g = app.ui.glyphs
        progress = self._live_lxm.progress
        state = self._live_lxm.state
        pct = int(progress * 100)

        if state == LXMF.LXMessage.FAILED:
            self.progress_widget.set_text("  "+g["cross"]+" Transfer failed")
            self.transfer_done = True
            self._live_lxm = None
        elif state == LXMF.LXMessage.REJECTED:
            self.progress_widget.set_text("  "+g["cross"]+" Rejected: too large or not accepted")
            self.transfer_done = True
            self._live_lxm = None
        elif state >= LXMF.LXMessage.SENT:
            self.progress_widget.set_text("")
            self.transfer_done = True
            self._live_lxm = None
        else:
            bar_width = 20
            filled = int(bar_width * progress)
            if app.ui.colormode >= 256:
                bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
            else:
                bar = "#" * filled + "-" * (bar_width - filled)
            self.progress_widget.set_text("  ["+bar+"] "+str(pct)+"%")

        if not self.transfer_done:
            try:
                ui_loop = app.ui.loop
                if ui_loop:
                    ui_loop.set_alarm_in(0.3, self._poll_progress)
                    ui_loop.draw_screen()
            except Exception:
                pass


class ClickableAttachment(urwid.Text):
    def __init__(self, label, filename, conv_message, field_type, field_index=0):
        self.filename = filename
        self.conv_message = conv_message
        self.field_type = field_type
        self.field_index = field_index
        self.saved = False
        super().__init__(label)

    def mouse_event(self, size, event, button, x, y, focus):
        if button == 1 and urwid.util.is_mouse_press(event):
            self._save()
            return True
        return False

    def _save(self):
        if self.saved:
            return
        app = nomadnet.NomadNetworkApp.get_shared_instance()
        g = app.ui.glyphs
        try:
            src_path = self.conv_message.get_attachment_file_path(self.field_type, self.field_index)
            if src_path and os.path.isfile(src_path):
                save_path = _copy_attachment_to_dest(self.filename, src_path)
            else:
                if self.field_type == "file":
                    attachments = self.conv_message.get_file_attachments()
                    if self.field_index < len(attachments):
                        att = attachments[self.field_index]
                        if isinstance(att, list) and len(att) >= 2:
                            data = att[1] if isinstance(att[1], bytes) else b""
                        else:
                            data = b""
                    else:
                        data = b""
                elif self.field_type == "image":
                    data = self.conv_message.get_image()
                    data = data if isinstance(data, bytes) else b""
                elif self.field_type == "audio":
                    data = self.conv_message.get_audio()
                    data = data if isinstance(data, bytes) else b""
                else:
                    data = b""
                self.conv_message.unload()
                if not data:
                    return
                save_path = _save_attachment_to_disk(self.filename, data)

            self.saved = True
            self.set_text("  "+g["check"]+" Copied to: "+save_path)
        except Exception as e:
            RNS.log("Error saving attachment: "+str(e), RNS.LOG_ERROR)
            self.set_text("  "+g["cross"]+" Save failed: "+str(e))


def _resolve_attachment_save_path(filename):
    app = nomadnet.NomadNetworkApp.get_shared_instance()
    save_dir = app.attachment_save_path if app.attachment_save_path else app.downloads_path
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir)
    safe_name = ConversationMessage.safe_attachment_name(filename)
    base_dir = os.path.realpath(save_dir) + os.sep
    candidate = os.path.realpath(os.path.join(save_dir, safe_name))
    if not (candidate + os.sep).startswith(base_dir):
        raise OSError(13, os.strerror(13))
    counter = 0
    base, ext = os.path.splitext(safe_name)
    while os.path.isfile(candidate):
        counter += 1
        candidate = os.path.realpath(os.path.join(save_dir, base+"_"+str(counter)+ext))
        if not (candidate + os.sep).startswith(base_dir):
            raise OSError(13, os.strerror(13))
    return candidate


def _copy_attachment_to_dest(filename, src_path):
    save_path = _resolve_attachment_save_path(filename)
    shutil.copy2(src_path, save_path)
    return save_path


def _save_attachment_to_disk(filename, data):
    save_path = _resolve_attachment_save_path(filename)
    with open(save_path, "wb") as f:
        f.write(data)
    return save_path


class SyncProgressBar(urwid.ProgressBar):
    def get_text(self):
        status = nomadnet.NomadNetworkApp.get_shared_instance().get_sync_status()
        show_percent = nomadnet.NomadNetworkApp.get_shared_instance().sync_status_show_percent()
        if show_percent:
            return status+" "+super().get_text()
        else:
            return status
