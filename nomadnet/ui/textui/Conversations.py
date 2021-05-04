class ConversationsDisplayShortcuts():
    def __init__(self, app):
        import urwid
        self.app = app

        self.widget = urwid.AttrMap(urwid.Text("Conversations Display Shortcuts"), "shortcutbar")

class ConversationsDisplay():
    def __init__(self, app):
        import urwid
        from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox

        self.app = app

        conversation_list_widgets = []
        for conversation in app.conversations():
            widget = urwid.SelectableIcon(str(conversation), cursor_position=-1)
            widget.conversation = conversation
            conversation_list_widgets.append(urwid.AttrMap(widget, None, "list_focus"))

        walker = urwid.SimpleFocusListWalker(conversation_list_widgets)
        listbox = urwid.LineBox(urwid.Filler(IndicativeListBox(conversation_list_widgets), height=("relative", 100)))

        placeholder = urwid.Text("Conversation Display Area", "left")

        conversation_area = urwid.LineBox(
            urwid.Frame(
                urwid.Filler(placeholder,"top"),
                footer=urwid.AttrMap(urwid.Edit(caption="\u270E", edit_text="Message input"), "msg_editor")
            )
        )

        columns_widget = urwid.Columns([("weight", 0.33, listbox), ("weight", 0.67, conversation_area)], dividechars=0, focus_column=0, box_columns=[0])

        self.shortcuts_display = ConversationsDisplayShortcuts(self.app)
        self.widget = columns_widget

    def shortcuts(self):
        return self.shortcuts_display