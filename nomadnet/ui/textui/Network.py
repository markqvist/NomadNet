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

        self.widget = urwid.AttrMap(urwid.Text("[C-l] Nodes/Announces  [C-x] Remove  [C-w] Disconnect  [C-d] Back  [C-f] Forward  [C-r] Reload  [C-u] URL  [C-g] Fullscreen"), "shortcutbar")
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
    def keypress(self, size, key):
        if key == "esc":
            options = self.parent.left_pile.options(height_type="weight", height_amount=1)
            self.parent.left_pile.contents[0] = (self.parent.announce_stream_display, options)
        else:
            return super(AnnounceInfo, self).keypress(size, key)

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
        info_type    = announce[3]

        is_node = False
        is_pn   = False
        if info_type == "node" or info_type == True:
            type_string = "Nomad Network Node " + g["node"]
            is_node = True
        elif info_type == "pn":
            type_string = "LXMF Propagation Node " + g["sent"]
            is_pn = True
        elif info_type == "peer" or info_type == False:
            type_string = "Peer " + g["peer"]

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

        def save_node(sender):
            node_entry = DirectoryEntry(source_hash, display_name=data_str, trust_level=trust_level, hosts_node=True)
            self.app.directory.remember(node_entry)
            self.app.ui.main_display.sub_displays.network_display.directory_change_callback()
            show_announce_stream(None)

        if is_node:
            node_ident = RNS.Identity.recall(source_hash)
            if not node_ident:
                raise KeyError("Could not recall identity for selected node")

            op_hash = RNS.Destination.hash_from_name_and_identity("lxmf.delivery", node_ident)
            op_str = self.app.directory.simplest_display_str(op_hash)

        def msg_op(sender):
            show_announce_stream(None)
            if is_node:
                try:
                    existing_conversations = nomadnet.Conversation.conversation_list(self.app)
                    
                    source_hash_text = RNS.hexrep(op_hash, delimit=False)
                    display_name = op_str

                    if not source_hash_text in [c[0] for c in existing_conversations]:
                        entry = DirectoryEntry(source_hash, display_name, trust_level)
                        self.app.directory.remember(entry)

                        new_conversation = nomadnet.Conversation(source_hash_text, nomadnet.NomadNetworkApp.get_shared_instance(), initiator=True)
                        self.app.ui.main_display.sub_displays.conversations_display.update_conversation_list()

                    self.app.ui.main_display.sub_displays.conversations_display.display_conversation(None, source_hash_text)
                    self.app.ui.main_display.show_conversations(None)

                except Exception as e:
                    RNS.log("Error while starting conversation from announce. The contained exception was: "+str(e), RNS.LOG_ERROR)

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

        def use_pn(sender):
            show_announce_stream(None)
            try:
                self.app.set_user_selected_propagation_node(source_hash)
            except Exception as e:
                RNS.log("Error while setting active propagation node from announce. The contained exception was: "+str(e), RNS.LOG_ERROR)

        if is_node:
            type_button = ("weight", 0.45, urwid.Button("Connect", on_press=connect))
            msg_button =  ("weight", 0.45, urwid.Button("Msg Op", on_press=msg_op))
            save_button = ("weight", 0.45, urwid.Button("Save", on_press=save_node))
        elif is_pn:
            type_button = ("weight", 0.45, urwid.Button("Use as default", on_press=use_pn))
            save_button = None
        else:
            type_button = ("weight", 0.45, urwid.Button("Converse", on_press=converse))
            save_button = None

        if is_node:
            button_columns = urwid.Columns([("weight", 0.45, urwid.Button("Back", on_press=show_announce_stream)), ("weight", 0.1, urwid.Text("")), type_button, ("weight", 0.1, urwid.Text("")), msg_button, ("weight", 0.1, urwid.Text("")), save_button])
        else:
            button_columns = urwid.Columns([("weight", 0.45, urwid.Button("Back", on_press=show_announce_stream)), ("weight", 0.1, urwid.Text("")), type_button])

        pile_widgets = []

        if is_pn:
            pile_widgets = [
                urwid.Text("Time  : "+ts_string, align="left"),
                urwid.Text("Addr  : "+addr_str, align="left"),
                urwid.Text("Type  : "+type_string, align="left"),
                urwid.Divider(g["divider1"]),
                button_columns
            ]

        else:
            pile_widgets = [
                urwid.Text("Time  : "+ts_string, align="left"),
                urwid.Text("Addr  : "+addr_str, align="left"),
                urwid.Text("Type  : "+type_string, align="left"),
                urwid.Text("Name  : "+display_str, align="left"),
                urwid.Text(["Trust : ", (style, trust_str)], align="left"),
                urwid.Divider(g["divider1"]),
                urwid.Text(["Announce Data: \n", (data_style, data_str)], align="left"),
                urwid.Divider(g["divider1"]),
                button_columns
            ]

            if is_node:
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
        date_only_format = "%Y-%m-%d"

        timestamp = announce[0]
        source_hash = announce[1]
        announce_type = announce[3]
        self.app = app
        self.timestamp = timestamp
        time_format = app.time_format
        dt = datetime.fromtimestamp(self.timestamp)
        dtn = datetime.fromtimestamp(time.time())
        g = self.app.ui.glyphs

        if dt.strftime(date_time_format) == dtn.strftime(date_time_format):
            ts_string = dt.strftime(time_time_format)
        else:
            ts_string = dt.strftime(date_only_format)

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

        if announce_type == "node" or announce_type == True:
            type_symbol = g["node"]
        elif announce_type == "peer" or announce_type == False:
            type_symbol = g["peer"]
        elif announce_type == "pn":
            type_symbol = g["sent"]

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

        self.ilb = ExceptionHandlingListBox(
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

class KnownNodeInfo(urwid.WidgetWrap):
    def keypress(self, size, key):
        if key == "esc":
            options = self.parent.left_pile.options(height_type="weight", height_amount=1)
            self.parent.left_pile.contents[0] = (self.parent.known_nodes_display, options)
        else:
            return super(KnownNodeInfo, self).keypress(size, key)

    def __init__(self, node_hash):
        self.app = nomadnet.NomadNetworkApp.get_shared_instance()
        self.parent = self.app.ui.main_display.sub_displays.network_display
        self.pn_changed = False
        g = self.app.ui.glyphs

        source_hash  = node_hash
        node_ident   = RNS.Identity.recall(node_hash)
        time_format  = self.app.time_format
        trust_level  = self.app.directory.trust_level(source_hash)
        trust_str    = ""
        node_entry   = self.app.directory.find(source_hash)
        if node_entry == None:
            display_str = self.app.directory.simplest_display_str(source_hash)
        else:
            display_str = node_entry.display_name

        addr_str     = "<"+RNS.hexrep(source_hash, delimit=False)+">"

        if display_str == None:
            display_str = addr_str

        pn_hash = RNS.Destination.hash_from_name_and_identity("lxmf.propagation", node_ident)

        if node_ident != None:
            lxmf_addr_str = g["sent"]+" LXMF Propagation Node Address is "+RNS.prettyhexrep(pn_hash)
        else:
            lxmf_addr_str = "No associated Propagation Node known"


        type_string = "Nomad Network Node " + g["node"]

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

        trust_button_group = []
        r_untrusted = urwid.RadioButton(trust_button_group, "Untrusted", state=untrusted_selected)
        r_unknown   = urwid.RadioButton(trust_button_group, "Unknown", state=unknown_selected)
        r_trusted   = urwid.RadioButton(trust_button_group, "Trusted", state=trusted_selected)

        e_name = urwid.Edit(caption="Name      : ",edit_text=display_str)

        node_ident = RNS.Identity.recall(source_hash)
        op_hash = None
        op_str = None
        if node_ident != None:
            op_hash = RNS.Destination.hash_from_name_and_identity("lxmf.delivery", node_ident)
            op_str = self.app.directory.simplest_display_str(op_hash)
        else:
            op_str = "Unknown"

        def show_known_nodes(sender):
            options = self.parent.left_pile.options(height_type="weight", height_amount=1)
            self.parent.left_pile.contents[0] = (self.parent.known_nodes_display, options)

        def connect(sender):
            self.parent.browser.retrieve_url(RNS.hexrep(source_hash, delimit=False))
            show_known_nodes(None)

        def msg_op(sender):
            show_known_nodes(None)
            if node_ident != None:
                try:
                    existing_conversations = nomadnet.Conversation.conversation_list(self.app)
                    
                    source_hash_text = RNS.hexrep(op_hash, delimit=False)
                    display_name = op_str

                    if not source_hash_text in [c[0] for c in existing_conversations]:
                        entry = DirectoryEntry(source_hash, display_name, trust_level)
                        self.app.directory.remember(entry)

                        new_conversation = nomadnet.Conversation(source_hash_text, nomadnet.NomadNetworkApp.get_shared_instance(), initiator=True)
                        self.app.ui.main_display.sub_displays.conversations_display.update_conversation_list()

                    self.app.ui.main_display.sub_displays.conversations_display.display_conversation(None, source_hash_text)
                    self.app.ui.main_display.show_conversations(None)

                except Exception as e:
                    RNS.log("Error while starting conversation from node info. The contained exception was: "+str(e), RNS.LOG_ERROR)

        def pn_change(sender, userdata):
            self.pn_changed = True

        def ident_change(sender, userdata):
            pass

        propagation_node_checkbox = urwid.CheckBox("Use as default propagation node", state=(self.app.get_user_selected_propagation_node() == source_hash), on_state_change=pn_change)
        connect_identify_checkbox = urwid.CheckBox("Identify when connecting", state=self.app.directory.should_identify_on_connect(source_hash), on_state_change=ident_change)

        def save_node(sender):
            if self.pn_changed:
                if propagation_node_checkbox.get_state():
                    self.app.set_user_selected_propagation_node(pn_hash)
                else:
                    self.app.set_user_selected_propagation_node(None)

            trust_level = DirectoryEntry.UNTRUSTED
            if r_unknown.get_state() == True:
                trust_level = DirectoryEntry.UNKNOWN
            
            if r_trusted.get_state() == True:
                trust_level = DirectoryEntry.TRUSTED

            display_str = e_name.get_edit_text()

            node_entry = DirectoryEntry(source_hash, display_name=display_str, trust_level=trust_level, hosts_node=True, identify_on_connect=connect_identify_checkbox.get_state())
            self.app.directory.remember(node_entry)
            self.app.ui.main_display.sub_displays.network_display.directory_change_callback()
            show_known_nodes(None)

        back_button = ("weight", 0.2, urwid.Button("Back", on_press=show_known_nodes))
        connect_button = ("weight", 0.2, urwid.Button("Connect", on_press=connect))
        save_button = ("weight", 0.2, urwid.Button("Save", on_press=save_node))
        msg_button = ("weight", 0.2, urwid.Button("Msg Op", on_press=msg_op))
        bdiv = ("weight", 0.02, urwid.Text(""))

        button_columns = urwid.Columns([back_button, bdiv, connect_button, bdiv, msg_button, bdiv, save_button])

        pile_widgets = [
            urwid.Text("Type      : "+type_string, align="left"),
            e_name,
            urwid.Text("Node Addr : "+addr_str, align="left"),
            urwid.Divider(g["divider1"]),
            urwid.Text(lxmf_addr_str, align="center"),
            urwid.Divider(g["divider1"]),
            propagation_node_checkbox,
            connect_identify_checkbox,
            urwid.Divider(g["divider1"]),
            r_untrusted,
            r_unknown,
            r_trusted,
            urwid.Divider(g["divider1"]),
            button_columns
        ]

        operator_entry = urwid.Text("Operator  : "+op_str, align="left")
        pile_widgets.insert(3, operator_entry)

        hops = RNS.Transport.hops_to(source_hash)
        if hops == 1:
            str_s = ""
        else:
            str_s = "s"

        if hops != RNS.Transport.PATHFINDER_M:
            hops_str = str(hops)+" hop"+str_s
        else:
            hops_str = "Unknown"

        operator_entry = urwid.Text("Distance  : "+hops_str, align="left")
        pile_widgets.insert(4, operator_entry)

        pile = urwid.Pile(pile_widgets)
        
        pile.focus_position = len(pile.contents)-1
        button_columns.focus_position = 0


        self.display_widget = urwid.Filler(pile, valign="top", height="pack")

        urwid.WidgetWrap.__init__(self, urwid.LineBox(self.display_widget, title="Node Info"))


# Yes, this is weird. There is a bug in Urwid/ILB that causes
# an indexing exception when the list is very small vertically.
# This mitigates it.
class ExceptionHandlingListBox(IndicativeListBox):
    def keypress(self, size, key):
        try:
            return super(ExceptionHandlingListBox, self).keypress(size, key)

        except Exception as e:
            if key == "up":
                nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.set_focus("header")
            elif key == "down":
                nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.sub_displays.network_display.left_pile.set_focus(1)
            else:
                RNS.log("An error occurred while processing an interface event. The contained exception was: "+str(e), RNS.LOG_ERROR)


class KnownNodes(urwid.WidgetWrap):
    def __init__(self, app):
        self.app = app
        self.node_list = app.directory.known_nodes()
        g = self.app.ui.glyphs

        self.widget_list = self.make_node_widgets()
        
        self.ilb = ExceptionHandlingListBox(
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

        urwid.WidgetWrap.__init__(self, urwid.AttrMap(urwid.LineBox(self.display_widget, title="Saved Nodes"), widget_style))

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

        parent = self.app.ui.main_display.sub_displays.network_display

        def dismiss_dialog(sender):
            self.delegate.close_list_dialogs()

        def confirmed(sender):
            self.delegate.browser.retrieve_url(RNS.hexrep(source_hash, delimit=False))
            self.delegate.close_list_dialogs()

        def show_info(sender):
            info_widget = KnownNodeInfo(source_hash)
            options = parent.left_pile.options(height_type="weight", height_amount=1)
            parent.left_pile.contents[0] = (info_widget, options)


        dialog = ListDialogLineBox(
            urwid.Pile([
                urwid.Text("Connect to node\n"+self.app.directory.simplest_display_str(source_hash)+"\n", align="center"),
                urwid.Columns([
                    ("weight", 0.45, urwid.Button("Yes", on_press=confirmed)),
                    ("weight", 0.1, urwid.Text("")),
                    ("weight", 0.45, urwid.Button("No", on_press=dismiss_dialog)),
                    ("weight", 0.1, urwid.Text("")),
                    ("weight", 0.45, urwid.Button("Info", on_press=show_info))])
            ]), title="?"
        )
        dialog.delegate = self.delegate
        bottom = self

        overlay = urwid.Overlay(dialog, bottom, align="center", width=("relative", 100), valign="middle", height="pack", left=2, right=2)

        options = self.delegate.left_pile.options("weight", 1)
        self.delegate.left_pile.contents[0] = (overlay, options)

    def delete_selected_entry(self):
        si = self.ilb.get_selected_item()
        if si != None:
            source_hash = si.original_widget.source_hash

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

        self.display_widget.set_text("Announced : "+self.last_announce_string)

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


class NodeAnnounceTime(urwid.WidgetWrap):
    def __init__(self, app):
        self.started = False
        self.app = app
        self.timeout = self.app.config["textui"]["animation_interval"]
        self.display_widget = urwid.Text("")
        self.update_time()

        urwid.WidgetWrap.__init__(self, self.display_widget)

    def update_time(self):
        self.last_announce_string = "Never"
        if self.app.peer_settings["node_last_announce"] != None:
            self.last_announce_string = pretty_date(int(self.app.peer_settings["node_last_announce"]))

        self.display_widget.set_text("Last Announce  : "+self.last_announce_string)

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

class NodeActiveConnections(urwid.WidgetWrap):
    def __init__(self, app):
        self.started = False
        self.app = app
        self.timeout = self.app.config["textui"]["animation_interval"]
        self.display_widget = urwid.Text("")
        self.update_stat()

        urwid.WidgetWrap.__init__(self, self.display_widget)

    def update_stat(self):
        self.stat_string = "None"
        if self.app.node != None:
            self.stat_string = str(len(self.app.node.destination.links))

        self.display_widget.set_text("Connected Now  : "+self.stat_string)

    def update_stat_callback(self, loop=None, user_data=None):
        self.update_stat()
        if self.started:
            self.app.ui.loop.set_alarm_in(self.timeout, self.update_stat_callback)

    def start(self):
        was_started = self.started
        self.started = True
        if not was_started:
            self.update_stat_callback()

    def stop(self):
        self.started = False

class NodeStorageStats(urwid.WidgetWrap):
    def __init__(self, app):
        self.started = False
        self.app = app
        self.timeout = self.app.config["textui"]["animation_interval"]
        self.display_widget = urwid.Text("")
        self.update_stat()

        urwid.WidgetWrap.__init__(self, self.display_widget)

    def update_stat(self):
        self.stat_string = "None"
        if self.app.node != None:

            limit = self.app.message_router.message_storage_limit
            used = self.app.message_router.message_storage_size()

            if limit != None:
                pct = round((used/limit)*100, 1)
                pct_str = str(pct)+"%, "
                limit_str = " of "+RNS.prettysize(limit)
            else:
                limit_str = ""
                pct_str = ""

            self.stat_string = pct_str+RNS.prettysize(used)+limit_str

        self.display_widget.set_text("LXMF Storage   : "+self.stat_string)

    def update_stat_callback(self, loop=None, user_data=None):
        self.update_stat()
        if self.started:
            self.app.ui.loop.set_alarm_in(self.timeout, self.update_stat_callback)

    def start(self):
        was_started = self.started
        self.started = True
        if not was_started:
            self.update_stat_callback()

    def stop(self):
        self.started = False

class NodeTotalConnections(urwid.WidgetWrap):
    def __init__(self, app):
        self.started = False
        self.app = app
        self.timeout = self.app.config["textui"]["animation_interval"]
        self.display_widget = urwid.Text("")
        self.update_stat()

        urwid.WidgetWrap.__init__(self, self.display_widget)

    def update_stat(self):
        self.stat_string = "None"
        if self.app.node != None:
            self.stat_string = str(self.app.peer_settings["node_connects"])

        self.display_widget.set_text("Total Connects : "+self.stat_string)

    def update_stat_callback(self, loop=None, user_data=None):
        self.update_stat()
        if self.started:
            self.app.ui.loop.set_alarm_in(self.timeout, self.update_stat_callback)

    def start(self):
        was_started = self.started
        self.started = True
        if not was_started:
            self.update_stat_callback()

    def stop(self):
        self.started = False


class NodeTotalPages(urwid.WidgetWrap):
    def __init__(self, app):
        self.started = False
        self.app = app
        self.timeout = self.app.config["textui"]["animation_interval"]
        self.display_widget = urwid.Text("")
        self.update_stat()

        urwid.WidgetWrap.__init__(self, self.display_widget)

    def update_stat(self):
        self.stat_string = "None"
        if self.app.node != None:
            self.stat_string = str(self.app.peer_settings["served_page_requests"])

        self.display_widget.set_text("Served Pages   : "+self.stat_string)

    def update_stat_callback(self, loop=None, user_data=None):
        self.update_stat()
        if self.started:
            self.app.ui.loop.set_alarm_in(self.timeout, self.update_stat_callback)

    def start(self):
        was_started = self.started
        self.started = True
        if not was_started:
            self.update_stat_callback()

    def stop(self):
        self.started = False


class NodeTotalFiles(urwid.WidgetWrap):
    def __init__(self, app):
        self.started = False
        self.app = app
        self.timeout = self.app.config["textui"]["animation_interval"]
        self.display_widget = urwid.Text("")
        self.update_stat()

        urwid.WidgetWrap.__init__(self, self.display_widget)

    def update_stat(self):
        self.stat_string = "None"
        if self.app.node != None:
            self.stat_string = str(self.app.peer_settings["served_file_requests"])

        self.display_widget.set_text("Served Files   : "+self.stat_string)

    def update_stat_callback(self, loop=None, user_data=None):
        self.update_stat()
        if self.started:
            self.app.ui.loop.set_alarm_in(self.timeout, self.update_stat_callback)

    def start(self):
        was_started = self.started
        self.started = True
        if not was_started:
            self.update_stat_callback()

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

        t_id =           urwid.Text("LXMF Addr : "+RNS.prettyhexrep(self.app.lxmf_destination.hash))
        i_id =           urwid.Text("Identity  : "+RNS.prettyhexrep(self.app.identity.hash))
        e_name = urwid.Edit(caption="Name      : ", edit_text=display_name)

        def save_query(sender):
            def dismiss_dialog(sender):
                self.dialog_open = False
                self.parent.left_pile.contents[1] = (LocalPeer(self.app, self.parent), options)

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
            self.parent.left_pile.contents[1] = (overlay, options)

        def announce_query(sender):
            def dismiss_dialog(sender):
                self.dialog_open = False
                options = self.parent.left_pile.options(height_type="pack", height_amount=None)
                self.parent.left_pile.contents[1] = (LocalPeer(self.app, self.parent), options)

            self.app.announce_now()

            dialog = DialogLineBox(
                urwid.Pile([
                    urwid.Text("\n\n\nAnnounce Sent\n\n\n", align="center"),
                    urwid.Button("OK", on_press=dismiss_dialog)
                ]), title=g["info"]
            )
            dialog.delegate = self
            bottom = self

            #overlay = urwid.Overlay(dialog, bottom, align="center", width=("relative", 100), valign="middle", height="pack", left=4, right=4)
            overlay = dialog
            
            self.dialog_open = True
            options = self.parent.left_pile.options(height_type="pack", height_amount=None)
            self.parent.left_pile.contents[1] = (overlay, options)

        def node_info_query(sender):
            options = self.parent.left_pile.options(height_type="pack", height_amount=None)
            self.parent.left_pile.contents[1] = (self.parent.node_info_display, options)

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
                i_id,
                e_name,
                urwid.Divider(g["divider1"]),
                self.t_last_announce,
                announce_button,
                urwid.Divider(g["divider1"]),
                urwid.Columns([("weight", 0.45, urwid.Button("Save", on_press=save_query)), ("weight", 0.1, urwid.Text("")), ("weight", 0.45, urwid.Button("Node Info", on_press=node_info_query))])
            ]
        )

        urwid.WidgetWrap.__init__(self, urwid.LineBox(self.display_widget, title="Local Peer Info"))

    def start(self):
        self.t_last_announce.start()


