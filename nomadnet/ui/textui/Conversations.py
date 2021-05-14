import RNS
import time
import nomadnet
import LXMF

import urwid

from datetime import datetime
from nomadnet.Directory import DirectoryEntry

class ConversationListDisplayShortcuts():
    def __init__(self, app):
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("[Enter] Open  [C-e] Directory Entry  [C-x] Delete  [C-n] New"), "shortcutbar")

class ConversationDisplayShortcuts():
    def __init__(self, app):
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("[C-d] Send  [C-k] Clear  [C-t] Add Title  [C-w] Close Conversation  [C-p] Purge Failed"), "shortcutbar")

class ConversationsArea(urwid.LineBox):
    def keypress(self, size, key):
        if key == "ctrl e":
            self.delegate.edit_selected_in_directory()
        elif key == "ctrl x":
            self.delegate.delete_selected_conversation()
        elif key == "ctrl n":
            self.delegate.new_conversation()
        else:
            return super(ConversationsArea, self).keypress(size, key)

class ConversationsDisplay():
    list_width = 0.33
    cached_conversation_widgets = {}

    def __init__(self, app):
        self.app = app
        self.dialog_open = False

        def disp_list_shortcuts(sender, arg1, arg2):
            self.shortcuts_display = self.list_shortcuts
            self.app.ui.main_display.update_active_shortcuts()

        self.update_listbox()

        self.columns_widget = urwid.Columns([("weight", ConversationsDisplay.list_width, self.listbox), ("weight", 1-ConversationsDisplay.list_width, self.make_conversation_widget(None))], dividechars=0, focus_column=0, box_columns=[0])

        self.list_shortcuts = ConversationListDisplayShortcuts(self.app)
        self.editor_shortcuts = ConversationDisplayShortcuts(self.app)

        self.shortcuts_display = self.list_shortcuts
        self.widget = self.columns_widget
        nomadnet.Conversation.created_callback = self.update_conversation_list

    def focus_change_event(self):
        # This hack corrects buggy styling behaviour in IndicativeListBox
        if not self.dialog_open:
            ilb_position = self.ilb.get_selected_position()
            self.update_conversation_list()
            if ilb_position != None:
                self.ilb.select_item(ilb_position)

    def update_listbox(self):
        
        from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox

        conversation_list_widgets = []
        for conversation in self.app.conversations():
            conversation_list_widgets.append(self.conversation_list_widget(conversation))

        walker = urwid.SimpleFocusListWalker(conversation_list_widgets)
        self.list_widgets = conversation_list_widgets
        self.ilb = IndicativeListBox(
            self.list_widgets,
            on_selection_change=self.conversation_list_selection,
            initialization_is_selection_change=False,
            highlight_offFocus="list_off_focus"
        )

        self.listbox = ConversationsArea(urwid.Filler(self.ilb, height=("relative", 100)))
        self.listbox.delegate = self

    def delete_selected_conversation(self):
        self.dialog_open = True
        source_hash = self.ilb.get_selected_item().source_hash

        def dismiss_dialog(sender):
            self.update_conversation_list()
            self.dialog_open = False

        def confirmed(sender):
            self.dialog_open = False
            self.delete_conversation(source_hash)
            nomadnet.Conversation.delete_conversation(source_hash, self.app)
            self.update_conversation_list()

        dialog = urwid.LineBox(
            urwid.Pile([
                urwid.Text("Delete conversation with\n"+self.app.directory.simplest_display_str(bytes.fromhex(source_hash))+"\n", align="center"),
                urwid.Columns([("weight", 0.45, urwid.Button("Yes", on_press=confirmed)), ("weight", 0.1, urwid.Text("")), ("weight", 0.45, urwid.Button("No", on_press=dismiss_dialog))])
            ]), title="?"
        )
        bottom = self.listbox

        overlay = urwid.Overlay(dialog, bottom, align="center", width=("relative", 100), valign="middle", height="pack", left=2, right=2)

        options = self.columns_widget.options("weight", ConversationsDisplay.list_width)
        self.columns_widget.contents[0] = (overlay, options)

    def edit_selected_in_directory(self):
        self.dialog_open = True
        source_hash_text = self.ilb.get_selected_item().source_hash
        display_name = self.ilb.get_selected_item().display_name

        e_id = urwid.Edit(caption="ID   : ",edit_text=source_hash_text)
        t_id = urwid.Text("ID   : "+source_hash_text)
        e_name = urwid.Edit(caption="Name : ",edit_text=display_name)

        selected_id_widget = t_id

        untrusted_selected = False
        unknown_selected   = True
        trusted_selected   = False

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
        except Exception as e:
            RNS.log("EXC: "+str(e))

        trust_button_group = []
        r_untrusted = urwid.RadioButton(trust_button_group, "Untrusted", state=untrusted_selected)
        r_unknown   = urwid.RadioButton(trust_button_group, "Unknown", state=unknown_selected)
        r_trusted   = urwid.RadioButton(trust_button_group, "Trusted", state=trusted_selected)

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

                entry = DirectoryEntry(source_hash, display_name, trust_level)
                self.app.directory.remember(entry)
                self.update_conversation_list()
                self.dialog_open = False
            except Exception as e:
                RNS.log("Could not save directory entry. The contained exception was: "+str(e), RNS.LOG_VERBOSE)
                if not dialog_pile.error_display:
                    dialog_pile.error_display = True
                    options = dialog_pile.options(height_type="pack")
                    dialog_pile.contents.append((urwid.Text(""), options))
                    dialog_pile.contents.append((urwid.Text(("error_text", "Could not save entry. Check your input."), align="center"), options))

        dialog_pile = urwid.Pile([
            selected_id_widget,
            e_name,
            urwid.Text(""),
            r_untrusted,
            r_unknown,
            r_trusted,
            urwid.Text(""),
            urwid.Columns([("weight", 0.45, urwid.Button("Save", on_press=confirmed)), ("weight", 0.1, urwid.Text("")), ("weight", 0.45, urwid.Button("Cancel", on_press=dismiss_dialog))])
        ])
        dialog_pile.error_display = False

        dialog = urwid.LineBox(dialog_pile, title="Edit Directory Entry")
        bottom = self.listbox

        overlay = urwid.Overlay(dialog, bottom, align="center", width=("relative", 100), valign="middle", height="pack", left=2, right=2)

        options = self.columns_widget.options("weight", ConversationsDisplay.list_width)
        self.columns_widget.contents[0] = (overlay, options)

    def new_conversation(self):
        self.dialog_open = True
        source_hash = ""
        display_name = ""

        e_id = urwid.Edit(caption="ID   : ",edit_text=source_hash)
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
                source_hash_text = e_id.get_edit_text()
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
                    options = dialog_pile.options(height_type="pack")
                    dialog_pile.contents.append((urwid.Text(""), options))
                    dialog_pile.contents.append((urwid.Text(("error_text", "Could not start conversation. Check your input."), align="center"), options))

        dialog_pile = urwid.Pile([
            e_id,
            e_name,
            urwid.Text(""),
            r_untrusted,
            r_unknown,
            r_trusted,
            urwid.Text(""),
            urwid.Columns([("weight", 0.45, urwid.Button("Start", on_press=confirmed)), ("weight", 0.1, urwid.Text("")), ("weight", 0.45, urwid.Button("Cancel", on_press=dismiss_dialog))])
        ])
        dialog_pile.error_display = False

        dialog = urwid.LineBox(dialog_pile, title="New Conversation")
        bottom = self.listbox

        overlay = urwid.Overlay(dialog, bottom, align="center", width=("relative", 100), valign="middle", height="pack", left=2, right=2)

        options = self.columns_widget.options("weight", ConversationsDisplay.list_width)
        self.columns_widget.contents[0] = (overlay, options)

    def delete_conversation(self, source_hash):
        if source_hash in ConversationsDisplay.cached_conversation_widgets:
            conversation = ConversationsDisplay.cached_conversation_widgets[source_hash]
            self.close_conversation(conversation)

    def conversation_list_selection(self, arg1, arg2):
        pass

    def update_conversation_list(self):
        ilb_position = self.ilb.get_selected_position()
        self.update_listbox()
        options = self.columns_widget.options("weight", ConversationsDisplay.list_width)
        self.columns_widget.contents[0] = (self.listbox, options)
        if ilb_position != None:
            self.ilb.select_item(ilb_position)
        nomadnet.NomadNetworkApp.get_shared_instance().ui.loop.draw_screen()




    def display_conversation(self, sender=None, source_hash=None):
        self.currently_displayed_conversation = source_hash
        options = self.widget.options("weight", 1-ConversationsDisplay.list_width)
        self.widget.contents[1] = (self.make_conversation_widget(source_hash), options)
        

    def make_conversation_widget(self, source_hash):
        if source_hash in ConversationsDisplay.cached_conversation_widgets:
            conversation_widget = ConversationsDisplay.cached_conversation_widgets[source_hash]
            if source_hash != None:
                conversation_widget.update_message_widgets(replace=True)
            return conversation_widget
        else:
            widget = ConversationWidget(source_hash)
            widget.delegate = self
            ConversationsDisplay.cached_conversation_widgets[source_hash] = widget
            return widget

    def close_conversation(self, conversation):
        ConversationsDisplay.cached_conversation_widgets.pop(conversation.source_hash)
        self.display_conversation(sender=None, source_hash=None)


    def conversation_list_widget(self, conversation):
        trust_level  = conversation[2]
        display_name = conversation[1]
        source_hash  = conversation[0]

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

        display_text = symbol
        if display_name != None:
            display_text += " "+display_name

        if trust_level != DirectoryEntry.TRUSTED:
            display_text += " <"+source_hash+">"

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
        elif key == "ctrl k":
            self.delegate.clear_editor()
        else:
            return super(MessageEdit, self).keypress(size, key)


