import RNS
import urwid
import nomadnet
from datetime import datetime
from nomadnet.Directory import DirectoryEntry
from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox, MODIFIER_KEY

class NetworkDisplayShortcuts():
    def __init__(self, app):
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("Network Display Shortcuts"), "shortcutbar")


class DialogLineBox(urwid.LineBox):
    def keypress(self, size, key):
        if key == "esc":
            self.delegate.update_conversation_list()
        else:
            return super(DialogLineBox, self).keypress(size, key)


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

class AnnounceStreamEntry(urwid.WidgetWrap):
    def __init__(self, app, timestamp, source_hash):
        self.app = app
        self.timestamp = timestamp
        time_format = app.time_format
        dt = datetime.fromtimestamp(self.timestamp)
        ts_string = dt.strftime(time_format)

        trust_level  = self.app.directory.trust_level(source_hash)
        display_str = self.app.directory.simplest_display_str(source_hash)

        if trust_level == DirectoryEntry.UNTRUSTED:
            symbol        = "\u2715"
            style         = "list_untrusted"
            focus_style   = "list_focus_untrusted"
        elif trust_level == DirectoryEntry.UNKNOWN:
            symbol        = "?"
            style         = "list_unknown"
            focus_style   = "list_focus"
        elif trust_level == DirectoryEntry.TRUSTED:
            symbol        = "\u2713"
            style         = "list_trusted"
            focus_style   = "list_focus_trusted"
        elif trust_level == DirectoryEntry.WARNING:
            symbol        = "\u26A0"
            style         = "list_warning"
            focus_style   = "list_focus"
        else:
            symbol        = "\u26A0"
            style         = "list_untrusted"
            focus_style   = "list_focus_untrusted"

        widget = ListEntry(ts_string+" "+display_str)

        self.display_widget = urwid.AttrMap(widget, style, focus_style)
        urwid.WidgetWrap.__init__(self, self.display_widget)

class AnnounceStream(urwid.WidgetWrap):
    def __init__(self, app, parent):
        self.app = app
        self.parent = parent
        self.started = False
        self.timeout = self.app.config["textui"]["animation_interval"]*2
        self.ilb = None
        
        self.added_entries = []
        self.widget_list = []
        self.update_widget_list()

        wlt = [AnnounceStreamEntry(self.app, e[0], e[1]) for e in self.app.directory.announce_stream]
        self.ilb = IndicativeListBox(
            self.widget_list,
            #wlt,
            on_selection_change=self.list_selection,
            initialization_is_selection_change=False,
            modifier_key=MODIFIER_KEY.CTRL,
            #highlight_offFocus="list_off_focus"
        )

        self.display_widget = self.ilb
        urwid.WidgetWrap.__init__(self, urwid.LineBox(self.display_widget, title="Announce Stream"))

    def rebuild_widget_list(self):
        self.added_entries = []
        self.widget_list = []
        self.update_widget_list()

    def update_widget_list(self):
        new_entries = []
        for e in self.app.directory.announce_stream:
            if not e[0] in self.added_entries:
                self.added_entries.insert(0, e[0])
                new_entries.insert(0, e)

        new_widgets = [AnnounceStreamEntry(self.app, e[0], e[1]) for e in new_entries]
        for nw in new_widgets:
            self.widget_list.insert(0, nw)

        if len(new_widgets) > 0:
            if self.ilb != None:
                self.ilb.set_body(self.widget_list)

    def list_selection(self, arg1, arg2):
        pass

    def update(self):
        self.update_widget_list()

    def update_callback(self, loop=None, user_data=None):
        self.update()
        if self.started:
            self.app.ui.loop.set_alarm_in(self.timeout, self.update_callback)

    def start(self):
        was_started = self.started
        self.started = True
        if not was_started:
            self.update_callback()

    def stop(self):
        self.started = False

class SelectText(urwid.Text):
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

class KnownNodes(urwid.WidgetWrap):
    def __init__(self, app):
        self.app = app
        self.node_list = app.directory.known_nodes()
        
        self.ilb = IndicativeListBox(
            self.make_node_widgets(),
            on_selection_change=self.node_list_selection,
            initialization_is_selection_change=False,
            highlight_offFocus="list_off_focus"
        )

        if len(self.node_list) > 0:
            self.display_widget = self.ilb
            widget_style = None
            self.no_content = False
        else:
            self.no_content = True
            widget_style = "inactive_text"
            self.display_widget = urwid.Pile([urwid.Text(("warning_text", "- i -\n"), align="center"), SelectText(("warning_text", "Currently, no nodes are known\n\n"), align="center")])

        urwid.WidgetWrap.__init__(self, urwid.AttrMap(urwid.LineBox(self.display_widget, title="Known Nodes"), widget_style))

    def keypress(self, size, key):
        if key == "up" and (self.no_content or self.ilb.top_is_visible):
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.set_focus("header")
            
        return super(KnownNodes, self).keypress(size, key)


    def node_list_selection(self, arg1, arg2):
        pass

    def make_node_widgets(self):
        widget_list = []
        for node_entry in self.node_list:
            # TODO: Implement this
            widget_list.append(ListEntry("Node "+RNS.prettyhexrep(node_entry.source_hash)))

        # TODO: Sort list
        return widget_list


