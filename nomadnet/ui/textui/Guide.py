import RNS
import urwid
import nomadnet
from nomadnet.vendor.additional_urwid_widgets import IndicativeListBox, MODIFIER_KEY
from .MicronParser import markup_to_attrmaps
from nomadnet.vendor.Scrollable import *

class GuideDisplayShortcuts():
    def __init__(self, app):
        self.app = app
        g = app.ui.glyphs

        self.widget = urwid.AttrMap(urwid.Padding(urwid.Text(""), align="left"), "shortcutbar")

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
    def __init__(self, app, parent, reader, topic_name):
        self.app = app
        self.parent = parent
        self.reader = reader
        self.last_keypress = None
        self.topic_name = topic_name
        g = self.app.ui.glyphs

        widget = ListEntry(topic_name)
        urwid.connect_signal(widget, "click", self.display_topic, self.topic_name)

        style = "topic_list_normal"
        focus_style = "list_focus"
        self.display_widget = urwid.AttrMap(widget, style, focus_style)
        urwid.WidgetWrap.__init__(self, self.display_widget)

    def display_topic(self, event, topic):
        markup = TOPICS[topic]
        attrmaps = markup_to_attrmaps(markup, url_delegate=None)

        topic_position = None
        index = 0
        for topic in self.parent.topic_list:
            widget = topic._original_widget
            if widget.topic_name == self.topic_name:
                topic_position = index
            index += 1

        if topic_position != None:
            self.parent.ilb.select_item(topic_position)

        self.reader.set_content_widgets(attrmaps)
        self.reader.focus_reader()


    def micron_released_focus(self):
        self.reader.focus_topics()

