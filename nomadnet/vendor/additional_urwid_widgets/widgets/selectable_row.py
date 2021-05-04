#! /usr/bin/env python3
# -*- coding: utf-8 -*-


import urwid


class SelectableRow(urwid.WidgetWrap):
    """Wraps 'urwid.Columns' to make it selectable.
    This class has been slightly modified, but essentially corresponds to this class posted on stackoverflow.com:
    https://stackoverflow.com/questions/52106244/how-do-you-combine-multiple-tui-forms-to-write-more-complex-applications#answer-52174629"""

    def __init__(self, contents, *, align="left", on_select=None, space_between=2):
        # A list-like object, where each element represents the value of a column.
        self.contents = contents
        
        self._columns = urwid.Columns([urwid.Text(c, align=align) for c in contents],
                                       dividechars=space_between)
        
        # Wrap 'urwid.Columns'.
        super().__init__(self._columns)
        
        # A hook which defines the behavior that is executed when a specified key is pressed.
        self.on_select = on_select
    
    def __repr__(self):
        return "{}(contents='{}')".format(self.__class__.__name__,
                                          self.contents)
    
    def selectable(self):
        return True
    
    def keypress(self, size, key):
        if (key == "enter") and (self.on_select is not None):
            self.on_select(self)
            key = None
            
        return key
    
    def set_contents(self, contents):
        # Update the list record inplace...
        self.contents[:] = contents
        
        # ... and update the displayed items.
        for t, (w, _) in zip(contents, self._columns.contents):
            w.set_text(t)
            
