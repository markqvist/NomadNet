import RNS
import os
import shutil
import time
import nomadnet
import LXMF

import urwid

from datetime import datetime, timedelta
from nomadnet.Directory import DirectoryEntry
from nomadnet.Conversation import ConversationMessage

from nomadnet.util import strip_modifiers
from nomadnet.util import sanitize_name


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

        self.widget = urwid.AttrMap(urwid.Text("[C-e] Peer Info  [C-x] Delete  [C-r] Sync  [C-n] New  [C-u] Ingest URI  [C-o] Sort  [C-g] Fullscreen"), "shortcutbar")

class ConversationDisplayShortcuts():
    def __init__(self, app):
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("[C-d] Send  [C-p] Paper Msg  [C-t] Title  [C-a] Attach  [C-s] Save  [C-k] Clear  [C-w] Close  [C-u] Purge  [C-x] Clear History  [C-o] Sort"), "shortcutbar")

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
        elif key == "tab":
            self.delegate.app.ui.main_display.frame.focus_position = "header"
        elif key == "up" and (self.delegate.ilb.first_item_is_selected() or self.delegate.ilb.body_is_empty()):
            self.delegate.app.ui.main_display.frame.focus_position = "header"
        else:
            return super(ConversationsArea, self).keypress(size, key)

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

    def __init__(self, app):
        self.app = app
        self.dialog_open = False
        self.sync_dialog = None
        self.currently_displayed_conversation = None
        self.list_sort_mode = ConversationsDisplay.SORT_RECENT

        def disp_list_shortcuts(sender, arg1, arg2):
            self.shortcuts_display = self.list_shortcuts
            self.app.ui.main_display.update_active_shortcuts()

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

        self.shortcuts_display = self.list_shortcuts
        self.widget = self.columns_widget
        nomadnet.Conversation.created_callback = self.update_conversation_list

    def focus_change_event(self):
        if not self.dialog_open:
            self.update_conversation_list()

    def toggle_list_sort(self):
        if self.list_sort_mode == ConversationsDisplay.SORT_RECENT:
            self.list_sort_mode = ConversationsDisplay.SORT_NAME
        else:
            self.list_sort_mode = ConversationsDisplay.SORT_RECENT
        self.update_conversation_list()

    def update_listbox(self):
        conversations = self.app.conversations()
        if self.list_sort_mode == ConversationsDisplay.SORT_NAME:
            conversations.sort(key=lambda e: (e[3].lower(), e[0]))

        conversation_list_widgets = []
        for conversation in conversations:
            conversation_list_widgets.append(self.conversation_list_widget(conversation))

        self.list_widgets = conversation_list_widgets
        self.ilb = IndicativeListBox(
            self.list_widgets,
            on_selection_change=self.conversation_list_selection,
            initialization_is_selection_change=False,
            highlight_offFocus="list_off_focus"
        )

        self.listbox = ConversationsArea(urwid.Filler(self.ilb, height=urwid.RELATIVE_100), title="Conversations")
        self.listbox.delegate = self

    def delete_selected_conversation(self):
        self.dialog_open = True
        item = self.ilb.get_selected_item()
        if item == None:
            return
        source_hash = item.source_hash

        def dismiss_dialog(sender):
            self.update_conversation_list()
            self.dialog_open = False

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

    def edit_selected_in_directory(self):
        g = self.app.ui.glyphs
        self.dialog_open = True
        item = self.ilb.get_selected_item()
        if item == None:
            return
        source_hash_text = item.source_hash
        display_name = self.ilb.get_selected_item().display_name
        if display_name == None:
            display_name = ""

        e_id = urwid.Edit(caption="Addr : ",edit_text=source_hash_text)
        t_id = urwid.Text("Addr : "+source_hash_text)
        e_name = urwid.Edit(caption="Name : ",edit_text=display_name)

        selected_id_widget = t_id

        untrusted_selected  = False
        unknown_selected    = True
        trusted_selected    = False

        direct_selected     = True
        propagated_selected = False

        try:
            if self.app.directory.find(bytes.fromhex(source_hash_text)):
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

                if self.app.directory.preferred_delivery(bytes.fromhex(source_hash_text)) == DirectoryEntry.PROPAGATED:
                    direct_selected = False
                    propagated_selected = True
                    
        except Exception as e:
            pass

        trust_button_group = []
        r_untrusted = urwid.RadioButton(trust_button_group, "Untrusted", state=untrusted_selected)
        r_unknown   = urwid.RadioButton(trust_button_group, "Unknown", state=unknown_selected)
        r_trusted   = urwid.RadioButton(trust_button_group, "Trusted", state=trusted_selected)

        method_button_group = []
        r_direct     = urwid.RadioButton(method_button_group, "Deliver directly", state=direct_selected)
        r_propagated = urwid.RadioButton(method_button_group, "Use propagation nodes", state=propagated_selected)

        def dismiss_dialog(sender):
            self.update_conversation_list()
            self.dialog_open = False

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

                entry = DirectoryEntry(source_hash, display_name, trust_level, preferred_delivery=delivery)
                self.app.directory.remember(entry)
                self.update_conversation_list()
                self.dialog_open = False
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

        dialog_pile = urwid.Pile([
            selected_id_widget,
            e_name,
            urwid.Divider(g["divider1"]),
            r_untrusted,
            r_unknown,
            r_trusted,
            urwid.Divider(g["divider1"]),
            r_direct,
            r_propagated,
            known_section,
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

        e_id = urwid.Edit(caption="Addr : ",edit_text=source_hash)
        e_name = urwid.Edit(caption="Name : ",edit_text=display_name)

        trust_button_group = []
        r_untrusted = urwid.RadioButton(trust_button_group, "Untrusted")
        r_unknown   = urwid.RadioButton(trust_button_group, "Unknown", state=True)
        r_trusted   = urwid.RadioButton(trust_button_group, "Trusted")

        def dismiss_dialog(sender):
            self.update_conversation_list()
            self.dialog_open = False

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

                if not source_hash in [c[0] for c in existing_conversations]:
                    entry = DirectoryEntry(source_hash, display_name, trust_level)
                    self.app.directory.remember(entry)

                    new_conversation = nomadnet.Conversation(source_hash_text, nomadnet.NomadNetworkApp.get_shared_instance(), initiator=True)

                    self.update_conversation_list()

                self.display_conversation(source_hash_text)
                self.dialog_open = False

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
        e_uri = urwid.Edit(caption="URI : ",edit_text=lxm_uri)

        def dismiss_dialog(sender):
            self.update_conversation_list()
            self.dialog_open = False

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

        pn_ident = None
        if self.app.get_default_propagation_node() != None:
            pn_hash = self.app.get_default_propagation_node()
            pn_ident = RNS.Identity.recall(pn_hash)

            if pn_ident == None:
                RNS.log("Propagation node identity is unknown, requesting from network...", RNS.LOG_DEBUG)
                RNS.Transport.request_path(pn_hash)

        if pn_ident != None:
            node_hash = RNS.Destination.hash_from_name_and_identity("nomadnetwork.node", pn_ident)
            pn_entry = self.app.directory.find(node_hash)
            pn_display_str = " "
            if pn_entry != None:
                pn_display_str += " "+str(pn_entry.display_name)
            else:
                pn_display_str += " "+RNS.prettyhexrep(pn_hash)

            dialog = DialogLineBox(
                urwid.Pile([
                    urwid.Text(""+g["node"]+pn_display_str, align=urwid.CENTER),
                    urwid.Divider(g["divider1"]),
                    sync_progress,
                    urwid.Divider(g["divider1"]),
                    r_mall,
                    rbs,
                    urwid.Text(""),
                    button_columns
                ]), title="Message Sync"
            )
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
        if not (self.dialog_open and self.sync_dialog != None):
            self.columns_widget.contents[0] = (self.listbox, options)
        else:
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

        if selected_hash is not None:
            for idx, widget in enumerate(self.list_widgets):
                if widget.source_hash == selected_hash:
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
        # options = self.widget.options(urwid.WEIGHT, 1-ConversationsDisplay.list_width)
        options = self.widget.options(urwid.WEIGHT, 1)
        self.widget.contents[1] = (self.make_conversation_widget(source_hash), options)
        if source_hash == None:
            self.widget.focus_position = 0
        else:
            if self.app.conversation_is_unread(source_hash):
                self.app.mark_conversation_read(source_hash)
                self.update_conversation_list()

            self.widget.focus_position = 1
            conversation_position = None
            index = 0
            for widget in self.list_widgets:
                if widget.source_hash == source_hash:
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
            widget = ConversationWidget(source_hash)
            widget.delegate = self
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

        display_text = symbol

        if display_name != None and display_name != "":
            display_text += " "+display_name

        if trust_level != DirectoryEntry.TRUSTED:
            display_text += " <"+source_hash+">"
        
        if trust_level != DirectoryEntry.UNTRUSTED:
            if unread:
                if source_hash != self.currently_displayed_conversation:
                    if unread > 1:
                        display_text += " "+g["unread"]+" ("+str(unread)+")"
                    else:
                        display_text += " "+g["unread"]


        if last_activity > 0:
            display_text += "\n  "+relative_time(last_activity)

        widget = ListEntry(display_text)
        urwid.connect_signal(widget, "click", self.display_conversation, conversation[0])
        display_widget = urwid.AttrMap(widget, style, focus_style)
        display_widget.source_hash = source_hash
        display_widget.display_name = display_name

        return display_widget


    def shortcuts(self):
        focus_path = self.widget.get_focus_path()
        if focus_path[0] == 0:
            return self.list_shortcuts
        elif focus_path[0] == 1:
            return self.editor_shortcuts
        else:
            return self.list_shortcuts

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

class MessageEdit(urwid.Edit):
    def keypress(self, size, key):
        if key == "ctrl d":
            self.delegate.send_message()
        elif key == "ctrl p":
            self.delegate.paper_message()
        elif key == "ctrl a":
            self.delegate.attach_file()
        elif key == "ctrl s":
            self.delegate.save_focused_attachments()
        elif key == "ctrl k":
            self.delegate.clear_editor()
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
    def keypress(self, size, key):
        if self.focus_position == "body":
            if getattr(self.delegate, "dialog_active", False) or getattr(self.delegate, "dialog_open", False):
                return super(ConversationFrame, self).keypress(size, key)
            elif key == "up" and self.delegate.messagelist.top_is_visible:
                nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.focus_position = "header"
            elif key == "down" and self.delegate.messagelist.bottom_is_visible:
                self.focus_position = "footer"
            else:
                return super(ConversationFrame, self).keypress(size, key)
        elif key == "ctrl k":
            self.delegate.clear_editor()
        else:
            return super(ConversationFrame, self).keypress(size, key)

class ConversationWidget(urwid.WidgetWrap):
    def __init__(self, source_hash):
        self.app = nomadnet.NomadNetworkApp.get_shared_instance()
        g = self.app.ui.glyphs
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
                self.updating_message_widgets = False
                self.pending_attachments = []
                self.dialog_active = False

                self.update_message_widgets()

                self.conversation.register_changed_callback(self.conversation_changed)

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

                header_widgets = [self.peer_info_widget]
                if self.conversation.trust_level == DirectoryEntry.UNTRUSTED:
                    header_widgets.append(urwid.AttrMap(
                        urwid.Padding(
                            urwid.Text(g["warning"]+" Warning: Conversation with untrusted peer "+g["warning"], align=urwid.CENTER)),
                        "msg_warning_untrusted",
                    ))
                header = urwid.Pile(header_widgets)

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

        right_parts = []
        if stamp_cost is not None:
            right_parts.append("Stamp: "+str(stamp_cost))
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
                self.frame.contents["footer"] = (self._build_footer(), None)
            else:
                warning = urwid.AttrMap(
                    urwid.Padding(urwid.Text(
                        "\n"+g["info"]+"\n\nYou cannot currently message this peer, since its identity keys are not known. "
                                       "The keys have been requested from the network and should arrive shortly, if available. "
                                       "Close this conversation and reopen it to try again.\n\n"
                                       "To query the network manually, select this conversation in the conversation list, "
                                       "press Ctrl-E, and use the query button.\n",
                        align=urwid.CENTER,
                    )),
                    "msg_header_caution",
                )
                self.frame.contents["footer"] = (warning, None)

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
        elif key == "ctrl w":
            self.close()
        elif key == "ctrl u":
            self.conversation.purge_failed()
            self.conversation_changed(None)
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
        else:
            return super(ConversationWidget, self).keypress(size, key)

    def conversation_changed(self, conversation):
        if hasattr(self, "peer_info_widget"):
            self._update_peer_info()
        self.update_message_widgets(replace = True)

    def update_message_widgets(self, replace = False):
        while self.updating_message_widgets:
            time.sleep(0.5)

        self.updating_message_widgets = True
        self.message_widgets = []
        added_hashes = []
        needs_index = []
        for message in self.conversation.messages:
            message_hash = message.get_hash()
            if not message_hash in added_hashes:
                added_hashes.append(message_hash)
                was_loaded = message.loaded
                message_widget = LXMessageWidget(message)
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
        self.messagelist = IndicativeListBox(self.message_widgets, position = len(self.message_widgets)-1)
        self.messagelist.name = "messagelist"
        if replace:
            self.frame.contents["body"] = (self.messagelist, None)
            nomadnet.NomadNetworkApp.get_shared_instance().ui.loop.draw_screen()

        self.updating_message_widgets = False


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

            if self.conversation.send(content, title, fields=fields):
                self.clear_editor()

    def attach_file(self):
        self.dialog_active = True
        browser = FileBrowserDialog(self)
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
    def __init__(self, message):
        app = nomadnet.NomadNetworkApp.get_shared_instance()
        g = app.ui.glyphs
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

        has_attachments = message.has_attachments()
        cached_names = message._cached_attachment_names or []

        if has_attachments and cached_names:
            attachment_strings = []
            for atype, aname, *arest in cached_names:
                attachment_strings.append(g[atype if atype != "file" else "file"]+" "+aname)
            title_string += " | " + " ".join(attachment_strings)

        title = urwid.AttrMap(urwid.Text(title_string), header_style)

        self.progress_widget = urwid.Text("")
        self.progress_attr = urwid.AttrMap(self.progress_widget, "progress_full")

        content_text = message.get_content()
        content_lines = content_text.split("\n")
        indented = "\n".join("  "+line for line in content_lines)

        pile_widgets = [title]

        if is_outbound and msg_state is not None and msg_state < LXMF.LXMessage.SENT and msg_hash is not None:
            try:
                for pending in app.message_router.pending_outbound:
                    if pending.hash == msg_hash:
                        if pending.representation == LXMF.LXMessage.RESOURCE:
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
                pile_widgets.append(self.progress_attr)
                self._start_progress_poll()

        pile_widgets.append(urwid.Text(indented))

        if has_attachments and cached_names:
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


def _copy_attachment_to_dest(filename, src_path):
    app = nomadnet.NomadNetworkApp.get_shared_instance()
    save_dir = app.attachment_save_path if app.attachment_save_path else app.downloads_path
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir)
    save_path = os.path.join(save_dir, filename)
    counter = 0
    base, ext = os.path.splitext(filename)
    while os.path.isfile(save_path):
        counter += 1
        save_path = os.path.join(save_dir, base+"_"+str(counter)+ext)
    shutil.copy2(src_path, save_path)
    return save_path


def _save_attachment_to_disk(filename, data):
    app = nomadnet.NomadNetworkApp.get_shared_instance()
    save_dir = app.attachment_save_path if app.attachment_save_path else app.downloads_path
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir)
    save_path = os.path.join(save_dir, filename)
    counter = 0
    base, ext = os.path.splitext(filename)
    while os.path.isfile(save_path):
        counter += 1
        save_path = os.path.join(save_dir, base+"_"+str(counter)+ext)
    with open(save_path, "wb") as f:
        f.write(data)
    return save_path


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


