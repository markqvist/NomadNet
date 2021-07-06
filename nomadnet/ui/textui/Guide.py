import RNS
import urwid
import nomadnet
from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox, MODIFIER_KEY
from .MicronParser import markup_to_attrmaps
from .Scrollable import *

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
            GuideEntry(self.app, guide_display, "First Run"),
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
        #content = urwid.LineBox(urwid.Filler(pile, "top"))
        content = urwid.LineBox(urwid.AttrMap(ScrollBar(Scrollable(pile), thumb_char="\u2503", trough_char=" "), "scrollbar"))

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

TOPIC_MARKUP = '''>Outputting Formatted Text


>>>>>>>>>>>>>>>
-\u223f
<

`c`!Hello!`! This is output from `*micron`*
Micron generates formatted text for your terminal
`a

>>>>>>>>>>>>>>>
-\u223f
<


Nomad Network supports a simple and functional markup language called `*micron`*. If you are familiar with `*markdown`* or `*HTML`*, you will feel right at home writing pages with micron.

With micron you can easily create structured documents and pages with formatting, colors, glyphs and icons, ideal for display in terminals.

>>Recommendations and Requirements

While micron can output formatted text to even the most basic terminal, there's a few capabilities your terminal `*must`* support to display micron output correctly, and some that, while not strictly necessary, make the experience a lot better.

>>>Encoding

All micron sources are intepreted as UTF-8, and micron assumes it can output UTF-8 characters to the terminal. If your terminal does not support UTF-8, output will be faulty.

>>>Colors

Shading and coloring text and backgrounds is integral to micron output, and while micron will attempt to gracefully degrade output even to 1-bit terminals, you will get the best output with terminals supporting at least 256 colors. True-color support is recommended.

>>>Terminal Font

While any font any unicode capable font can be used with micron, it's highly recommended to use a `*"Nerd Font"`* (see https://www.nerdfonts.com/), which will add a lot of extra glyphs and icons to your output.

> A Few Demo Outputs

`F222`Bddd

`cWith micron, you can control layout and presentation
`a

``

`B33f

You can change background ...

``

`B393

`r`F320... and foreground colors`f
`a

`b

If you want to make a break, horizontal dividers can be inserted. They can be plain, like the one below this text, or you can style them with unicode characters and glyphs, like the wavy divider in the beginning of this document.

-

`cText can be `_underlined`_, `!bold`! or `*italic`*.

You can also `_`*`!`B5d5`F222combine`f`b`_ `_`Ff00f`Ff80o`Ffd0r`F9f0m`F0f2a`F0fdt`F07ft`F43fi`F70fn`Fe0fg`` for some fabulous effects.
`a


>>>Sections and Headings

You can define an arbitrary number of sections and sub sections, each with their own named headings. Text inside sections will be automatically indented.

-

If you place a divider inside a section, it will adhere to the section indents.

>>>>>
If no heading text is defined, the section will appear as a sub-section without a header. This can be useful for creating indented blocks of text, like this one.

>Micron tags

Tags are used to format text with micron. Some tags can appear anywhere in text, and some must appear at the beginning of a line. If you need to write text that contains a sequence that would be interpreted as a tag, you can escape it with the character \\.

In the following sections, the different tags will be introduced. Any styling set within micron can be reset to the default style by using the special \\`\\` tag anywhere in the markup, which will immediately remove any formatting previously specified. 

>>Alignment

To control text alignment use the tag \\`c to center text, \\`l to left-align, \\`r to right-align, and \\`a to return to the default alignment of the document. Alignment tags must appear at the beginning of a line. Here is an example:

`Faaa
`=
`cThis line will be centered.
So will this.
`aThe alignment has now been returned to default.
`rThis will be aligned to the right
``
`=
``

The above markup produces the following output:

`Faaa`B333

`cThis line will be centered.
So will this.

`aThe alignment has now been returned to default.

`rThis will be aligned to the right

``


>>Formatting

Text can be formatted as `!bold`! by using the \\`! tag, `_underline`_ by using the \\`_ tag and `*italic`* by using the \\`* tag.

Here's an example of formatting text:

`Faaa
`=
We shall soon see `!bold`! paragraphs of text decorated with `_underlines`_ and `*italics`*. Some even dare `!`*`_combine`` them!
`=
``

The above markup produces the following output:

`Faaa`B333

We shall soon see `!bold`! paragraphs of text decorated with `_underlines`_ and `*italics`*. Some even dare `!`*`_combine`!`*`_ them!

``


>>Sections

To create sections and subsections, use the > tag. This tag must be placed at the beginning of a line. To specify a sub-section of any level, use any number of > tags. If text is placed after a > tag, it will be used as a heading.

Here is an example of sections:

`Faaa
`=
>High Level Stuff
This is a section. It contains this text.

>>Another Level
This is a sub section.

>>>Going deeper
A sub sub section. We could continue, but you get the point.

>>>>
Wait! It's worth noting that we can also create sections without headings. They look like this.
`=
``

The above markup produces the following output:

`Faaa`B333
>High Level Stuff
This is a section. It contains this text.

>>Another Level
This is a sub section.

>>>Going deeper
A sub sub section. We could continue, but you get the point.

>>>>
Wait! It's worth noting that we can also create sections without headings. They look like this.
``


>Colors

Foreground colors can be specified with the \\`F tag, followed by three hexadecimal characters. To return to the default foreground color, use the \\`f tag. Background color is specified in the same way, but by using the \\`B and \\`b tags.

Here's a few examples:

`Faaa
`=
You can use `B5d5`F222 color `f`b `Ff00f`Ff80o`Ffd0r`F9f0m`F0f2a`F0fdt`F07ft`F43fi`F70fn`Fe0fg`f for some fabulous effects.
`=
``

The above markup produces the following output:

`Faaa`B333

You can use `B5d5`F222 color `f`B333 `Ff00f`Ff80o`Ffd0r`F9f0m`F0f2a`F0fdt`F07ft`F43fi`F70fn`Fe0fg`f for some fabulous effects.

``


>Literals

To display literal content, for example source-code, or blocks of text that should not be interpreted by micron, you can use literal blocks, specified by the \\`= tag. Below is the source code of this entire document, presented as a literal block.

-

`=
'''
TOPIC_MARKUP += TOPIC_MARKUP.replace("`=", "\\`=") + "[ micron source for document goes here, we don't want infinite recursion now, do we? ]\n\\`="
TOPIC_MARKUP += "\n`=\n\n>Closing Remarks\n\nIf you made it all the way here, you should be well equipped to write documents and pages using micron. Thank you for staying with me.\n\n`c\U0001F332\n"

