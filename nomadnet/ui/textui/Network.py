import RNS
import urwid
import nomadnet
import time
from datetime import datetime
from nomadnet.Directory import DirectoryEntry
from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox, MODIFIER_KEY

from .Browser import Browser

class NetworkDisplayShortcuts():
    def __init__(self, app):
        self.app = app
        g = app.ui.glyphs

        self.widget = urwid.AttrMap(urwid.Text("[C-l] Toggle Nodes/Announces view  [C-x] Remove entry  [C-w] Disconnect remote"), "shortcutbar")
        #   "[C-"+g["arrow_u"]+g["arrow_d"]+"] Navigate Lists"


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


class AnnounceInfo(urwid.WidgetWrap):
    def __init__(self, announce, parent, app):
        self.app = nomadnet.NomadNetworkApp.get_shared_instance()
        self.parent = self.app.ui.main_display.sub_displays.network_display
        g = self.app.ui.glyphs

        source_hash  = announce[1]
        time_format  = app.time_format
        dt           = datetime.fromtimestamp(announce[0])
        ts_string    = dt.strftime(time_format)
        trust_level  = self.app.directory.trust_level(source_hash)
        trust_str    = ""
        display_str  = self.app.directory.simplest_display_str(source_hash)
        addr_str     = "<"+RNS.hexrep(source_hash, delimit=False)+">"
        is_node      = announce[3]

        if is_node:
            type_string = g["node"] + " Node"
        else:
            type_string = g["peer"] + " Peer"

        try:
            data_str = announce[2].decode("utf-8")
            data_style = ""
            if trust_level != DirectoryEntry.TRUSTED and len(data_str) > 32:
                data_str = data_str[:32]+" [...]"
        except Exception as e:
            data_str = "Decode failed"
            data_style = "list_untrusted"


        if trust_level == DirectoryEntry.UNTRUSTED:
            trust_str     = "Untrusted"
            symbol        = g["cross"]
            style         = "list_untrusted"
        elif trust_level == DirectoryEntry.UNKNOWN:
            trust_str     = "Unknown"
            symbol        = g["unknown"]
            style         = "list_unknown"
        elif trust_level == DirectoryEntry.TRUSTED:
            trust_str     = "Trusted"
            symbol        = g["check"]
            style         = "list_trusted"
        elif trust_level == DirectoryEntry.WARNING:
            trust_str     = "Warning"
            symbol        = g["warning"]
            style         = "list_warning"
        else:
            trust_str     = "Warning"
            symbol        = g["warning"]
            style         = "list_untrusted"

        def show_announce_stream(sender):
            options = self.parent.left_pile.options(height_type="weight", height_amount=1)
            self.parent.left_pile.contents[0] = (self.parent.announce_stream_display, options)

        def connect(sender):
            self.parent.browser.retrieve_url(RNS.hexrep(source_hash, delimit=False))
            show_announce_stream(None)

        def converse(sender):
            show_announce_stream(None)
            try:
                existing_conversations = nomadnet.Conversation.conversation_list(self.app)
                
                source_hash_text = RNS.hexrep(source_hash, delimit=False)
                display_name = data_str

                if not source_hash_text in [c[0] for c in existing_conversations]:
                    entry = DirectoryEntry(source_hash, display_name, trust_level)
                    self.app.directory.remember(entry)

                    new_conversation = nomadnet.Conversation(source_hash_text, nomadnet.NomadNetworkApp.get_shared_instance(), initiator=True)
                    self.app.ui.main_display.sub_displays.conversations_display.update_conversation_list()

                self.app.ui.main_display.sub_displays.conversations_display.display_conversation(None, source_hash_text)
                self.app.ui.main_display.show_conversations(None)

            except Exception as e:
                RNS.log("Error while starting conversation from announce. The contained exception was: "+str(e), RNS.LOG_ERROR)

        if is_node:
            type_button = ("weight", 0.45, urwid.Button("Connect", on_press=connect))
        else:
            type_button = ("weight", 0.45, urwid.Button("Converse", on_press=converse))

        pile_widgets = [
            urwid.Text("Time  : "+ts_string, align="left"),
            urwid.Text("Addr  : "+addr_str, align="left"),
            urwid.Text("Type  : "+type_string, align="left"),
            urwid.Text("Name  : "+display_str, align="left"),
            urwid.Text(["Trust : ", (style, trust_str)], align="left"),
            urwid.Divider(g["divider1"]),
            urwid.Text(["Announce Data: \n", (data_style, data_str)], align="left"),
            urwid.Divider(g["divider1"]),
            urwid.Columns([("weight", 0.45, urwid.Button("Back", on_press=show_announce_stream)), ("weight", 0.1, urwid.Text("")), type_button])
        ]

        if is_node:
            node_ident = RNS.Identity.recall(source_hash)
            op_hash = RNS.Destination.hash_from_name_and_identity("lxmf.delivery", node_ident)
            op_str = self.app.directory.simplest_display_str(op_hash)
            operator_entry = urwid.Text("Oprtr : "+op_str, align="left")
            pile_widgets.insert(4, operator_entry)

        pile = urwid.Pile(pile_widgets)

        self.display_widget = urwid.Filler(pile, valign="top", height="pack")

        urwid.WidgetWrap.__init__(self, urwid.LineBox(self.display_widget, title="Announce Info"))