class NodeInfo(urwid.WidgetWrap):
    announce_timer = None
    links_timer = None
    conns_timer = None
    pages_timer = None
    files_timer = None
    storage_timer = None

    def __init__(self, app, parent):
        self.app = app
        self.parent = parent
        g = self.app.ui.glyphs

        self.dialog_open = False

        widget_style = ""

        def show_peer_info(sender):
            options = self.parent.left_pile.options(height_type="pack", height_amount=None)
            self.parent.left_pile.contents[1] = (LocalPeer(self.app, self.parent), options)
        
        if self.app.enable_node:
            if self.app.node != None:
                display_name = self.app.node.name
            else:
                display_name = None
        
            if display_name == None:
                display_name = ""

            t_id = urwid.Text("Addr : "+RNS.hexrep(self.app.node.destination.hash, delimit=False))
            e_name = urwid.Text("Name : "+display_name)

            def stats_query(sender):
                self.app.peer_settings["node_connects"] = 0
                self.app.peer_settings["served_page_requests"] = 0
                self.app.peer_settings["served_file_requests"] = 0
                self.app.save_peer_settings()

            def announce_query(sender):
                def dismiss_dialog(sender):
                    self.dialog_open = False
                    options = self.parent.left_pile.options(height_type="pack", height_amount=None)
                    self.parent.left_pile.contents[1] = (NodeInfo(self.app, self.parent), options)

                self.app.node.announce()

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
                self.parent.left_pile.contents[1] = (overlay, options)

            def connect_query(sender):
                self.parent.browser.retrieve_url(RNS.hexrep(self.app.node.destination.hash, delimit=False))

            if NodeInfo.announce_timer == None:
                self.t_last_announce = NodeAnnounceTime(self.app)
                NodeInfo.announce_timer = self.t_last_announce
            else:
                self.t_last_announce = NodeInfo.announce_timer
                self.t_last_announce.update_time()

            if NodeInfo.links_timer == None:
                self.t_active_links = NodeActiveConnections(self.app)
                NodeInfo.links_timer = self.t_active_links
            else:
                self.t_active_links = NodeInfo.links_timer
                self.t_active_links.update_stat()

            if NodeInfo.storage_timer == None:
                self.t_storage_stats = NodeStorageStats(self.app)
                NodeInfo.storage_timer = self.t_storage_stats
            else:
                self.t_storage_stats = NodeInfo.storage_timer
                self.t_storage_stats.update_stat()

            if NodeInfo.conns_timer == None:
                self.t_total_connections = NodeTotalConnections(self.app)
                NodeInfo.conns_timer = self.t_total_connections
            else:
                self.t_total_connections = NodeInfo.conns_timer
                self.t_total_connections.update_stat()

            if NodeInfo.pages_timer == None:
                self.t_total_pages = NodeTotalPages(self.app)
                NodeInfo.pages_timer = self.t_total_pages
            else:
                self.t_total_pages = NodeInfo.pages_timer
                self.t_total_pages.update_stat()

            if NodeInfo.files_timer == None:
                self.t_total_files = NodeTotalFiles(self.app)
                NodeInfo.files_timer = self.t_total_files
            else:
                self.t_total_files = NodeInfo.files_timer
                self.t_total_files.update_stat()

            lxmf_addr_str = g["sent"]+" LXMF Propagation Node Address is "+RNS.prettyhexrep(RNS.Destination.hash_from_name_and_identity("lxmf.propagation", self.app.node.destination.identity))
            e_lxmf = urwid.Text(lxmf_addr_str, align="center")

            announce_button = urwid.Button("Announce", on_press=announce_query)
            connect_button = urwid.Button("Browse", on_press=connect_query)
            reset_button = urwid.Button("Rst Stats", on_press=stats_query)

            pile = urwid.Pile([
                t_id,
                e_name,
                urwid.Divider(g["divider1"]),
                e_lxmf,
                urwid.Divider(g["divider1"]),
                self.t_last_announce,
                self.t_storage_stats,
                self.t_active_links,
                self.t_total_connections,
                self.t_total_pages,
                self.t_total_files,
                urwid.Divider(g["divider1"]),
                urwid.Columns([
                    ("weight", 5, urwid.Button("Back", on_press=show_peer_info)),
                    ("weight", 0.5, urwid.Text("")),
                    ("weight", 6, connect_button),
                    ("weight", 0.5, urwid.Text("")),
                    ("weight", 8, reset_button),
                    ("weight", 0.5, urwid.Text("")),
                    ("weight", 7, announce_button),
                ])
            ])
        else:
            pile = urwid.Pile([
                urwid.Text("\n"+g["info"], align="center"),
                urwid.Text("\nThis instance is not hosting a node\n\n", align="center"),
                urwid.Padding(urwid.Button("Back", on_press=show_peer_info), "center", "pack")
            ])

        self.display_widget = pile

        urwid.WidgetWrap.__init__(self, urwid.AttrMap(urwid.LineBox(self.display_widget, title="Local Node Info"), widget_style))

    def start(self):
        if self.app.node != None:
            self.t_last_announce.start()
            self.t_active_links.start()
            self.t_total_connections.start()
            self.t_total_pages.start()
            self.t_total_files.start()


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

        self.w_heard_peers = UpdatingText(self.app, "Heard Peers: ", get_num_peers, append_text=" (30m)")
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
        elif key == "ctrl g":
            self.parent.toggle_fullscreen()
        elif key == "ctrl e":
            self.parent.selected_node_info()
        elif key == "ctrl p":
            self.parent.reinit_lxmf_peers()
            self.parent.show_peers()
        elif key == "ctrl w":
            self.parent.browser.disconnect()
        elif key == "ctrl u":
            self.parent.browser.url_dialog()
        elif key == "ctrl s":
            self.parent.browser.save_node_dialog()

        else:
            return super(NetworkLeftPile, self).keypress(size, key)