class AnnounceTime(urwid.WidgetWrap):
    def __init__(self, app):
        self.started = False
        self.app = app
        self.timeout = self.app.config["textui"]["animation_interval"]
        self.display_widget = urwid.Text("")
        self.update_time()

        urwid.WidgetWrap.__init__(self, self.display_widget)

    def update_time(self):
        self.last_announce_string = "Never"
        if self.app.peer_settings["last_announce"] != None:
            self.last_announce_string = pretty_date(int(self.app.peer_settings["last_announce"]))

        self.display_widget.set_text("Last Announce : "+self.last_announce_string)

    def update_time_callback(self, loop=None, user_data=None):
        self.update_time()
        if self.started:
            self.app.ui.loop.set_alarm_in(self.timeout, self.update_time_callback)

    def start(self):
        was_started = self.started
        self.started = True
        if not was_started:
            self.update_time_callback()

    def stop(self):
        self.started = False


class LocalPeer(urwid.WidgetWrap):
    announce_timer = None

    def __init__(self, app, parent):
        self.app = app
        self.parent = parent
        self.dialog_open = False
        display_name = self.app.lxmf_destination.display_name
        if display_name == None:
            display_name = ""

        t_id = urwid.Text("Addr : "+RNS.hexrep(self.app.lxmf_destination.hash, delimit=False))
        e_name = urwid.Edit(caption="Name : ", edit_text=display_name)

        def save_query(sender):
            def dismiss_dialog(sender):
                self.dialog_open = False
                self.parent.left_pile.contents[3] = (LocalPeer(self.app, self.parent), options)

            self.app.set_display_name(e_name.get_edit_text())

            dialog = DialogLineBox(
                urwid.Pile([
                    urwid.Text("\n\n\nSaved\n\n", align="center"),
                    urwid.Button("OK", on_press=dismiss_dialog)
                ]), title="i"
            )
            dialog.delegate = self
            bottom = self

            #overlay = urwid.Overlay(dialog, bottom, align="center", width=("relative", 100), valign="middle", height="pack", left=4, right=4)
            overlay = dialog
            options = self.parent.left_pile.options(height_type="pack", height_amount=None)
            self.dialog_open = True
            self.parent.left_pile.contents[3] = (overlay, options)

        def announce_query(sender):
            def dismiss_dialog(sender):
                self.dialog_open = False
                options = self.parent.left_pile.options(height_type="pack", height_amount=None)
                self.parent.left_pile.contents[3] = (LocalPeer(self.app, self.parent), options)

            self.app.announce_now()

            dialog = DialogLineBox(
                urwid.Pile([
                    urwid.Text("\n\n\nAnnounce Sent\n\n", align="center"),
                    urwid.Button("OK", on_press=dismiss_dialog)
                ]), title="i"
            )
            dialog.delegate = self
            bottom = self

            #overlay = urwid.Overlay(dialog, bottom, align="center", width=("relative", 100), valign="middle", height="pack", left=4, right=4)
            overlay = dialog
            
            self.dialog_open = True
            options = self.parent.left_pile.options(height_type="pack", height_amount=None)
            self.parent.left_pile.contents[3] = (overlay, options)

        def node_settings_query(sender):
            options = self.parent.left_pile.options(height_type="pack", height_amount=None)
            self.parent.left_pile.contents[3] = (self.parent.node_settings_display, options)

        if LocalPeer.announce_timer == None:
            self.t_last_announce = AnnounceTime(self.app)
            LocalPeer.announce_timer = self.t_last_announce
        else:
            self.t_last_announce = LocalPeer.announce_timer
            self.t_last_announce.update_time()

        announce_button = urwid.Button("Announce Now", on_press=announce_query)
        
        self.display_widget = urwid.Pile(
            [
                t_id,
                e_name,
                urwid.Divider("\u2504"),
                self.t_last_announce,
                announce_button,
                urwid.Divider("\u2504"),
                urwid.Columns([("weight", 0.45, urwid.Button("Save", on_press=save_query)), ("weight", 0.1, urwid.Text("")), ("weight", 0.45, urwid.Button("Node Cfg", on_press=node_settings_query))])
            ]
        )

        urwid.WidgetWrap.__init__(self, urwid.LineBox(self.display_widget, title="Local Peer Info"))

    def start(self):
        self.t_last_announce.start()


