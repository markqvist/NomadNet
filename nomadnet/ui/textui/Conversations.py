import RNS
import time
import nomadnet

class ConversationsDisplayShortcuts():
    def __init__(self, app):
        import urwid
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("Conversations Display Shortcuts"), "shortcutbar")

class ConversationsDisplay():
    list_width = 0.33
    cached_conversation_widgets = {}

    def __init__(self, app):
        import urwid
        from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox

        self.app = app

        conversation_list_widgets = []
        for conversation in app.conversations():
            conversation_list_widgets.append(self.conversation_list_widget(conversation))

        walker = urwid.SimpleFocusListWalker(conversation_list_widgets)
        listbox = urwid.LineBox(urwid.Filler(IndicativeListBox(conversation_list_widgets), height=("relative", 100)))

        columns_widget = urwid.Columns([("weight", ConversationsDisplay.list_width, listbox), ("weight", 1-ConversationsDisplay.list_width, self.make_conversation_widget(None))], dividechars=0, focus_column=0, box_columns=[0])

        self.shortcuts_display = ConversationsDisplayShortcuts(self.app)
        self.widget = columns_widget

    def display_conversation(self, sender=None, source_hash=None):
        options = self.widget.options("weight", 1-ConversationsDisplay.list_width)
        self.widget.contents[1] = (self.make_conversation_widget(source_hash), options)
        

    def make_conversation_widget(self, source_hash):
        time_format = self.app.time_format
        import urwid
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
                widget = urwid.LineBox(
                    urwid.Frame(
                        messagelist,
                        footer=urwid.AttrMap(urwid.Edit(caption="\u270E", edit_text=""), "msg_editor")
                    )
                )

                ConversationsDisplay.cached_conversation_widgets[source_hash] = widget
                return widget


    def conversation_list_widget(self, conversation):
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

        #widget = urwid.SelectableIcon(str(conversation), cursor_position=-1)
        widget = ListEntry(str(conversation))
        urwid.connect_signal(widget, "click", self.display_conversation, conversation)
        return urwid.AttrMap(widget, None, "list_focus")


    def shortcuts(self):
        return self.shortcuts_display