class ConversationWidget(urwid.WidgetWrap):
    def __init__(self, source_hash):
        if source_hash == None:
            display_widget = urwid.LineBox(urwid.Filler(urwid.Text("No conversation selected"), "top"))
            urwid.WidgetWrap.__init__(self, display_widget)
        else:
            if source_hash in ConversationsDisplay.cached_conversation_widgets:
                return ConversationsDisplay.cached_conversation_widgets[source_hash]
            else:
                self.source_hash = source_hash
                self.conversation = nomadnet.Conversation(source_hash, nomadnet.NomadNetworkApp.get_shared_instance())
                self.message_widgets = []
                self.updating_message_widgets = False

                self.update_message_widgets()

                self.conversation.register_changed_callback(self.conversation_changed)

                msg_editor  = MessageEdit(caption="\u270E", edit_text="", multiline=True)
                msg_editor.delegate = self

                header = None
                if self.conversation.trust_level == DirectoryEntry.UNTRUSTED:
                    header = urwid.AttrMap(urwid.Padding(urwid.Text("\u26A0 Warning: Conversation with untrusted peer \u26A0", align="center")), "msg_warning_untrusted")

                self.editor = msg_editor

                self.frame = urwid.Frame(
                    self.messagelist,
                    header=header,
                    footer=urwid.AttrMap(msg_editor, "msg_editor")
                )

                self.display_widget = urwid.LineBox(
                    self.frame
                )
                
                urwid.WidgetWrap.__init__(self, self.display_widget)

    def keypress(self, size, key):
        if key == "ctrl w":
            self.close()
        elif key == "ctrl p":
            self.conversation.purge_failed()
            self.conversation_changed(None)
        else:
            return super(ConversationWidget, self).keypress(size, key)

    def conversation_changed(self, conversation):
        self.update_message_widgets(replace = True)

    def update_message_widgets(self, replace = False):
        while self.updating_message_widgets:
            time.sleep(0.5)

        self.updating_message_widgets = True
        self.message_widgets = []
        added_hashes = []
        for message in self.conversation.messages:
            message_hash = message.get_hash()
            if not message_hash in added_hashes:
                added_hashes.append(message_hash)
                message_widget = LXMessageWidget(message)
                self.message_widgets.append(message_widget)
        
        self.message_widgets.sort(key=lambda m: m.timestamp, reverse=False)

        from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox
        self.messagelist = IndicativeListBox(self.message_widgets, position = len(self.message_widgets)-1)

        if replace:
            self.frame.contents["body"] = (self.messagelist, None)
            nomadnet.NomadNetworkApp.get_shared_instance().ui.loop.draw_screen()

        self.updating_message_widgets = False


    def clear_editor(self):
        self.editor.set_edit_text("")

    def send_message(self):
        content = self.editor.get_edit_text()
        if not content == "":
            self.conversation.send(content)
            self.clear_editor()

    def close(self):
        self.delegate.close_conversation(self)