class TopicList(urwid.WidgetWrap):
    def __init__(self, app, guide_display):
        self.app = app
        g = self.app.ui.glyphs

        self.first_run_entry = GuideEntry(self.app, self, guide_display, "First Run")

        self.topic_list = [
            GuideEntry(self.app, self, guide_display, "Introduction"),
            GuideEntry(self.app, self, guide_display, "Hosting a Node"),
            GuideEntry(self.app, self, guide_display, "Markup"),
            self.first_run_entry,
            GuideEntry(self.app, self, guide_display, "Display Test"),
            GuideEntry(self.app, self, guide_display, "Credits & Licenses"),
        ]

        self.ilb = IndicativeListBox(
            self.topic_list,
            initialization_is_selection_change=False,
            highlight_offFocus="list_off_focus"
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

        topic_text = urwid.Text("\n  No topic selected", align="left")

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

        if self.app.firstrun:
            entry = self.left_area.first_run_entry
            entry.display_topic(entry.display_topic, entry.topic_name)

    def set_content_widgets(self, new_content):
        options = self.columns.options(width_type="weight", width_amount=1-GuideDisplay.list_width)
        pile = urwid.Pile(new_content)
        #content = urwid.LineBox(urwid.Filler(pile, "top"))
        content = urwid.LineBox(urwid.AttrMap(ScrollBar(Scrollable(pile), thumb_char="\u2503", trough_char=" "), "scrollbar"))

        self.columns.contents[1] = (content, options)

    def shortcuts(self):
        return self.shortcuts_display

    def focus_topics(self):
        self.columns.focus_position = 0

    def focus_reader(self):
        self.columns.focus_position = 1


TOPIC_INTRODUCTION = '''>Nomad Network

`c`*Communicate Freely.`*
`a

The intention with this program is to provide a tool to that allows you to build private and resilient communications platforms that are in complete control and ownership of the people that use them.

Nomad Network is build on LXMF and Reticulum, which together provides the cryptographic mesh functionality and peer-to-peer message routing that Nomad Network relies on. This foundation also makes it possible to use the program over a very wide variety of communication mediums, from packet radio to gigabit fiber.

Nomad Network does not need any connections to the public internet to work. In fact, it doesn't even need an IP or Ethernet network. You can use it entirely over packet radio, LoRa or even serial lines. But if you wish, you can bridge islanded Reticulum networks over the Internet or private ethernet networks, or you can build networks running completely over the Internet. The choice is yours.

The current version of the program should be considered an alpha release. The program works well, but there will most probably be bugs and possibly sub-optimal performance in some scenarios. On the other hand, this is the best time to have an influence on the direction of the development of Nomad Network. To do so, join the discussion on the Nomad Network project on GitHub.

>Concepts and Terminology

The following section will briefly introduce various concepts and terms used in the program.

>>Peer

A `*peer`* refers to another Nomad Network client, which will generally be operated by another person. But since Nomad Network is a general LXMF client, it could also be any other LXMF client, program, automated system or machine that can communicate over LXMF.

>>Announces

An `*announce`* can be sent by any peer on the network, which will notify other peers of its existence, and contains the cryptographic keys that allows other peers to communicate with it.

In the `![ Network ]`! section of the program, you can monitor announces on the network, initiate conversations with announced peers, and announce your own peer on the network. You can also connect to nodes on the network and browse information shared by them.

>>Conversations

Nomad Network uses the term `*conversation`* to signify both direct peer-to-peer messaging threads, and also discussion threads with an arbitrary number of participants that might change over time.

Both things like discussion forums and chat threads can be encapsulated as conversations in Nomad Network. The user interface will indicate the different characteristics a conversation can take, and also what form of transport encryption messages within used.

In the `![ Conversations ]`! part of the program you can view and interact with all currently active conversations. You can also edit nickname and trust settings for peers here.

>>Node

A Nomad Network `*node`* is an instance of the Nomad Network program that has been configured to host information for other peers and help propagate messages and information on the network.

Nodes can host pages (similar to webpages) written in a markup-language called `*micron`*, as well as make files and other resources available for download for peers on the network. Nodes are also integral in allowing forum/discussion threads to exist and propagate on the network.

If no nodes exist on a network, all peers will still be able to communicate directly peer-to-peer, but both endpoints of a conversation will need to be online at the same time to converse. When nodes exist on the network, messages will be held and syncronised between nodes for deferred delivery if the destination peer is unavailable.

'''

TOPIC_HOSTING = '''>Hosting a Node

To host a node on the network, you must enable it in the configuration file, by setting `*enable_node`* directive to `*yes`*. You should also configure the other node-related parameters such as the node name and announce interval settings. Once node hosting has been enabled in the configuration, Nomad Network will start hosting your node as soon as the program is lauched, and other peers on the network will be able to connect and interact with content on your node.

By default, no content is defined, apart from a short placeholder home page. To learn how to add your own content, read on.

>>Pages

Nomad Network nodes can host pages similar to web pages, that other peers can read and interact with. Pages are written in a compact markup language called `*micron`*. To learn how to write formatted pages with micron, see the `*Markup`* section of this guide (which is, itself, written in micron). Pages can be linked arbitrarily with hyperlinks, that can also link to pages (or other resources) on other nodes.

To add pages to your node, place micron files in the `*pages`* directory of your Nomad Network programs `*storage`* directory. By default, the path to this will be `!~/.nomadnetwork/storage/pages`!. You should probably create the file `!index.mu`! first, as this is the page that will get served by default to a connecting peer.

You can control how long a peer will cache your pages by including the cache header in a page. To do so, the first line of your page must start with `!#!c=X`!, where `!X`! is the cache time in seconds. To tell the peer to always load the page from your node, and never cache it, set the cache time to zero. You should only do this if there is a real need, for example if your page displays dynamic content that `*must`* be updated at every page view. The default caching time is 12 hours. In most cases, you should not need to include the cache control header in your pages.

You can use a preprocessor such as PHP, bash, Python (or whatever you prefer) to generate dynamic pages. To do so, just set executable permissions on the relevant page file, and be sure to include the interpreter at the beginning of the file, for example `!#!/usr/bin/python3`!.

>>Files

Like pages, you can place files you want to make available in the `!~/.nomadnetwork/storage/files`! directory. To let a peer download a file, you should create a link to it in one of your pages.

>>Links and URLs

Links to pages and resources in Nomad Network use a simple URL format. Here is an example:

`!1385edace36466a6b3dd:/page/index.mu`!

The first part is the 10 byte destination address of the node (represented as readable hexadecimal), followed by the `!:`! character. Everything after the `!:`! represents the request path.

By convention, Nomad Network nodes maps all hosted pages under the `!/page`! path, and all hosted files under the `!/file`! path. You can create as many subdirectories for pages and files as you please, and they will be automatically mapped to corresponding request paths.

You can omit the destination address of the node, if you are reffering to a local page or file. You must still keep the `!:`! character. In such a case, the URL to a page could look like this:

`!:/page/other_page.mu`!

The URL to a local file could look like this:

`!:/file/document.pdf`!

Links can be inserted into micron documents. See the `*Markup`* section of this guide for info on how to do so.

'''

TOPIC_CONVERSATIONS = '''>Conversations

Conversations in Nomad Network
'''


TOPIC_FIRST_RUN = '''>First Time Information

Hi there. This first run message will only appear once. It contains a few pointers on getting started with Nomad Network, and getting the most out of the program.

You're currently located in the guide section of the program. I'm sorry I had to drag you here by force, but it will only happen this one time, I promise. If you ever get lost, return here and peruse the list of topics you see on the left. I will do my best to fill it with answers to mostly anything about Nomad Network.

To get the most out of Nomad Network, you will need a terminal that supports UTF-8 and at least 256 colors, ideally true-color. If your terminal supports true-color, you can go to the `![ Config ]`! menu item, launch the editor and change the configuration.

If you don't already have a Nerd Font installed (see https://www.nerdfonts.com/), I also highly recommend to do so, since it will greatly expand the amount of glyphs, icons and graphics that Nomad Network can use. Once you have your terminal set up with a Nerd Font, go to the `![ Config ]`! menu item and enable Nerd Fonts in the configuration instead of normal unicode glyphs.

Nomad Network expects that you are already connected to some form of Reticulum network. That could be as simple as the default UDP-based demo interface on your local ethernet network. This short guide won't go into any details on building, but you will find other entries in the guide that deal with network setup and configuration.

At least, if Nomad Network launches, it means that it is connected to a running Reticulum instance, that should in turn be connected to `*something`*, which should get you started.

For more some more information, you can also read the `*Introduction`* section of this guide.

Now go out there and explore. This is still early days. See what you can find and create.

>>>>>>>>>>>>>>>
-\u223f
<

'''

TOPIC_DISPLAYTEST = '''>Markup & Color Display Test


`cYou can use this section to gauge how well your terminal reproduces the various types of formatting used by Nomad Network.
``


>>>>>>>>>>>>>>>>>>>>
-\u223f
<


>>
`a`!This line should be bold, and aligned to the left`!

`c`*This one should be italic and centered`*

`r`_And this one should be underlined, aligned right`_
``

The following line should contain a red gradient bar:
`B100 `B200 `B300 `B400 `B500 `B600 `B700 `B800 `B900 `Ba00 `Bb00 `Bc00 `Bd00 `Be00 `Bf00`b

The following line should contain a green gradient bar:
`B010 `B020 `B030 `B040 `B050 `B060 `B070 `B080 `B090 `B0a0 `B0b0 `B0c0 `B0d0 `B0e0 `B0f0`b

The following line should contain a blue gradient bar:
`B001 `B002 `B003 `B004 `B005 `B006 `B007 `B008 `B009 `B00a `B00b `B00c `B00d `B00e `B00f`b

Unicode Glyphs   : \u2713  \u2715  \u26a0  \u24c3  \u2193

Nerd Font Glyphs : \uf484  \uf9c4 \uf719  \uf502  \uf415  \uf023  \uf06e
'''


TOPIC_LICENSES = '''>Thanks, Acknowledgements and Licenses

This program uses various other software components, without which Nomad Network would not have been possible. Sincere thanks to the authors and contributors of the following projects

>>>
 - `!Cryptography.io`! by `*pyca`*
   https://cryptography.io/
   BSD License

 - `!Urwid`! by `*Ian Ward`*
   http://urwid.org/
   LGPL-2.1 License

 - `!Additional Urwid Widgets`! by `*AFoeee`*
   https://github.com/AFoeee/additional_urwid_widgets
   MIT License

 - `!Scrollable`! by `*rndusr`*
   https://github.com/rndusr/stig/blob/master/stig/tui/scroll.py
   GPLv3 License

 - `!Configobj`! by `*Michael Foord`*
   https://github.com/DiffSK/configobj
   BSD License

 - `!Reticulum Network Stack`! by `*unsignedmark`*
   https://github.com/markqvist/Reticulum
   MIT License

 - `!LXMF`! by `*unsignedmark`*
   https://github.com/markqvist/LXMF
   MIT License
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

Formatting such as `_underline`_, `!bold`! or `*italics`* will be displayed if your terminal supports it.

If you are having trouble getting micron output to display correctly, try using `*gnome-terminal`*, which should work with all formatting options out of the box. Most other terminals will work fine as well, but you might have to change some settings to get certain formatting to display correctly.

>>>Encoding

All micron sources are intepreted as UTF-8, and micron assumes it can output UTF-8 characters to the terminal. If your terminal does not support UTF-8, output will be faulty.

>>>Colors

Shading and coloring text and backgrounds is integral to micron output, and while micron will attempt to gracefully degrade output even to 1-bit terminals, you will get the best output with terminals supporting at least 256 colors. True-color support is recommended.

>>>Terminal Font

While any unicode capable font can be used with micron, it's highly recommended to use a `*"Nerd Font"`* (see https://www.nerdfonts.com/), which will add a lot of extra glyphs and icons to your output.

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


>Links

Links to pages, files or other resources can be created with the \\`[ tag, which should always be terminated with a closing ]. You can create links with and without labels, it is up to you to control the formatting of links with other tags. Although not strictly necessary, it is good practice to at least format links with underlining.

Here's a few examples:

`Faaa
`=
Here is a link without any label: `[1385edace36466a6b3dd:/page/index.mu]

This is a `[labeled link`1385edace36466a6b3dd:/page/index.mu] to the same page, but it's hard to see if you don't know it

Here is `F00a`_`[a more visible link`1385edace36466a6b3dd:/page/index.mu]`_`f
`=
``

The above markup produces the following output:

`Faaa`B333

Here is a link without any label: `[1385edace36466a6b3dd:/page/index.mu]

This is a `[labeled link`1385edace36466a6b3dd:/page/index.mu] to the same page, but it's hard to see if you don't know it

Here is `F00f`_`[a more visible link`1385edace36466a6b3dd:/page/index.mu]`_`f

``

When links like these are displayed in the built-in browser, clicking on them or activating them using the keyboard will cause the browser to load the specified URL.

>Comments

You can insert comments that will not be displayed in the output by starting a line with the # character.

Here's an example:

`Faaa
`=
# This line will not be displayed
This line will
`=
``

The above markup produces the following output:

`Faaa`B333

# This line will not be displayed
This line will

``


>Literals

To display literal content, for example source-code, or blocks of text that should not be interpreted by micron, you can use literal blocks, specified by the \\`= tag. Below is the source code of this entire document, presented as a literal block.

-

`=
'''
TOPIC_MARKUP += TOPIC_MARKUP.replace("`=", "\\`=") + "[ micron source for document goes here, we don't want infinite recursion now, do we? ]\n\\`="
TOPIC_MARKUP += "\n`=\n\n>Closing Remarks\n\nIf you made it all the way here, you should be well equipped to write documents and pages using micron. Thank you for staying with me.\n\n`c\U0001F332\n"


TOPICS = {
    "Introduction": TOPIC_INTRODUCTION,
    "Conversations": TOPIC_CONVERSATIONS,
    "Hosting a Node": TOPIC_HOSTING,
    "Markup": TOPIC_MARKUP,
    "First Run": TOPIC_FIRST_RUN,
    "Display Test": TOPIC_DISPLAYTEST,
    "Credits & Licenses": TOPIC_LICENSES,
}