class AnnounceStreamEntry(urwid.WidgetWrap):
    def __init__(self, app, announce):
        full_time_format = "%Y-%m-%d %H:%M:%S"
        date_time_format = "%Y-%m-%d"
        time_time_format = "%H:%M:%S"
        short_time_format = "%Y-%m-%d %H:%M"

        timestamp = announce[0]
        source_hash = announce[1]
        is_node = announce[3]
        self.app = app
        self.timestamp = timestamp
        time_format = app.time_format
        dt = datetime.fromtimestamp(self.timestamp)
        dtn = datetime.fromtimestamp(time.time())
        g = self.app.ui.glyphs

        if dt.strftime(date_time_format) == dtn.strftime(date_time_format):
            ts_string = dt.strftime(time_time_format)
        else:
            ts_string = dt.strftime(short_time_format)

        trust_level  = self.app.directory.trust_level(source_hash)
        display_str = self.app.directory.simplest_display_str(source_hash)

        if trust_level == DirectoryEntry.UNTRUSTED:
            symbol        = g["cross"]
            style         = "list_untrusted"
            focus_style   = "list_focus_untrusted"
        elif trust_level == DirectoryEntry.UNKNOWN:
            symbol        = g["unknown"]
            style         = "list_unknown"
            focus_style   = "list_focus"
        elif trust_level == DirectoryEntry.TRUSTED:
            symbol        = g["check"]
            style         = "list_trusted"
            focus_style   = "list_focus_trusted"
        elif trust_level == DirectoryEntry.WARNING:
            symbol        = g["warning"]
            style         = "list_warning"
            focus_style   = "list_focus"
        else:
            symbol        = g["warning"]
            style         = "list_untrusted"
            focus_style   = "list_focus_untrusted"

        if is_node:
            type_symbol = g["node"]
        else:
            type_symbol = g["peer"]

        widget = ListEntry(ts_string+" "+type_symbol+" "+display_str)
        urwid.connect_signal(widget, "click", self.display_announce, announce)

        self.display_widget = urwid.AttrMap(widget, style, focus_style)
        urwid.WidgetWrap.__init__(self, self.display_widget)

    def display_announce(self, event, announce):
        parent = self.app.ui.main_display.sub_displays.network_display
        info_widget = AnnounceInfo(announce, parent, self.app)
        options = parent.left_pile.options(height_type="weight", height_amount=1)
        parent.left_pile.contents[0] = (info_widget, options)

    def timestamp(self):
        return self.timestamp

