#! /usr/bin/env python3
# -*- coding: utf-8 -*-


from ..assisting_modules.modifier_key import MODIFIER_KEY        # pylint: disable=unused-import
from .selectable_row import SelectableRow

import sys      # pylint: disable=unused-import
import urwid


class IntegerPicker(urwid.WidgetWrap):
    """Serves as a selector for integer numbers."""

    def __init__(self, value, *, min_v=(-sys.maxsize - 1), max_v=sys.maxsize, step_len=1, jump_len=100, on_selection_change=None,
                 initialization_is_selection_change=False, modifier_key=MODIFIER_KEY.NONE, ascending=True,
                 return_unused_navigation_input=True, topBar_align="center", topBar_endCovered_prop=("▲", None, None),
                 topBar_endExposed_prop=("───", None, None), bottomBar_align="center", bottomBar_endCovered_prop=("▼", None, None),
                 bottomBar_endExposed_prop=("───", None, None), display_syntax="{}", display_align="center", display_prop=(None, None)):
        assert (min_v <= max_v), "'min_v' must be less than or equal to 'max_v'."
        
        assert (min_v <= value <= max_v), "'min_v <= value <= max_v' must be True."
        
        self._value = value
        
        self._minimum = min_v
        self._maximum = max_v
    
        # Specifies how far to move in the respective direction when the keys 'up/down' are pressed.
        self._step_len = step_len
        
        # Specifies how far to jump in the respective direction when the keys 'page up/down' or the mouse events 'wheel up/down'
        # are passed.
        self._jump_len = jump_len
        
        # A hook which is triggered when the value changes.
        self.on_selection_change = on_selection_change
        
        # 'MODIFIER_KEY' changes the behavior, so that the widget responds only to modified input. ('up' => 'ctrl up')
        self._modifier_key = modifier_key
        
        # Specifies whether moving upwards represents a decrease or an increase of the value.
        self._ascending = ascending
        
        # If the minimum has been reached and an attempt is made to select an even smaller value, the input is normally not
        # swallowed by the widget, but passed on so that other widgets can interpret it. This may result in transferring the focus.
        self._return_unused_navigation_input = return_unused_navigation_input
        
        # The bars are just 'urwid.Text' widgets.
        self._top_bar = urwid.AttrMap(urwid.Text("", topBar_align),
                                      None)
        
        self._bottom_bar = urwid.AttrMap(urwid.Text("", bottomBar_align),
                                         None)
        
        # During the initialization of 'urwid.AttrMap', the value can be passed as non-dict. After initializing, its value can be
        # manipulated by passing a dict. The dicts I create below will be used later to change the appearance of the widgets.
        self._topBar_endCovered_markup = topBar_endCovered_prop[0]
        self._topBar_endCovered_focus = {None:topBar_endCovered_prop[1]}
        self._topBar_endCovered_offFocus = {None:topBar_endCovered_prop[2]}
        
        self._topBar_endExposed_markup = topBar_endExposed_prop[0]
        self._topBar_endExposed_focus = {None:topBar_endExposed_prop[1]}
        self._topBar_endExposed_offFocus = {None:topBar_endExposed_prop[2]}
        
        self._bottomBar_endCovered_markup = bottomBar_endCovered_prop[0]
        self._bottomBar_endCovered_focus = {None:bottomBar_endCovered_prop[1]}
        self._bottomBar_endCovered_offFocus = {None:bottomBar_endCovered_prop[2]}
        
        self._bottomBar_endExposed_markup = bottomBar_endExposed_prop[0]
        self._bottomBar_endExposed_focus = {None:bottomBar_endExposed_prop[1]}
        self._bottomBar_endExposed_offFocus = {None:bottomBar_endExposed_prop[2]}
        
        # Format the number before displaying it. That way it is easier to read.
        self._display_syntax = display_syntax
        
        # The current value is displayed via this widget.
        self._display = SelectableRow([display_syntax.format(value)],
                                     align=display_align)
        
        display_attr = urwid.AttrMap(self._display,
                                     display_prop[1],
                                     display_prop[0])
        
        # wrap 'urwid.Pile'
        super().__init__(urwid.Pile([self._top_bar,
                                     display_attr,
                                     self._bottom_bar]))
        
        # Is 'on_selection_change' triggered during the initialization?
        if initialization_is_selection_change and (on_selection_change is not None):
            on_selection_change(None, value)
            
    def __repr__(self):
        return "{}(value='{}', min_v='{}', max_v='{}', ascending='{}')".format(self.__class__.__name__,
                                                                               self._value,
                                                                               self._minimum,
                                                                               self._maximum,
                                                                               self._ascending)
            
    def render(self, size, focus=False):
        # Changes the appearance of the bar at the top depending on whether the upper limit is reached.
        if self._value == (self._minimum if self._ascending else self._maximum):
            self._top_bar.original_widget.set_text(self._topBar_endExposed_markup)
            self._top_bar.set_attr_map(self._topBar_endExposed_focus
                                       if focus else self._topBar_endExposed_offFocus)
        else:
            self._top_bar.original_widget.set_text(self._topBar_endCovered_markup)
            self._top_bar.set_attr_map(self._topBar_endCovered_focus
                                       if focus else self._topBar_endCovered_offFocus)
        
        # Changes the appearance of the bar at the bottom depending on whether the lower limit is reached.
        if self._value == (self._maximum if self._ascending else self._minimum):
            self._bottom_bar.original_widget.set_text(self._bottomBar_endExposed_markup)
            self._bottom_bar.set_attr_map(self._bottomBar_endExposed_focus
                                          if focus else self._bottomBar_endExposed_offFocus)
        else:
            self._bottom_bar.original_widget.set_text(self._bottomBar_endCovered_markup)
            self._bottom_bar.set_attr_map(self._bottomBar_endCovered_focus
                                          if focus else self._bottomBar_endCovered_offFocus)
            
        return super().render(size, focus=focus)
    
    def keypress(self, size, key):
        # A keystroke is changed to a modified one ('up' => 'ctrl up'). This prevents the widget from responding when the arrows 
        # keys are used to navigate between widgets. That way it can be used in a 'urwid.Pile' or similar.
        if key == self._modifier_key.prepend_to("up"):
            successful = self._change_value(-self._step_len)
        
        elif key == self._modifier_key.prepend_to("down"):
            successful = self._change_value(self._step_len)
        
        elif key == self._modifier_key.prepend_to("page up"):
            successful = self._change_value(-self._jump_len)
        
        elif key == self._modifier_key.prepend_to("page down"):
            successful = self._change_value(self._jump_len)
        
        elif key == self._modifier_key.prepend_to("home"):
            successful = self._change_value(float("-inf"))
        
        elif key == self._modifier_key.prepend_to("end"):
            successful = self._change_value(float("inf"))
        
        else:
            successful = False
        
        return key if not successful else None
    
    def mouse_event(self, size, event, button, col, row, focus):
        if focus:
            # An event is changed to a modified one ('mouse press' => 'ctrl mouse press'). This prevents the original widget from
            # responding when mouse buttons are also used to navigate between widgets.
            if event == self._modifier_key.prepend_to("mouse press"):
                # mousewheel up
                if button == 4.0:
                    result = self._change_value(-self._jump_len)
                    return result if self._return_unused_navigation_input else True
                
                # mousewheel down
                elif button == 5.0:
                    result = self._change_value(self._jump_len)
                    return result if self._return_unused_navigation_input else True
        
        return False
    
    # This method tries to change the value depending on the desired arrangement and returns True if this change was successful.
    def _change_value(self, summand):
        value_before_input = self._value
        
        if self._ascending:
            new_value = self._value + summand
            
            if summand < 0:
                # If the corresponding limit has already been reached, then determine whether the unused input should be
                # returned or swallowed.
                if self._value == self._minimum:
                    return not self._return_unused_navigation_input
                
                # If the new value stays within the permitted range, use it.
                elif new_value > self._minimum:
                    self._value = new_value
                
                # The permitted range would be exceeded, so the limit is set instead.
                else:
                    self._value = self._minimum
            
            elif summand > 0:
                if self._value == self._maximum:
                    return not self._return_unused_navigation_input
                
                elif new_value < self._maximum:
                    self._value = new_value
                
                else:
                    self._value = self._maximum
        else:
            new_value = self._value - summand
            
            if summand < 0:
                if self._value == self._maximum:
                    return not self._return_unused_navigation_input
                
                elif new_value < self._maximum:
                    self._value = new_value
                
                else:
                    self._value = self._maximum
            
            elif summand > 0:
                if self._value == self._minimum:
                    return not self._return_unused_navigation_input
                
                elif new_value > self._minimum:
                    self._value = new_value
                
                else:
                    self._value = self._minimum
        
        # Update the displayed value.
        self._display.set_contents([self._display_syntax.format(self._value)])
        
        # If the value has changed, execute the hook (if existing).
        if (value_before_input != self._value) and (self.on_selection_change is not None):
            self.on_selection_change(value_before_input,
                                     self._value)
        
        return True
    
    def get_value(self):
        return self._value
    
    def set_value(self, value):
        if not (self._minimum <= value <= self._maximum):
            raise ValueError("'minimum <= value <= maximum' must be True.")
            
        if value != self._value:
            value_before_change = self._value
            self._value = value
            
            # Update the displayed value.
            self._display.set_contents([self._display_syntax.format(self._value)])
            
            # Execute the hook (if existing).
            if (self.on_selection_change is not None):
                self.on_selection_change(value_before_change, self._value)
        
    def set_to_minimum(self):
        self.set_value(self._minimum)
    
    def set_to_maximum(self):
        self.set_value(self._maximum)
        
    def set_minimum(self, new_min):
        if new_min > self._maximum:
            raise ValueError("'new_min' must be less than or equal to the maximum value.")
        
        self._minimum = new_min
        
        if self._value < new_min:
            self.set_to_minimum()
    
    def set_maximum(self, new_max):
        if new_max < self._minimum:
            raise ValueError("'new_max' must be greater than or equal to the minimum value.")
        
        self._maximum = new_max
        
        if self._value > new_max:
            self.set_to_maximum()
        
    def minimum_is_selected(self):
        return self._value == self._minimum
    
    def maximum_is_selected(self):
        return self._value == self._maximum
        