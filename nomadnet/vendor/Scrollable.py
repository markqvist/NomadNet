# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details
# http://www.gnu.org/licenses/gpl-3.0.txt

import urwid
from urwid.widget import BOX, FIXED, FLOW

# Scroll actions
SCROLL_LINE_UP        = 'line up'
SCROLL_LINE_DOWN      = 'line down'
SCROLL_PAGE_UP        = 'page up'
SCROLL_PAGE_DOWN      = 'page down'
SCROLL_TO_TOP         = 'to top'
SCROLL_TO_END         = 'to end'

# Scrollbar positions
SCROLLBAR_LEFT  = 'left'
SCROLLBAR_RIGHT = 'right'

class Scrollable(urwid.WidgetDecoration):
    def sizing(self):
        return frozenset([BOX,])

    def selectable(self):
        return True

    def __init__(self, widget, force_forward_keypress = False):
        """Box widget that makes a fixed or flow widget vertically scrollable

        TODO: Focusable widgets are handled, including switching focus, but
        possibly not intuitively, depending on the arrangement of widgets.  When
        switching focus to a widget that is ouside of the visible part of the
        original widget, the canvas scrolls up/down to the focused widget.  It
        would be better to scroll until the next focusable widget is in sight
        first.  But for that to work we must somehow obtain a list of focusable
        rows in the original canvas.
        """
        if not any(s in widget.sizing() for s in (FIXED, FLOW)):
            raise ValueError('Not a fixed or flow widget: %r' % widget)
        self._trim_top = 0
        self._scroll_action = None
        self._forward_keypress = None
        self._old_cursor_coords = None
        self._rows_max_cached = 0
        self.force_forward_keypress = force_forward_keypress
        self.__super.__init__(widget)

    def render(self, size, focus=False):
        maxcol, maxrow = size

        # Render complete original widget
        ow = self._original_widget
        ow_size = self._get_original_widget_size(size)
        canv_full = ow.render(ow_size, focus)

        # Make full canvas editable
        canv = urwid.CompositeCanvas(canv_full)
        canv_cols, canv_rows = canv.cols(), canv.rows()

        if canv_cols <= maxcol:
            pad_width = maxcol - canv_cols
            if pad_width > 0:
                # Canvas is narrower than available horizontal space
                canv.pad_trim_left_right(0, pad_width)

        if canv_rows <= maxrow:
            fill_height = maxrow - canv_rows
            if fill_height > 0:
                # Canvas is lower than available vertical space
                canv.pad_trim_top_bottom(0, fill_height)

        if canv_cols <= maxcol and canv_rows <= maxrow:
            # Canvas is small enough to fit without trimming
            return canv

        self._adjust_trim_top(canv, size)

        # Trim canvas if necessary
        trim_top = self._trim_top
        trim_end = canv_rows - maxrow - trim_top
        trim_right = canv_cols - maxcol
        if trim_top > 0:
            canv.trim(trim_top)
        if trim_end > 0:
            canv.trim_end(trim_end)
        if trim_right > 0:
            canv.pad_trim_left_right(0, -trim_right)

        # Disable cursor display if cursor is outside of visible canvas parts
        if canv.cursor is not None:
            curscol, cursrow = canv.cursor
            if cursrow >= maxrow or cursrow < 0:
                canv.cursor = None

        # Figure out whether we should forward keypresses to original widget
        if canv.cursor is not None:
            # Trimmed canvas contains the cursor, e.g. in an Edit widget
            self._forward_keypress = True
        else:
            if canv_full.cursor is not None:
                # Full canvas contains the cursor, but scrolled out of view
                self._forward_keypress = False
            else:
                # Original widget does not have a cursor, but may be selectable

                # FIXME: Using ow.selectable() is bad because the original
                # widget may be selectable because it's a container widget with
                # a key-grabbing widget that is scrolled out of view.
                # ow.selectable() returns True anyway because it doesn't know
                # how we trimmed our canvas.
                #
                # To fix this, we need to resolve ow.focus and somehow
                # ask canv whether it contains bits of the focused widget.  I
                # can't see a way to do that.
                if ow.selectable():
                    self._forward_keypress = True
                else:
                    self._forward_keypress = False

        return canv

    def keypress(self, size, key):
        # Maybe offer key to original widget
        if self._forward_keypress or self.force_forward_keypress:
            ow = self._original_widget
            ow_size = self._get_original_widget_size(size)

            # Remember previous cursor position if possible
            if hasattr(ow, 'get_cursor_coords'):
                self._old_cursor_coords = ow.get_cursor_coords(ow_size)

            key = ow.keypress(ow_size, key)
            if key is None:
                return None

        # Handle up/down, page up/down, etc
        command_map = self._command_map
        if command_map[key] == urwid.CURSOR_UP:
            self._scroll_action = SCROLL_LINE_UP
        elif command_map[key] == urwid.CURSOR_DOWN:
            self._scroll_action = SCROLL_LINE_DOWN

        elif command_map[key] == urwid.CURSOR_PAGE_UP:
            self._scroll_action = SCROLL_PAGE_UP
        elif command_map[key] == urwid.CURSOR_PAGE_DOWN:
            self._scroll_action = SCROLL_PAGE_DOWN

        elif command_map[key] == urwid.CURSOR_MAX_LEFT:   # 'home'
            self._scroll_action = SCROLL_TO_TOP
        elif command_map[key] == urwid.CURSOR_MAX_RIGHT:  # 'end'
            self._scroll_action = SCROLL_TO_END

        else:
            return key

        self._invalidate()

    def mouse_event(self, size, event, button, col, row, focus):
        ow = self._original_widget
        if hasattr(ow, 'mouse_event'):
            ow_size = self._get_original_widget_size(size)
            row += self._trim_top
            return ow.mouse_event(ow_size, event, button, col, row, focus)
        else:
            return False

    def _adjust_trim_top(self, canv, size):
        """Adjust self._trim_top according to self._scroll_action"""
        action = self._scroll_action
        self._scroll_action = None

        maxcol, maxrow = size
        trim_top = self._trim_top
        canv_rows = canv.rows()

        if trim_top < 0:
            # Negative trim_top values use bottom of canvas as reference
            trim_top = canv_rows - maxrow + trim_top + 1

        if canv_rows <= maxrow:
            self._trim_top = 0  # Reset scroll position
            return

        def ensure_bounds(new_trim_top):
            return max(0, min(canv_rows - maxrow, new_trim_top))

        if action == SCROLL_LINE_UP:
            self._trim_top = ensure_bounds(trim_top - 1)
        elif action == SCROLL_LINE_DOWN:
            self._trim_top = ensure_bounds(trim_top + 1)

        elif action == SCROLL_PAGE_UP:
            self._trim_top = ensure_bounds(trim_top - maxrow + 1)
        elif action == SCROLL_PAGE_DOWN:
            self._trim_top = ensure_bounds(trim_top + maxrow - 1)

        elif action == SCROLL_TO_TOP:
            self._trim_top = 0
        elif action == SCROLL_TO_END:
            self._trim_top = canv_rows - maxrow

        else:
            self._trim_top = ensure_bounds(trim_top)

        # If the cursor was moved by the most recent keypress, adjust trim_top
        # so that the new cursor position is within the displayed canvas part.
        # But don't do this if the cursor is at the top/bottom edge so we can still scroll out
        if self._old_cursor_coords is not None and self._old_cursor_coords != canv.cursor and canv.cursor != None:
            self._old_cursor_coords = None
            curscol, cursrow = canv.cursor
            if cursrow < self._trim_top:
                self._trim_top = cursrow
            elif cursrow >= self._trim_top + maxrow:
                self._trim_top = max(0, cursrow - maxrow + 1)

    def _get_original_widget_size(self, size):
        ow = self._original_widget
        sizing = ow.sizing()
        if FIXED in sizing:
            return ()
        elif FLOW in sizing:
            return (size[0],)

    def get_scrollpos(self, size=None, focus=False):
        """Current scrolling position

        Lower limit is 0, upper limit is the maximum number of rows with the
        given maxcol minus maxrow.

        NOTE: The returned value may be too low or too high if the position has
        changed but the widget wasn't rendered yet.
        """
        return self._trim_top

    def set_scrollpos(self, position):
        """Set scrolling position

        If `position` is positive it is interpreted as lines from the top.
        If `position` is negative it is interpreted as lines from the bottom.

        Values that are too high or too low values are automatically adjusted
        during rendering.
        """
        self._trim_top = int(position)
        self._invalidate()

    def rows_max(self, size=None, focus=False):
        """Return the number of rows for `size`

        If `size` is not given, the currently rendered number of rows is returned.
        """
        if size is not None:
            ow = self._original_widget
            ow_size = self._get_original_widget_size(size)
            sizing = ow.sizing()
            if FIXED in sizing:
                self._rows_max_cached = ow.pack(ow_size, focus)[1]
            elif FLOW in sizing:
                self._rows_max_cached = ow.rows(ow_size, focus)
            else:
                raise RuntimeError('Not a flow/box widget: %r' % self._original_widget)
        return self._rows_max_cached