class AnnounceStream(urwid.WidgetWrap):
    def __init__(self, app, parent):
        self.app = app
        self.parent = parent
        self.started = False
        self.timeout = self.app.config["textui"]["animation_interval"]*2
        self.ilb = None
        self.no_content = True
        
        self.added_entries = []
        self.widget_list = []
        self.update_widget_list()

        self.ilb = IndicativeListBox(
            self.widget_list,
            on_selection_change=self.list_selection,
            initialization_is_selection_change=False,
            #modifier_key=MODIFIER_KEY.CTRL,
            #highlight_offFocus="list_off_focus"
        )

        self.display_widget = self.ilb
        urwid.WidgetWrap.__init__(self, urwid.LineBox(self.display_widget, title="Announce Stream"))

    def keypress(self, size, key):
        if key == "up" and (self.no_content or self.ilb.first_item_is_selected()):
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.set_focus("header")
        elif key == "ctrl x":
            self.delete_selected_entry()
            
        return super(AnnounceStream, self).keypress(size, key)

    def delete_selected_entry(self):
        if self.ilb.get_selected_item() != None:
            self.app.directory.remove_announce_with_timestamp(self.ilb.get_selected_item().original_widget.timestamp)
            self.rebuild_widget_list()

    def rebuild_widget_list(self):
        self.no_content = True
        self.added_entries = []
        self.widget_list = []
        self.update_widget_list()

    def update_widget_list(self):
        new_entries = []
        for e in self.app.directory.announce_stream:
            if not e[0] in self.added_entries:
                self.added_entries.insert(0, e[0])
                new_entries.insert(0, e)

        for e in new_entries:
            nw = AnnounceStreamEntry(self.app, e)
            nw.timestamp = e[0]
            self.widget_list.insert(0, nw)

        if len(new_entries) > 0:
            self.no_content = False
            if self.ilb != None:
                self.ilb.set_body(self.widget_list)
        else:
            if len(self.widget_list) == 0:
                self.no_content = True
            
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

class ListDialogLineBox(urwid.LineBox):
    def keypress(self, size, key):
        if key == "esc":
            self.delegate.close_list_dialogs()
        else:
            return super(ListDialogLineBox, self).keypress(size, key)