class NetworkDisplay():
    list_width = 0.33
    given_list_width = 52

    def __init__(self, app):
        self.app = app
        g = self.app.ui.glyphs

        self.browser = Browser(self.app, "nomadnetwork", "node", auth_identity = self.app.identity, delegate = self)

        if self.app.node != None:
            self.browser.loopback = self.app.node.destination.hash

        self.known_nodes_display = KnownNodes(self.app)
        self.lxmf_peers_display = LXMFPeers(self.app)
        self.network_stats_display = NetworkStats(self.app, self)
        self.announce_stream_display = AnnounceStream(self.app, self)
        self.local_peer_display = LocalPeer(self.app, self)
        self.node_info_display = NodeInfo(self.app, self)

        self.known_nodes_display.delegate = self

        self.list_display = 1
        self.left_pile = NetworkLeftPile([
            ("weight", 1, self.known_nodes_display),
            # ("pack", self.network_stats_display),
            ("pack", self.local_peer_display),
        ])

        self.left_pile.parent = self

        self.left_area = self.left_pile
        self.right_area = self.browser.display_widget
        self.right_area_width = 1-NetworkDisplay.list_width

        self.columns = urwid.Columns(
            [
                # ("weight", NetworkDisplay.list_width, self.left_area),
                # ("weight", self.right_area_width, self.right_area)
                (NetworkDisplay.given_list_width, self.left_area),
                ("weight", 1, self.right_area)
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

    def toggle_fullscreen(self):
        if NetworkDisplay.given_list_width != 0:
            self.saved_list_width = NetworkDisplay.given_list_width
            NetworkDisplay.given_list_width = 0
        else:
            NetworkDisplay.given_list_width = self.saved_list_width

        options = self.widget.options("given", NetworkDisplay.given_list_width)
        self.widget.contents[0] = (self.left_area, options)

    def show_peers(self):
        options = self.left_pile.options(height_type="weight", height_amount=1)
        self.left_pile.contents[0] = (self.lxmf_peers_display, options)

        if self.list_display != 0:
            self.list_display = 0
        else:
            self.list_display = 1

    def selected_node_info(self):
        if self.list_display == 1:
            parent = self.app.ui.main_display.sub_displays.network_display
            selected_node_entry = parent.known_nodes_display.ilb.get_selected_item()
            if selected_node_entry != None:
                selected_node_hash = selected_node_entry._get_base_widget().display_widget.source_hash
                
                if selected_node_hash != None:
                    info_widget = KnownNodeInfo(selected_node_hash)
                    options = parent.left_pile.options(height_type="weight", height_amount=1)
                    parent.left_pile.contents[0] = (info_widget, options)
    
    def focus_lists(self):
        self.columns.focus_position = 0

    def reinit_known_nodes(self):
        self.known_nodes_display = KnownNodes(self.app)
        self.known_nodes_display.delegate = self
        self.close_list_dialogs()
        self.announce_stream_display.rebuild_widget_list()

    def reinit_lxmf_peers(self):
        self.lxmf_peers_display = LXMFPeers(self.app)
        self.lxmf_peers_display.delegate = self
        self.close_list_dialogs()

    def close_list_dialogs(self):
        if self.list_display == 0:
            options = self.left_pile.options(height_type="weight", height_amount=1)
            self.left_pile.contents[0] = (self.announce_stream_display, options)
        else:
            options = self.left_pile.options(height_type="weight", height_amount=1)
            self.left_pile.contents[0] = (self.known_nodes_display, options)

    def start(self):
        self.local_peer_display.start()
        self.node_info_display.start()
        self.network_stats_display.start()
        # There seems to be an intermittent memory leak somewhere
        # in the periodic updating here. The periodic updater should
        # not be needed anymore, so dis
        #self.announce_stream_display.start()

    def shortcuts(self):
        return self.shortcuts_display

    def directory_change_callback(self):
        self.announce_stream_display.rebuild_widget_list()
        if self.known_nodes_display.no_content:
            self.reinit_known_nodes()
        else:
            self.known_nodes_display.rebuild_widget_list()


class LXMFPeers(urwid.WidgetWrap):
    def __init__(self, app):
        self.app = app
        self.peer_list = app.message_router.peers
        # self.peer_list = {}

        g = self.app.ui.glyphs

        self.widget_list = self.make_peer_widgets()

        self.ilb = IndicativeListBox(
            self.widget_list,
            on_selection_change=self.node_list_selection,
            initialization_is_selection_change=False,
            highlight_offFocus="list_off_focus"
        )

        if len(self.peer_list) > 0:
            self.display_widget = self.ilb
            widget_style = None
            self.no_content = False
        else:
            self.no_content = True
            widget_style = "inactive_text"
            self.pile = urwid.Pile([urwid.Text(("warning_text", g["info"]+"\n"), align="center"), SelectText(("warning_text", "Currently, no LXMF nodes are peered\n\n"), align="center")])
            self.display_widget = urwid.Filler(self.pile, valign="top", height="pack")

        urwid.WidgetWrap.__init__(self, urwid.AttrMap(urwid.LineBox(self.display_widget, title="LXMF Propagation Peers"), widget_style))

    def keypress(self, size, key):
        if key == "up" and (self.no_content or self.ilb.first_item_is_selected()):
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.set_focus("header")
        elif key == "ctrl x":
            self.delete_selected_entry()
            
        return super(LXMFPeers, self).keypress(size, key)


    def node_list_selection(self, arg1, arg2):
        pass

    def delete_selected_entry(self):
        si = self.ilb.get_selected_item()
        if si != None:
            destination_hash = si.original_widget.destination_hash
            self.app.message_router.unpeer(destination_hash)
            self.delegate.reinit_lxmf_peers()
            self.delegate.show_peers()


    def rebuild_widget_list(self):
        self.peer_list = self.app.message_router.peers
        self.widget_list = self.make_peer_widgets()
        self.ilb.set_body(self.widget_list)
        if len(self.widget_list) > 0:
            self.no_content = False
        else:
            self.no_content = True
            self.delegate.reinit_lxmf_peers()

    def make_peer_widgets(self):
        widget_list = []
        for peer_id in self.peer_list:
            peer = self.peer_list[peer_id]
            pe = LXMFPeerEntry(self.app, peer, self)
            pe.destination_hash = peer.destination_hash
            widget_list.append(pe)

        # TODO: Sort list
        return widget_list

class LXMFPeerEntry(urwid.WidgetWrap):
    def __init__(self, app, peer, delegate):
        destination_hash = peer.destination_hash

        self.app = app
        g = self.app.ui.glyphs

        node_identity = RNS.Identity.recall(destination_hash)
        display_str = RNS.prettyhexrep(destination_hash)
        if node_identity != None:            
            node_hash = RNS.Destination.hash_from_name_and_identity("nomadnetwork.node", node_identity)
            display_name = self.app.directory.alleged_display_str(node_hash)
            if display_name != None:
                display_str += " "+str(display_name)

        sym = g["sent"]
        style         = "list_unknown"
        focus_style   = "list_focus"

        alive_string = "Unknown"
        if hasattr(peer, "alive"):
            if peer.alive:
                alive_string = "Available"
            else:
                alive_string = "Unresponsive"

        widget = ListEntry(sym+" "+display_str+"\n  "+alive_string+", last heard "+pretty_date(int(peer.last_heard))+"\n  "+str(len(peer.unhandled_messages))+" unhandled LXMs")
        # urwid.connect_signal(widget, "click", delegate.connect_node, node)

        self.display_widget = urwid.AttrMap(widget, style, focus_style)
        self.display_widget.destination_hash = destination_hash
        urwid.WidgetWrap.__init__(self, self.display_widget)


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