class ScrollBar(urwid.WidgetDecoration):
    def sizing(self):
        return frozenset((BOX,))

    def selectable(self):
        return True

    def __init__(self, widget, thumb_char=u'\u2588', trough_char=' ',
                 side=SCROLLBAR_RIGHT, width=1):
        """Box widget that adds a scrollbar to `widget`

        `widget` must be a box widget with the following methods:
          - `get_scrollpos` takes the arguments `size` and `focus` and returns
            the index of the first visible row.
          - `set_scrollpos` (optional; needed for mouse click support) takes the
            index of the first visible row.
          - `rows_max` takes `size` and `focus` and returns the total number of
            rows `widget` can render.

        `thumb_char` is the character used for the scrollbar handle.
        `trough_char` is used for the space above and below the handle.
        `side` must be 'left' or 'right'.
        `width` specifies the number of columns the scrollbar uses.
        """
        if BOX not in widget.sizing():
            raise ValueError('Not a box widget: %r' % widget)
        self.__super.__init__(widget)
        self._thumb_char = thumb_char
        self._trough_char = trough_char
        self.scrollbar_side = side
        self.scrollbar_width = max(1, width)
        self._original_widget_size = (0, 0)

    def render(self, size, focus=False):
        maxcol, maxrow = size

        sb_width = self._scrollbar_width
        ow_size = (max(0, maxcol - sb_width), maxrow)
        sb_width = maxcol - ow_size[0]

        ow = self._original_widget
        ow_base = self.scrolling_base_widget
        ow_rows_max = ow_base.rows_max(size, focus)
        if ow_rows_max <= maxrow:
            # Canvas fits without scrolling - no scrollbar needed
            self._original_widget_size = size
            return ow.render(size, focus)
        ow_rows_max = ow_base.rows_max(ow_size, focus)

        ow_canv = ow.render(ow_size, focus)
        self._original_widget_size = ow_size

        pos = ow_base.get_scrollpos(ow_size, focus)
        posmax = ow_rows_max - maxrow

        # Thumb shrinks/grows according to the ratio of
        # <number of visible lines> / <number of total lines>
        thumb_weight = min(1, maxrow / max(1, ow_rows_max))
        thumb_height = max(1, round(thumb_weight * maxrow))

        # Thumb may only touch top/bottom if the first/last row is visible
        top_weight = float(pos) / max(1, posmax)
        top_height = int((maxrow - thumb_height) * top_weight)
        if top_height == 0 and top_weight > 0:
            top_height = 1

        # Bottom part is remaining space
        bottom_height = maxrow - thumb_height - top_height
        assert thumb_height + top_height + bottom_height == maxrow

        # Create scrollbar canvas
        # Creating SolidCanvases of correct height may result in "cviews do not
        # fill gaps in shard_tail!" or "cviews overflow gaps in shard_tail!"
        # exceptions. Stacking the same SolidCanvas is a workaround.
        # https://github.com/urwid/urwid/issues/226#issuecomment-437176837
        top = urwid.SolidCanvas(self._trough_char, sb_width, 1)
        thumb = urwid.SolidCanvas(self._thumb_char, sb_width, 1)
        bottom = urwid.SolidCanvas(self._trough_char, sb_width, 1)
        sb_canv = urwid.CanvasCombine(
            [(top, None, False)] * top_height +
            [(thumb, None, False)] * thumb_height +
            [(bottom, None, False)] * bottom_height,
        )

        combinelist = [(ow_canv, None, True, ow_size[0]),
                       (sb_canv, None, False, sb_width)]
        if self._scrollbar_side != SCROLLBAR_LEFT:
            return urwid.CanvasJoin(combinelist)
        else:
            return urwid.CanvasJoin(reversed(combinelist))

    @property
    def scrollbar_width(self):
        """Columns the scrollbar uses"""
        return max(1, self._scrollbar_width)

    @scrollbar_width.setter
    def scrollbar_width(self, width):
        self._scrollbar_width = max(1, int(width))
        self._invalidate()

    @property
    def scrollbar_side(self):
        """Where to display the scrollbar; must be 'left' or 'right'"""
        return self._scrollbar_side

    @scrollbar_side.setter
    def scrollbar_side(self, side):
        if side not in (SCROLLBAR_LEFT, SCROLLBAR_RIGHT):
            raise ValueError('scrollbar_side must be "left" or "right", not %r' % side)
        self._scrollbar_side = side
        self._invalidate()

    @property
    def scrolling_base_widget(self):
        """Nearest `original_widget` that is compatible with the scrolling API"""
        def orig_iter(w):
            while hasattr(w, 'original_widget'):
                w = w.original_widget
                yield w
            yield w

        def is_scrolling_widget(w):
            return hasattr(w, 'get_scrollpos') and hasattr(w, 'rows_max')

        for w in orig_iter(self):
            if is_scrolling_widget(w):
                return w
        raise ValueError('Not compatible to be wrapped by ScrollBar: %r' % w)

    def keypress(self, size, key):
        return self._original_widget.keypress(self._original_widget_size, key)

    def mouse_event(self, size, event, button, col, row, focus):
        ow = self._original_widget
        ow_size = self._original_widget_size
        handled = False
        if hasattr(ow, 'mouse_event'):
            handled = ow.mouse_event(ow_size, event, button, col, row, focus)

        if not handled and hasattr(ow, 'set_scrollpos'):
            if button == 4:    # scroll wheel up
                pos = ow.get_scrollpos(ow_size)
                newpos = pos - 1
                if newpos < 0:
                    newpos = 0
                ow.set_scrollpos(newpos)
                return True
            elif button == 5:  # scroll wheel down
                pos = ow.get_scrollpos(ow_size)
                ow.set_scrollpos(pos + 1)
                return True

        return False