class LXMessageWidget(urwid.WidgetWrap):
    def __init__(self, message):
        app = nomadnet.NomadNetworkApp.get_shared_instance()
        self.timestamp = message.get_timestamp()
        time_format = app.time_format
        message_time = datetime.fromtimestamp(self.timestamp)
        title_string = message_time.strftime(time_format)

        if app.lxmf_destination.hash == message.lxm.source_hash:
            if message.lxm.state == LXMF.LXMessage.DELIVERED:
                header_style = "msg_header_delivered"
                title_string = "\u2713 " + title_string
            elif message.lxm.state == LXMF.LXMessage.FAILED:
                header_style = "msg_header_failed"
                title_string = "\u2715 " + title_string
            else:
                header_style = "msg_header_sent"
                title_string = "\u2192 " + title_string
        else:
            if message.signature_validated():
                header_style = "msg_header_ok"
                title_string = "\u2713 " + title_string
            else:
                header_style = "msg_header_caution"
                title_string = "\u26A0 "+message.get_signature_description() + "\n  " + title_string

        if message.get_title() != "":
            title_string += " | " + message.get_title()

        title = urwid.AttrMap(urwid.Text(title_string), header_style)

        display_widget = urwid.Pile([
            title,
            urwid.Text(message.get_content()),
            urwid.Text("")
        ])

        urwid.WidgetWrap.__init__(self, display_widget)