TOPIC_FIRST_RUN = '''>First Time Information

Hi there. This first run message will only appear once. It contains a few pointers on getting started with Nomad Network, and getting the most out of the program. You're currently located in the guide section of the program. I'm sorry I had to drag you here by force, but it will only happen this one time, I promise. If you ever get lost, return here and peruse the list of topics you see on the left. I will do my best to fill it with answers to mostly anything about Nomad Network.

To get the most out of Nomad Network, you will need a terminal that supports UTF-8 and at least 256 colors, ideally true-color. By default, Nomad Network starts in low-color mode. It does this for the sake of compatibility, but it does look rather ugly. If your terminal supports true-color or just 256 colors, you should go to the `![ Config ]`! menu item, launch the editor and change the configuration to use a high-color mode.

If you don't already have a Nerd Font installed (see https://www.nerdfonts.com/), I also highly recommend to do so, since it will greatly expand the amount of glyphs, icons and graphics that Nomad Network can use.

Nomad Network expects that you are already connected to some form of Reticulum network. That could be as simple as the default UDP-based demo interface on your local ethernet network, or as advanced as some elaborate hybrid RF and free-space optical laser network. This short guide won't go into any details on that, but you will find other entries in the guide that deal with network setup and configuration.

At least, if Nomad Network launches, it means that it is connected to a running Reticulum instance, that should in turn be connected to `*something`*, which should get you started.

Now go out there and explore. This is still early days. See what you can find and create.

>>>>>>>>>>>>>>>
-\u223f
<

'''

TOPIC_LICENSES = '''>Thanks, Acknowledgements and Licenses

Lorem Ipsum
'''

TOPICS = {
    "Introduction": TOPIC_INTRODUCTION,
    "Conversations": TOPIC_CONVERSATIONS,
    "Markup": TOPIC_MARKUP,
    "First Run": TOPIC_FIRST_RUN,
    "Licenses & Credits": TOPIC_LICENSES,
}