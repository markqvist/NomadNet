import RNS
import time
import nomadnet

import urwid

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


class ConversationListDisplayShortcuts():
    def __init__(self, app):
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("Conversation List Display Shortcuts"), "shortcutbar")

class ConversationDisplayShortcuts():
    def __init__(self, app):
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("[C-s] Send"), "shortcutbar")

class ConversationsDisplay():
    list_width = 0.33
    cached_conversation_widgets = {}

    def __init__(self, app):
        from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox

        self.app = app

        conversation_list_widgets = []
        for conversation in app.conversations():
            conversation_list_widgets.append(self.conversation_list_widget(conversation))

        def disp_list_shortcuts(sender, arg1, arg2):
            self.shortcuts_display = self.list_shortcuts
            self.app.ui.main_display.update_active_shortcuts()
            RNS.log("Modified")

        walker = urwid.SimpleFocusListWalker(conversation_list_widgets)
        ilb = IndicativeListBox(conversation_list_widgets)
        listbox = urwid.LineBox(urwid.Filler(ilb, height=("relative", 100)))

        columns_widget = urwid.Columns([("weight", ConversationsDisplay.list_width, listbox), ("weight", 1-ConversationsDisplay.list_width, self.make_conversation_widget(None))], dividechars=0, focus_column=0, box_columns=[0])

        self.list_shortcuts = ConversationListDisplayShortcuts(self.app)
        self.editor_shortcuts = ConversationDisplayShortcuts(self.app)

        self.shortcuts_display = self.list_shortcuts
        self.widget = columns_widget

    def display_conversation(self, sender=None, source_hash=None):
        options = self.widget.options("weight", 1-ConversationsDisplay.list_width)
        self.widget.contents[1] = (self.make_conversation_widget(source_hash), options)
        

    def make_conversation_widget(self, source_hash):
        time_format = self.app.time_format
        class LXMessageWidget(urwid.WidgetWrap):
            def __init__(self, message):
                title_string = time.strftime(time_format)
                if message.get_title() != "":
                    title_string += " | " + message.get_title()
                if message.signature_validated():
                    header_style = "msg_header_ok"
                else:
                    header_style = "msg_header_caution"
                    title_string = "\u26A0 "+message.get_signature_description() + "\n" + title_string

                title = urwid.AttrMap(urwid.Text(title_string), header_style)

                display_widget = urwid.Pile([
                    title,
                    urwid.Text(message.get_content()),
                    urwid.Text("")
                ])

                urwid.WidgetWrap.__init__(self, display_widget)

        if source_hash == None:
            return urwid.LineBox(urwid.Filler(urwid.Text("No conversation selected"), "top"))
        else:
            if source_hash in ConversationsDisplay.cached_conversation_widgets:
                return ConversationsDisplay.cached_conversation_widgets[source_hash]
            else:
                conversation = nomadnet.Conversation(source_hash, self.app)
                message_widgets = []

                for message in conversation.messages:
                    message_widget = LXMessageWidget(message)
                    message_widgets.append(message_widget)


                from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox
                messagelist = IndicativeListBox(message_widgets)
                msg_editor  = urwid.Edit(caption="\u270E", edit_text="", multiline=True)

                widget = urwid.LineBox(
                    urwid.Frame(
                        messagelist,
                        footer=urwid.AttrMap(msg_editor, "msg_editor")
                    )
                )

                def disp_editor_shortcuts(sender, arg1, arg2):
                    self.shortcuts_display = self.editor_shortcuts
                    self.app.ui.main_display.update_active_shortcuts()

                urwid.connect_signal(msg_editor, "change", disp_editor_shortcuts, "modified event")
                
                ConversationsDisplay.cached_conversation_widgets[source_hash] = widget
                return widget


    def conversation_list_widget(self, conversation):
        #widget = urwid.SelectableIcon(str(conversation), cursor_position=-1)
        widget = ListEntry(str(conversation))
        urwid.connect_signal(widget, "click", self.display_conversation, conversation)
        return urwid.AttrMap(widget, None, "list_focus")


    def shortcuts(self):
        focus_path = self.widget.get_focus_path()
        if focus_path[0] == 0:
            return self.list_shortcuts
        elif focus_path[0] == 1:
            return self.editor_shortcuts
        else:
            return self.list_shortcuts