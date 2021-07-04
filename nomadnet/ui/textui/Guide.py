import RNS
import urwid
import nomadnet
from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox, MODIFIER_KEY
from .MarkupParser import markup_to_attrmaps

class GuideDisplayShortcuts():
    def __init__(self, app):
        self.app = app
        g = app.ui.glyphs

        self.widget = urwid.AttrMap(urwid.Text(""), "shortcutbar")

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

class GuideEntry(urwid.WidgetWrap):
    def __init__(self, app, reader, topic_name):
        self.app = app
        self.reader = reader
        g = self.app.ui.glyphs

        widget = ListEntry(topic_name)
        urwid.connect_signal(widget, "click", self.display_topic, topic_name)

        style = "list_normal"
        focus_style = "list_focus"
        self.display_widget = urwid.AttrMap(widget, style, focus_style)
        urwid.WidgetWrap.__init__(self, self.display_widget)

    def display_topic(self, event, topic):
        markup = TOPICS[topic]
        attrmaps = markup_to_attrmaps(markup)

        self.reader.set_content_widgets(attrmaps)

class TopicList(urwid.WidgetWrap):
    def __init__(self, app, guide_display):
        self.app = app
        g = self.app.ui.glyphs

        self.topic_list = [
            GuideEntry(self.app, guide_display, "Introduction"),
            GuideEntry(self.app, guide_display, "Conversations"),
            GuideEntry(self.app, guide_display, "Markup"),
            GuideEntry(self.app, guide_display, "Licenses & Credits"),
        ]

        self.ilb = IndicativeListBox(
            self.topic_list,
            initialization_is_selection_change=False,
        )

        urwid.WidgetWrap.__init__(self, urwid.LineBox(self.ilb, title="Topics"))


    def keypress(self, size, key):
        if key == "up" and (self.ilb.first_item_is_selected()):
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.set_focus("header")
            
        return super(TopicList, self).keypress(size, key)

class GuideDisplay():
    list_width = 0.33

    def __init__(self, app):
        self.app = app
        g = self.app.ui.glyphs

        topic_text = urwid.Text("\nNo topic selected", align="left")

        self.left_area  = TopicList(self.app, self)
        self.right_area = urwid.LineBox(urwid.Filler(topic_text, "top"))


        self.columns = urwid.Columns(
            [
                ("weight", GuideDisplay.list_width, self.left_area),
                ("weight", 1-GuideDisplay.list_width, self.right_area)
            ],
            dividechars=0, focus_column=0
        )

        self.shortcuts_display = GuideDisplayShortcuts(self.app)
        self.widget = self.columns

    def set_content_widgets(self, new_content):
        options = self.columns.options(width_type="weight", width_amount=1-GuideDisplay.list_width)
        pile = urwid.Pile(new_content)
        content = urwid.LineBox(urwid.Filler(pile, "top"))

        self.columns.contents[1] = (content, options)

    def shortcuts(self):
        return self.shortcuts_display


TOPIC_INTRODUCTION = '''>Nomad Network

Communicate Freely.

Nomad Network is built using Reticulum
-~
## Notable Features
 - Encrypted messaging over packet-radio, LoRa, WiFi or anything else [Reticulum](https://github.com/markqvist/Reticulum) supports.
 - Zero-configuration, minimal-infrastructure mesh communication
-
## Current Status

Pre-alpha. At this point Nomad Network is usable as a basic messaging client over Reticulum networks, but only the very core features have been implemented. Development is ongoing and current features being implemented are:

 - Propagated messaging and discussion threads
 - Connectable nodes that can host pages, files and other resources
 - Collaborative information sharing and spatial map-style "wikis"
-
## Dependencies:
 - Python 3
 - RNS
 - LXMF

```

To use Nomad Network on packet radio or LoRa, you will need to configure your Reticulum installation 
to use any relevant packet radio TNCs or LoRa devices on your system. See the Reticulum documentation
 for info.

## Caveat Emptor
Nomad Network is experimental software, and should be considered as such. While it has been built wit
h cryptography best-practices very foremost in mind, it _has not_ been externally security audited, a
nd there could very well be privacy-breaking bugs. If you want to help out, or help sponsor an audit,
 please do get in touch.
'''

TOPIC_CONVERSATIONS = '''Conversations
=============

Conversations in Nomad Network
'''

TOPIC_MARKUP = '''>Markup
Nomad Network supports a simple and functional markup language called micron. It has a lean markup structure that adds very little overhead, and is still readable as plain text, but offers basic formatting and text structuring, ideal for displaying in a terminal.

Lorem ipsum dolor sit amet.

>>Encoding
`F222`BdddAll uM source files are encoded as UTF-8, and clients supporting uM display should support UTF-8.
``
>>>Sections and `F900Headings`f
You can define an arbitrary number of sections and sub-sections, each with their own heading

-

Dividers inside section will adhere to section indents

>>>>
If no heading text is defined, the section will appear as a sub-section without a header.

<-
Horizontal dividers can be inserted

Text `F2cccan`f be `_underlined`_, `!bold`! or `*italic`*. You `F000`B2cccan`b`f also `_`*`!combine formatting``!

'''

TOPICS = {
    "Introduction": TOPIC_INTRODUCTION,
    "Conversations": TOPIC_CONVERSATIONS,
    "Markup": TOPIC_MARKUP,
}