class FileBrowserDialog(urwid.WidgetWrap):
    def __init__(self, delegate):
        self.delegate = delegate
        app = nomadnet.NomadNetworkApp.get_shared_instance()
        self.g = app.ui.glyphs
        self.current_path = os.path.expanduser("~")

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

        self.browser_frame = urwid.Frame(
            self.file_listbox,
            header=header_pile,
            footer=footer_pile,
        )

        linebox = urwid.LineBox(self.browser_frame, title="Attach File")
        super().__init__(linebox)

    def _update_status(self):
        pending = self.delegate.pending_attachments
        if pending:
            names = [os.path.basename(p) for p in pending]
            self.status_label.set_text("  "+self.g["file"]+" "+str(len(pending))+" selected: "+", ".join(names))
        else:
            self.status_label.set_text("  No files selected")

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
            is_selected = full in self.delegate.pending_attachments
            entry = FileBrowserEntry(name, full, selected=is_selected)
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
        else:
            if entry.full_path in self.delegate.pending_attachments:
                self.delegate.pending_attachments.remove(entry.full_path)
            else:
                self.delegate.pending_attachments.append(entry.full_path)
            self.delegate.frame.contents["footer"] = (self.delegate._build_footer(), None)
            self._populate()

    def _dismiss(self, sender):
        self.delegate.file_browser_closed()

    def _cancel(self, sender):
        self.delegate.pending_attachments.clear()
        self.delegate.frame.contents["footer"] = (self.delegate._build_footer(), None)
        self.delegate.file_browser_closed()

    def keypress(self, size, key):
        if key == "esc":
            self.delegate.file_browser_closed()
            return
        result = super().keypress(size, key)
        if result == "down" and self.browser_frame.focus_position == "body":
            self.browser_frame.focus_position = "footer"
            return
        elif result == "up" and self.browser_frame.focus_position == "footer":
            self.browser_frame.focus_position = "body"
            return
        return result


class SyncProgressBar(urwid.ProgressBar):
    def get_text(self):
        status = nomadnet.NomadNetworkApp.get_shared_instance().get_sync_status()
        show_percent = nomadnet.NomadNetworkApp.get_shared_instance().sync_status_show_percent()
        if show_percent:
            return status+" "+super().get_text()
        else:
            return status
