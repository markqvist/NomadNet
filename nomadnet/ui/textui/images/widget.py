# An urwid widget that occupies the space an image should fill in a layout,
# without embedding any escape sequences in its canvas. The actual terminal
# graphics are transmitted by the ImageScreen class which tracks the widget's
# on-screen position after every draw.
# 
# This separation keeps the canvas trivially simple (urwid sees only blank
# rows) and lets the screen handle the hard parts; positioning, deletion when
# scrolled away, terminal resize and redraws - all of which are driven by
# urwid's own shard bookkeeping rather than by fragile escape-sequence
# manipulation inside canvas rows.
# 
# When the Kitty graphics protocol is unavailable (or the image cannot be
# loaded), the widget renders a simple text placeholder instead.

import os
import re
import urwid

from . import _termlib
from ._imagestore import image_store

DEFAULT_CELL_SIZE = (1, 2)  # Fallback, assume a 1:2 cell aspect ratio
MAX_Z_INDEX       = 2 ** 31 - 1
UI_MARGIN         = 8
_SIZE_SPEC_RE     = re.compile(r"(\d+(?:\.\d+)?)%")
_ALIGNS           = { "left": "<", "<": "<",
                      "center": "|", "|": "|",
                      "right": ">", ">": ">" }

def _check_align(value):
    if value not in _ALIGNS: raise ValueError("invalid alignment %r (expected 'left', 'center' or 'right')" % (value,))
    return _ALIGNS[value]


def _check_size_spec(value, name):
    if value is None: return None
    
    if isinstance(value, int):
        if value <= 0: raise ValueError("%s must be a positive integer, got %r" % (name, value))
        return value
    
    if isinstance(value, str):
        match = _SIZE_SPEC_RE.fullmatch(value)
        if not match or float(match.group(1)) <= 0:
            raise ValueError("invalid %s specification %r (expected a positive integer or a percent string like '50%%')" % (name, value))
        return value
    
    raise TypeError("invalid type for %s (got %s)" % (name, type(value).__name__))


