#! /usr/bin/env python3
# -*- coding: utf-8 -*-


import urwid


class MessageDialog(urwid.WidgetWrap):
    """Wraps 'urwid.Overlay' to show a message and expects a reaction from the user."""
    
    def __init__(self, contents, btns, overlay_size, *, contents_align="left", space_between_btns=2, title="", title_align="center",
                 background=urwid.SolidFill("#"), overlay_align=("center", "middle"), overlay_min_size=(None, None), left=0, right=0,
                 top=0, bottom=0):
        # Message part
        texts = [urwid.Text(content, align=contents_align)
                 for content in contents]
        
        # Lower part
        lower_part = [urwid.Divider(" "),
                      urwid.Columns(btns, dividechars=space_between_btns)]
        
        # frame 
        line_box = urwid.LineBox(urwid.Pile(texts + lower_part),
                                 title=title,
                                 title_align=title_align)
        
        # Wrap 'urwid.Overlay'
        super().__init__(urwid.Overlay(urwid.Filler(line_box),
                                       background,
                                       overlay_align[0],
                                       overlay_size[0],
                                       overlay_align[1],
                                       overlay_size[1],
                                       min_width=overlay_min_size[0],
                                       min_height=overlay_min_size[1],
                                       left=left,
                                       right=right,
                                       top=top,
                                       bottom=bottom))
        