class KnownNodes(urwid.WidgetWrap):
    def __init__(self, app):
        self.app = app
        self.node_list = app.directory.known_nodes()
        g = self.app.ui.glyphs

        self.widget_list = self.make_node_widgets()
        
        self.ilb = IndicativeListBox(
            self.widget_list,
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
            self.pile = urwid.Pile([urwid.Text(("warning_text", g["info"]+"\n"), align="center"), SelectText(("warning_text", "Currently, no nodes are known\n\n"), align="center")])
            self.display_widget = urwid.Filler(self.pile, valign="top", height="pack")

        urwid.WidgetWrap.__init__(self, urwid.AttrMap(urwid.LineBox(self.display_widget, title="Known Nodes"), widget_style))

    def keypress(self, size, key):
        if key == "up" and (self.no_content or self.ilb.first_item_is_selected()):
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.set_focus("header")
        elif key == "ctrl x":
            self.delete_selected_entry()
            
        return super(KnownNodes, self).keypress(size, key)


    def node_list_selection(self, arg1, arg2):
        pass

    def connect_node(self, event, node):
        source_hash = node.source_hash
        trust_level = node.trust_level
        trust_level  = self.app.directory.trust_level(source_hash)
        display_str = self.app.directory.simplest_display_str(source_hash)

        def dismiss_dialog(sender):
            self.delegate.close_list_dialogs()

        def confirmed(sender):
            self.delegate.browser.retrieve_url(RNS.hexrep(source_hash, delimit=False))
            self.delegate.close_list_dialogs()


        dialog = ListDialogLineBox(
            urwid.Pile([
                urwid.Text("Connect to node\n"+self.app.directory.simplest_display_str(source_hash)+"\n", align="center"),
                urwid.Columns([("weight", 0.45, urwid.Button("Yes", on_press=confirmed)), ("weight", 0.1, urwid.Text("")), ("weight", 0.45, urwid.Button("No", on_press=dismiss_dialog))])
            ]), title="?"
        )
        dialog.delegate = self.delegate
        bottom = self

        overlay = urwid.Overlay(dialog, bottom, align="center", width=("relative", 100), valign="middle", height="pack", left=2, right=2)

        options = self.delegate.left_pile.options("weight", 1)
        self.delegate.left_pile.contents[0] = (overlay, options)

    def delete_selected_entry(self):
        source_hash = self.ilb.get_selected_item().original_widget.source_hash

        def dismiss_dialog(sender):
            self.delegate.close_list_dialogs()

        def confirmed(sender):
            self.app.directory.forget(source_hash)
            self.rebuild_widget_list()
            self.delegate.close_list_dialogs()


        dialog = ListDialogLineBox(
            urwid.Pile([
                urwid.Text("Delete Node\n"+self.app.directory.simplest_display_str(source_hash)+"\n", align="center"),
                urwid.Columns([("weight", 0.45, urwid.Button("Yes", on_press=confirmed)), ("weight", 0.1, urwid.Text("")), ("weight", 0.45, urwid.Button("No", on_press=dismiss_dialog))])
            ]), title="?"
        )
        dialog.delegate = self.delegate
        bottom = self

        overlay = urwid.Overlay(dialog, bottom, align="center", width=("relative", 100), valign="middle", height="pack", left=2, right=2)

        options = self.delegate.left_pile.options("weight", 1)
        self.delegate.left_pile.contents[0] = (overlay, options)


    def rebuild_widget_list(self):
        self.node_list = self.app.directory.known_nodes()
        self.widget_list = self.make_node_widgets()
        self.ilb.set_body(self.widget_list)
        if len(self.widget_list) > 0:
            self.no_content = False
        else:
            self.no_content = True
            self.delegate.reinit_known_nodes()

    def make_node_widgets(self):
        widget_list = []
        for node_entry in self.node_list:
            # TODO: Implement this
            ne = NodeEntry(self.app, node_entry, self)
            ne.source_hash = node_entry.source_hash
            widget_list.append(ne)

        # TODO: Sort list
        return widget_list



class NodeEntry(urwid.WidgetWrap):
    def __init__(self, app, node, delegate):
        source_hash = node.source_hash
        trust_level = node.trust_level

        self.app = app
        g = self.app.ui.glyphs

        trust_level  = self.app.directory.trust_level(source_hash)
        display_str = self.app.directory.simplest_display_str(source_hash)

        if trust_level == DirectoryEntry.UNTRUSTED:
            symbol        = g["cross"]
            style         = "list_untrusted"
            focus_style   = "list_focus_untrusted"
        elif trust_level == DirectoryEntry.UNKNOWN:
            symbol        = g["unknown"]
            style         = "list_unknown"
            focus_style   = "list_focus"
        elif trust_level == DirectoryEntry.TRUSTED:
            symbol        = g["check"]
            style         = "list_trusted"
            focus_style   = "list_focus_trusted"
        elif trust_level == DirectoryEntry.WARNING:
            symbol        = g["warning"]
            style         = "list_warning"
            focus_style   = "list_focus"
        else:
            symbol        = g["warning"]
            style         = "list_untrusted"
            focus_style   = "list_focus_untrusted"

        type_symbol = g["node"]
        
        widget = ListEntry(type_symbol+" "+display_str)
        urwid.connect_signal(widget, "click", delegate.connect_node, node)

        self.display_widget = urwid.AttrMap(widget, style, focus_style)
        self.display_widget.source_hash = source_hash
        urwid.WidgetWrap.__init__(self, self.display_widget)


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
        g = self.app.ui.glyphs
        self.dialog_open = False
        display_name = self.app.lxmf_destination.display_name
        if display_name == None:
            display_name = ""

        t_id = urwid.Text("Addr : "+RNS.hexrep(self.app.lxmf_destination.hash, delimit=False))
        e_name = urwid.Edit(caption="Name : ", edit_text=display_name)

        def save_query(sender):
            def dismiss_dialog(sender):
                self.dialog_open = False
                self.parent.left_pile.contents[2] = (LocalPeer(self.app, self.parent), options)

            self.app.set_display_name(e_name.get_edit_text())

            dialog = DialogLineBox(
                urwid.Pile([
                    urwid.Text("\n\n\nSaved\n\n", align="center"),
                    urwid.Button("OK", on_press=dismiss_dialog)
                ]), title=g["info"]
            )
            dialog.delegate = self
            bottom = self

            #overlay = urwid.Overlay(dialog, bottom, align="center", width=("relative", 100), valign="middle", height="pack", left=4, right=4)
            overlay = dialog
            options = self.parent.left_pile.options(height_type="pack", height_amount=None)
            self.dialog_open = True
            self.parent.left_pile.contents[2] = (overlay, options)

        def announce_query(sender):
            def dismiss_dialog(sender):
                self.dialog_open = False
                options = self.parent.left_pile.options(height_type="pack", height_amount=None)
                self.parent.left_pile.contents[2] = (LocalPeer(self.app, self.parent), options)

            self.app.announce_now()

            dialog = DialogLineBox(
                urwid.Pile([
                    urwid.Text("\n\n\nAnnounce Sent\n\n", align="center"),
                    urwid.Button("OK", on_press=dismiss_dialog)
                ]), title=g["info"]
            )
            dialog.delegate = self
            bottom = self

            #overlay = urwid.Overlay(dialog, bottom, align="center", width=("relative", 100), valign="middle", height="pack", left=4, right=4)
            overlay = dialog
            
            self.dialog_open = True
            options = self.parent.left_pile.options(height_type="pack", height_amount=None)
            self.parent.left_pile.contents[2] = (overlay, options)

        def node_settings_query(sender):
            options = self.parent.left_pile.options(height_type="pack", height_amount=None)
            self.parent.left_pile.contents[2] = (self.parent.node_settings_display, options)

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
                urwid.Divider(g["divider1"]),
                self.t_last_announce,
                announce_button,
                urwid.Divider(g["divider1"]),
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
        g = self.app.ui.glyphs

        def show_peer_info(sender):
            options = self.parent.left_pile.options(height_type="pack", height_amount=None)
            self.parent.left_pile.contents[2] = (LocalPeer(self.app, self.parent), options)

        widget_style = "inactive_text"
        pile = urwid.Pile([
            urwid.Text("\n"+g["info"], align="center"),
            urwid.Text("\nNode Hosting currently unavailable\n\n", align="center"),
            urwid.Padding(urwid.Button("Back", on_press=show_peer_info), "center", "pack")
        ])

        self.display_widget = pile

        urwid.WidgetWrap.__init__(self, urwid.AttrMap(urwid.LineBox(self.display_widget, title="Node Settings"), widget_style))



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



class NetworkLeftPile(urwid.Pile):
    def keypress(self, size, key):
        if key == "ctrl l":
            self.parent.toggle_list()
        elif key == "ctrl w":
            self.parent.browser.disconnect()
        else:
            return super(NetworkLeftPile, self).keypress(size, key)


class NetworkDisplay():
    list_width = 0.33

    def __init__(self, app):
        self.app = app
        g = self.app.ui.glyphs

        self.browser = Browser(self.app, "nomadnetwork", "node", auth_identity = self.app.identity, delegate = self)

        self.known_nodes_display = KnownNodes(self.app)
        self.network_stats_display = NetworkStats(self.app, self)
        self.announce_stream_display = AnnounceStream(self.app, self)
        self.local_peer_display = LocalPeer(self.app, self)
        self.node_settings_display = NodeSettings(self.app, self)

        self.known_nodes_display.delegate = self

        self.list_display = 1
        self.left_pile = NetworkLeftPile([
            ("weight", 1, self.known_nodes_display),
            ("pack", self.network_stats_display),
            ("pack", self.local_peer_display),
        ])

        self.left_pile.parent = self

        self.left_area = self.left_pile
        self.right_area = self.browser.display_widget

        self.columns = urwid.Columns(
            [
                ("weight", NetworkDisplay.list_width, self.left_area),
                ("weight", 1-NetworkDisplay.list_width, self.right_area)
            ],
            dividechars=0, focus_column=0
        )

        self.shortcuts_display = NetworkDisplayShortcuts(self.app)
        self.widget = self.columns

    def toggle_list(self):
        if self.list_display != 0:
            options = self.left_pile.options(height_type="weight", height_amount=1)
            self.left_pile.contents[0] = (self.announce_stream_display, options)
            self.list_display = 0
        else:
            options = self.left_pile.options(height_type="weight", height_amount=1)
            self.left_pile.contents[0] = (self.known_nodes_display, options)
            self.list_display = 1

    def focus_lists(self):
        self.columns.focus_position = 0

    def reinit_known_nodes(self):
        self.known_nodes_display = KnownNodes(self.app)
        self.known_nodes_display.delegate = self
        self.close_list_dialogs()
        self.announce_stream_display.rebuild_widget_list()

    def close_list_dialogs(self):
        if self.list_display == 0:
            options = self.left_pile.options(height_type="weight", height_amount=1)
            self.left_pile.contents[0] = (self.announce_stream_display, options)
        else:
            options = self.left_pile.options(height_type="weight", height_amount=1)
            self.left_pile.contents[0] = (self.known_nodes_display, options)

    def start(self):
        self.local_peer_display.start()
        self.network_stats_display.start()
        self.announce_stream_display.start()

    def shortcuts(self):
        return self.shortcuts_display

    def directory_change_callback(self):
        self.announce_stream_display.rebuild_widget_list()
        if self.known_nodes_display.no_content:
            self.reinit_known_nodes()
        else:
            self.known_nodes_display.rebuild_widget_list()



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