class ImageWidget(urwid.Widget):
    # A widget that displays an image via the Kitty graphics protocol.
    # The widget is a plain FLOW/BOX widget; its canvas is blank. The
    # ImageScreen class performs the actual drawing over the Kitty
    # TGP side-channel.

    placeholder_glyph = ""

    _sizing = frozenset((urwid.FLOW, urwid.BOX))
    ignore_focus = True

    # Z-index allocation. Each widget instance gets a unique z-index so that
    # the screen can delete exactly one image when it scrolls away or moves.
    _ti_next_z = 1
    _ti_free_z = set()

    def __init__(self, path, name=None, width=None, height=None, align="center"):
        if path and not isinstance(path, (str, os.PathLike)): raise TypeError("path must be a string or path-like object")
        self.path = path
        self._notice = None
        self._ti_path = None
        self._ti_data = None
        self._ti_width = _check_size_spec(width, "width")
        self._ti_height = _check_size_spec(height, "height")
        self._ti_align = _check_align(align)
        self._ti_name = name if name is not None else ""
        self._ti_z = self._ti_alloc_z()
        self.image_id = self._ti_z
        
        # Display size (cols, rows) from the most recent render.
        # Used by the screen to place the image.
        self._ti_cols = None
        self._ti_rows = None
        self._ti_closed = False
        self._ti_key = None
        super().__init__()
        if self.path: self.load()

    def load(self, path=None):
        if path: self.path = path
        if self.path:
            from ._imagedata import ImageData
            self._ti_path = os.path.abspath(os.fspath(self.path))
            self._ti_data = ImageData(self._ti_path)

            if self._ti_data.ok:
                # Register with the image store (de-duplicates identical data
                # and allocates the terminal-side image id on first use).
                self._ti_key = self._ti_data.key
                image_store.register(self._ti_key, self._ti_data.data)
                self._invalidate()

    def notice(self, msg=""):
        if not msg: self._notice = None
        else:       self._notice = str(msg)
        self._invalidate()

    def __del__(self):
        try: type(self)._ti_free_z.add(self._ti_z)
        except Exception: pass
        try: self.close()
        except Exception: pass

    def close(self):
        # Releases the widget's reference to its image data.
        # The data is evicted from the terminal by the screen as soon as no
        # live widget references it any more. Safe to call multiple times and
        # from __del__.
        try:
            if not self._ti_closed:
                self._ti_closed = True
                if self._ti_key is not None: image_store.unregister(self._ti_key)
        except Exception: pass

    @classmethod
    def _ti_alloc_z(cls):
        if cls._ti_free_z: return cls._ti_free_z.pop()
        z = cls._ti_next_z
        if z >= MAX_Z_INDEX: raise RuntimeError("Too many image widgets")
        cls._ti_next_z += 1
        return z

    ##########
    # Sizing #
    ##########

    width = property(
        lambda self: self._ti_width,
        doc="""Display width specification: None (full width), a positive
        int (columns) or a percent string ("NN%") of the available layout
        width.""",
    )

    @width.setter
    def width(self, value):
        self._ti_width = _check_size_spec(value, "width")
        self._invalidate()

    height = property(
        lambda self: self._ti_height,
        doc="""Display height specification: None (derived, aspect
        preserving), a positive int (rows) or a percent string ("NN%") of
        the visible page height.""",
    )

    @height.setter
    def height(self, value):
        self._ti_height = _check_size_spec(value, "height")
        self._invalidate()

    align = property(
        lambda self: self._ti_align,
        doc="""Horizontal alignment of the image within its allocated
        space: ``"<"`` (left), ``"|"`` (center) or ``">"`` (right).""",
    )

    @align.setter
    def align(self, value):
        self._ti_align = _check_align(value)
        self._invalidate()

    def _short(self): return "img#%x" % (id(self) & 0xFFFFF)

    def _display_size(self, maxcol, maxrow=None):
        if not self._ti_data.ok: return (min(maxcol, 1), 1)
        iw, ih = self._ti_data.size
        cell_w, cell_h = _termlib.get_cell_size() or DEFAULT_CELL_SIZE
        w_spec, h_spec = self._ti_width, self._ti_height

        def _pct(value): return float(value[:-1]) / 100.0

        def _raw_width():
            if w_spec is None: return float(maxcol)
            if isinstance(w_spec, int): return float(w_spec)
            return maxcol * _pct(w_spec)

        def _raw_height():
            if h_spec is None: return None
            if isinstance(h_spec, int): return float(h_spec)
            columns, lines = _termlib.get_terminal_size()
            page = max(1, lines - UI_MARGIN)
            return page * _pct(h_spec)

        def _height_for_width(cols): return cols * cell_w * ih / (cell_h * iw)
        def _width_for_height(rows): return rows * cell_h * iw / (cell_w * ih)

        if w_spec is not None and h_spec is not None:
            # Stretch mode: Target rectangle, uniformly scaled down only if
            # it would overflow the available space.
            target_w = max(1.0, _raw_width())
            target_h = max(1.0, _raw_height())
            scale = min(1.0, maxcol / target_w)
            if maxrow is not None: scale = min(scale, maxrow / target_h)
            cols = max(1, round(target_w * scale))
            rows = max(1, round(target_h * scale))
        elif w_spec is not None:
            # Width given: Height derived, aspect preserving.
            cols = max(1, min(maxcol, round(_raw_width())))
            rows = max(1, round(_height_for_width(cols)))
            if maxrow is not None and rows > maxrow:
                rows = maxrow
                cols = max(1, min(maxcol, round(_width_for_height(rows))))
        elif h_spec is not None:
            # Height given: Width derived, aspect preserving.
            rows = max(1, round(_raw_height()))
            cols = max(1, min(maxcol, round(_width_for_height(rows))))
            if maxrow is not None and rows > maxrow:
                rows = maxrow
                cols = max(1, min(maxcol, round(_width_for_height(rows))))
        else:
            # Default: Full width, height derived.
            cols = maxcol
            rows = max(1, round(_height_for_width(cols)))
            if maxrow is not None and rows > maxrow:
                rows = maxrow
                cols = max(1, min(maxcol, round(_width_for_height(rows))))
        
        return (cols, rows)

    def rows(self, size, focus=False):
        maxcol = size[0]
        if not (self._ti_data and self._ti_data.ok and _termlib.is_kitty_supported()):
            return len(self._placeholder_lines())
        n = self._display_size(maxcol)[1]
        return n

    def render(self, size, focus=False):
        if len(size) == 2:
            maxcol, maxrow = size
            is_box = True
        else:
            maxcol, maxrow = size[0], None
            is_box = False

        if not (self._ti_data and self._ti_data.ok and _termlib.is_kitty_supported()):
            return self._placeholder_canvas(maxcol, maxrow, focus)

        cols, rows = self._display_size(maxcol, maxrow)
        self._ti_cols, self._ti_rows = cols, rows
        # urwid requires canvases to fill the allocated space exactly
        # (width == maxcol for FLOW, (maxcol, maxrow) for BOX). The image
        # itself is placed by the screen at its resolved size inside the
        # canvas, left-aligned; the rest of the canvas stays blank.
        if is_box: return ImageCanvas(maxcol, maxrow)
        else:      return ImageCanvas(maxcol, rows)

    #########################
    # Placeholder rendering #
    #########################

    def _placeholder_lines(self):
        return [f"{self.placeholder_glyph}{self._notice or self._ti_name}"]

    def _placeholder_canvas(self, maxcol, maxrow, focus):
        align = {"<": "left", "|": "center", ">": "right"}.get(self._ti_align, "center")
        text = urwid.Text("\n".join(self._placeholder_lines()), align=align)
        if maxrow is not None: return urwid.Filler(text).render((maxcol, maxrow), focus)
        else:                  return text.render((maxcol,), focus)


class ImageCanvas(urwid.SolidCanvas):
    # A blank canvas marking the space occupied by an image.
    # Urwid sets _widget_info on this canvas to the owning
    # ImageWidget. ImageScreen finds image canvases through
    # that reference during its shard scan.
    def __init__(self, cols, rows): super().__init__(" ", cols, rows)