class NodeSettings(urwid.WidgetWrap):
    def __init__(self, app, parent):
        self.app = app
        self.parent = parent

        def show_peer_info(sender):
            options = self.parent.left_pile.options(height_type="pack", height_amount=None)
            self.parent.left_pile.contents[3] = (LocalPeer(self.app, self.parent), options)

        widget_style = "inactive_text"
        pile = urwid.Pile([
            urwid.Text("- i -\n", align="center"),
            urwid.Text("\nNode Hosting currently unavailable\n\n", align="center"),
            urwid.Padding(urwid.Button("Back", on_press=show_peer_info), "center", "pack")
        ])

        self.display_widget = pile

        urwid.WidgetWrap.__init__(self, urwid.AttrMap(urwid.LineBox(self.display_widget, title="Node Settings"), widget_style))

    def node_list_selection(self, arg1, arg2):
        pass

    def make_node_widgets(self):
        widget_list = []
        for node_entry in self.node_list:
            # TODO: Implement this
            widget_list.append(ListEntry("Node "+RNS.prettyhexrep(node_entry.source_hash)))

        # TODO: Sort list
        return widget_list


class UpdatingText(urwid.WidgetWrap):
    def __init__(self, app, title, value_method, append_text=""):
        self.started = False
        self.app = app
        self.timeout = self.app.config["textui"]["animation_interval"]*5
        self.display_widget = urwid.Text("")
        self.value = None
        self.value_method = value_method
        self.title = title
        self.append_text = append_text
        self.update()

        urwid.WidgetWrap.__init__(self, self.display_widget)

    def update(self):
        self.value = self.value_method()
        self.display_widget.set_text(self.title+str(self.value)+str(self.append_text))

    def update_callback(self, loop=None, user_data=None):
        self.update()
        if self.started:
            self.app.ui.loop.set_alarm_in(self.timeout, self.update_callback)

    def start(self):
        was_started = self.started
        self.started = True
        if not was_started:
            self.update_callback()

    def stop(self):
        self.started = False

class NetworkStats(urwid.WidgetWrap):
    def __init__(self, app, parent):
        self.app = app
        self.parent = parent

        def get_num_peers():
            return self.app.directory.number_of_known_peers(lookback_seconds=30*60)


        def get_num_nodes():
            return self.app.directory.number_of_known_nodes()

        self.w_heard_peers = UpdatingText(self.app, "Heard Peers: ", get_num_peers, append_text=" (last 30m)")
        self.w_known_nodes = UpdatingText(self.app, "Known Nodes: ", get_num_nodes)

        pile = urwid.Pile([
            self.w_heard_peers,
            self.w_known_nodes,
        ])

        self.display_widget = urwid.LineBox(pile, title="Network Stats")

        urwid.WidgetWrap.__init__(self, self.display_widget)

    def start(self):
        self.w_heard_peers.start()
        self.w_known_nodes.start()

class NetworkDisplay():
    list_width = 0.33

    def __init__(self, app):
        self.app = app

        self.known_nodes_display = KnownNodes(self.app)
        self.network_stats_display = NetworkStats(self.app, self)
        self.announce_stream_display = AnnounceStream(self.app, self)
        self.local_peer_display = LocalPeer(self.app, self)
        self.node_settings_display = NodeSettings(self.app, self)

        self.left_pile = urwid.Pile([
            ("pack", self.known_nodes_display),
            ("weight", 1, self.announce_stream_display),
            ("pack", self.network_stats_display),
            ("pack", self.local_peer_display),
        ])

        self.left_area = self.left_pile
        self.right_area = urwid.AttrMap(urwid.LineBox(urwid.Filler(urwid.Text("Disconnected\n\u2190  \u2192", align="center"), "middle"), title="Remote Node"), "inactive_text")

        self.columns = urwid.Columns(
            [
                ("weight", NetworkDisplay.list_width, self.left_area),
                ("weight", 1-NetworkDisplay.list_width, self.right_area)
            ],
            dividechars=0, focus_column=0
        )

        self.shortcuts_display = NetworkDisplayShortcuts(self.app)
        self.widget = self.columns

    def start(self):
        self.local_peer_display.start()
        self.network_stats_display.start()
        self.announce_stream_display.start()

    def shortcuts(self):
        return self.shortcuts_display

    def directory_change_callback(self):
        self.announce_stream_display.rebuild_widget_list()



def pretty_date(time=False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    from datetime import datetime
    now = datetime.now()
    if type(time) is int:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time,datetime):
        diff = now - time
    elif not time:
        diff = now - now
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ''

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(second_diff) + " seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return str(int(second_diff / 60)) + " minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str(int(second_diff / 3600)) + " hours ago"
    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(int(day_diff / 7)) + " weeks ago"
    if day_diff < 365:
        return str(int(day_diff / 30)) + " months ago"
    return str(int(day_diff / 365)) + " years ago"
