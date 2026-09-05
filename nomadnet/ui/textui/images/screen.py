import urwid

from . import _ctlseqs
from ._imagestore import image_store
from ._termlib import is_kitty_supported
from .widget import ImageWidget

# A raw display screen subclass with Kitty TGP side-channel support
class ImageScreen(urwid.raw_display.Screen):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ti_images = {}

    ##########
    # Output #
    ##########

    def write(self, data):
        if isinstance(data, bytes): data = data.decode("ascii")
        return super().write(data)

    #############
    # Lifecycle #
    #############

    def clear(self):
        # Clears all images and forces a full repaint
        if is_kitty_supported():
            self.write(_ctlseqs.KITTY_DELETE_ALL)
            self._ti_images = {}
            image_store.mark_all_untransmitted()
        return super().clear()

    def _start(self, *args, **kwargs):
        ret = super()._start(*args, **kwargs)
        if is_kitty_supported():
            # Clear any images left over from a previous run/instance.
            self.write(_ctlseqs.KITTY_DELETE_ALL)
            self._ti_images = {}
            image_store.mark_all_untransmitted()
        return ret

    def _stop(self):
        self.purge_images()
        try: return super()._stop()
        finally: self._ti_images = {}

    def purge_images(self):
        # Purges all image data from the terminal buffer.
        if not is_kitty_supported(): return
        if self._ti_images or image_store.transmitted():
            self.write(_ctlseqs.KITTY_DELETE_ALL)
        self._ti_images = {}
        image_store.mark_all_untransmitted()

    ###########
    # Drawing #
    ###########

    def draw_screen(self, size, canvas):
        # Draws the canvas, then updates on-screen images within a
        # synchronized-update region to prevent flicker.        
        self.write(_ctlseqs.BEGIN_SYNCED_UPDATE)
        try:
            super().draw_screen(size, canvas)
            self._ti_update(canvas)
        finally:
            self.write(_ctlseqs.END_SYNCED_UPDATE)
            self.flush()

    def _ti_update(self, canvas):
        # Places/updates/deletes image placements to match the current
        # canvas, and evicts orphaned image data.
        if not is_kitty_supported(): return

        entries = self._ti_scan(canvas)
        current = {}
        for widget, row, col, canvas_cols, trim_top, vis_rows in entries:
            current[id(widget)] = (widget, row, col, canvas_cols, trim_top, vis_rows)

        # For widgets that scrolled completely out of view, remove their
        # placement only. The image data is kept in the terminal so that
        # scrolling back just re-places it.
        for wid, info in list(self._ti_images.items()):
            if wid in current: continue
            self._ti_unplace(info["widget"])
            del self._ti_images[wid]

        # For visible widgets, place/update the visible slice in place.
        for wid, (widget, row, col, canvas_cols, trim_top, vis_rows) in current.items():
            info = self._ti_images.setdefault(wid, {"widget": widget, "drawn": None})
            if vis_rows <= 0 or trim_top >= widget._ti_rows:
                if info["drawn"] is not None:
                    self._ti_unplace(widget)
                    info["drawn"] = None
                continue

            key = self._placement_key(widget, row, col, canvas_cols, trim_top, vis_rows)
            if key is None:
                if info["drawn"] is not None:
                    self._ti_unplace(widget)
                    info["drawn"] = None
                continue

            if info["drawn"] == key: continue
            self._ti_place(widget, key)
            info["drawn"] = key

        # Evict image data that no live widget references any more
        for key, image_id in image_store.evict_orphans():
            self.write(_ctlseqs.KITTY_DELETE_IMAGE % image_id)
            image_store.evict(key)

    #############
    # Internals #
    #############

    def _ti_scan(self, canvas):
        # Walks the canvas shards and returns a list of
        # (widget, row, col, canvas_cols, trim_top, visible_rows)
        # for every visible image canvas.
        found = []
        if not isinstance(canvas, urwid.CompositeCanvas): return found

        def process_shard_tails():
            nonlocal col
            while col in shard_tails:
                *trim, cols, rows, canv = shard_tails[col]
                if rows > n_rows: shard_tails[col] = (*trim, cols, rows - n_rows, canv)
                else:             del shard_tails[col]
                col += cols

        shard_tails = {}
        row = 0
        for n_rows, cviews in canvas.shards:
            col = 0
            for cview in cviews:
                process_shard_tails()
                *trim, cols, rows, _, canv = cview
                widget = self._ti_widget_of(canv)
                if widget is not None: found.append((widget, row, col, cols, trim[1], rows))
                if rows > n_rows: shard_tails[col] = (*trim, cols, rows - n_rows, canv)
                col += cols

            process_shard_tails()
            row += n_rows

        return found

    @staticmethod
    def _ti_widget_of(canv):
        # Returns the ImageWidget for a leaf canvas, or None
        widget_info = getattr(canv, "_widget_info", None)
        if not widget_info: return None
        widget = widget_info[0]
        if isinstance(widget, ImageWidget) and widget._ti_data.ok and not widget._ti_closed: return widget
        return None

    def _placement_key(self, widget, row, col, canvas_cols, trim_top, vis_rows):
        # Compute placement parameters for the visible slice of
        # an image, including the alignment offset.

        cols = widget._ti_cols
        rows = widget._ti_rows
        if not (cols and rows): return None
        place_col = col
        if cols < canvas_cols:
            align = widget._ti_align
            spare = canvas_cols - cols
            if align == ">":   place_col += spare
            elif align == "|": place_col += spare // 2

        vis_rows = max(1, min(vis_rows, rows))
        y_px = h_px = None
        if not (trim_top == 0 and vis_rows == rows):
            # Crop to the visible slice of the image, in image pixels
            ih = widget._ti_data.height
            y_px = min(ih - 1, round(trim_top * ih / rows))
            h_px = max(1, min(ih - y_px, round(vis_rows * ih / rows)))

        return (row, place_col, cols, vis_rows, y_px, h_px)

    def _ti_place(self, widget, key):
        # Place (or in-place update) the visible slice of an image
        row, place_col, cols, vis_rows, y_px, h_px = key
        entry = image_store.entry_for(widget._ti_key)
        if entry is None:
            # This should not happen, but if the image data was evicted
            # while the image was still alive, re-register it so the
            # data can be re-transmitted to the terminal buffer.
            image_store.register(widget._ti_key, widget._ti_data.data)
            entry = image_store.entry_for(widget._ti_key)
        image_id = entry["image_id"]

        if not entry["transmitted"]:
            payload = widget._ti_data.data
            b64_len = (len(payload) * 4 + 2) // 3
            n_chunks = max(1, (b64_len + _ctlseqs.CHUNK_SIZE - 1) // _ctlseqs.CHUNK_SIZE)
            self.write(_ctlseqs.kitty_transmission(_ctlseqs.kitty_transmit_control(image_id), payload))
            entry["transmitted"] = True

        self.write(_ctlseqs.CURSOR_POSITION % (row + 1, place_col + 1))
        self.write(_ctlseqs.kitty_placement(image_id, widget._ti_z, cols, vis_rows, widget._ti_z, y=y_px, h=h_px))

    def _ti_unplace(self, widget):
        # Delete a widget's placement, but keep the
        # image data in the terminal buffer.
        entry = image_store.entry_for(widget._ti_key)
        if entry is None: return
        self.write(_ctlseqs.KITTY_DELETE_PLACEMENT % (entry["image_id"], widget._ti_z))
