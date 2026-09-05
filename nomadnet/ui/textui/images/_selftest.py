#!/usr/bin/env python3
"""
.. Images - headless self test

Exercises the widget + screen machinery without a terminal: image header
parsing, display sizing, shard scanning, APC construction/chunking and the
transmit/delete state machine at various scroll positions.

Run::

    python3 -m nomadnet.ui.textui.images._selftest [image-file]
"""

import base64
import io
import os
import shutil
import struct
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

import urwid

from nomadnet.ui.textui.images import _ctlseqs
from nomadnet.ui.textui.images import _imagestore
from nomadnet.ui.textui.images import _termlib
from nomadnet.ui.textui.images._imagedata import ImageData, parse_image_header
from nomadnet.ui.textui.images.screen import ImageScreen
from nomadnet.ui.textui.images.widget import ImageWidget

DEFAULT_IMAGE = os.path.expanduser("~/Scratchpad/test.png")
VIEWPORT = (80, 24)
CELL_SIZE = (1, 2)  # forced fallback for deterministic layout

PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   - %s" % label)
    else:
        FAIL += 1
        print("  FAIL - %s" % label)


def build_pile(image_path, wrap_attrmap=False):
    widgets = []
    for i in range(12):
        widgets.append(urwid.Text("[%02d]\nline one\nline two\n" % i))  # 3 rows each
    img = ImageWidget(image_path)
    if wrap_attrmap:
        img = urwid.AttrMap(img, "body")
    widgets.append(urwid.Divider(" "))
    widgets.append(img)
    widgets.append(urwid.Divider(" "))
    for i in range(12):
        widgets.append(urwid.Text("[%02d]\nline one\nline two\n" % (13 + i)))
    return urwid.Pile(widgets)


class RecordingScreen(ImageScreen):
    def __init__(self):
        super().__init__()
        self.log = []

    def write(self, data):
        if isinstance(data, bytes):
            data = data.decode("ascii")
        self.log.append(data)
        return data

    def flush(self):
        pass


def extract_transmit(log):
    """Returns (image_id, joined_b64_payload) of the a=t transmission, or
    None if no transmission is present."""
    image_id = None
    payloads = []
    for item in log:
        if item.startswith("\x1b_Ga=t"):
            for piece in item.split("\x1b_G")[1:]:
                body = piece[:-2]  # strip the trailing ST (ESC \)
                head, sep, payload = body.partition(";")
                if not sep:
                    continue
                if image_id is None:
                    image_id = int(head.split("i=")[1].split(",")[0])
                payloads.append(payload)
    if image_id is None:
        return None
    return image_id, "".join(payloads)


def extract_placements(log):
    """Returns the control data of every a=p placement command."""
    return [
        item[3:-2]
        for item in log
        if item.startswith("\x1b_Ga=p")
    ]


def extract_deletes(log):
    """Returns the control data of every a=d delete command."""
    return [
        item[3:-2]
        for item in log
        if item.startswith("\x1b_Ga=d")
    ]


def screen_probe_placement_key(widget, row, col, canvas_cols, trim_top, vis_rows):
    """Computes an ImageScreen placement key without a screen instance."""
    return ImageScreen._placement_key(
        None, widget, row, col, canvas_cols, trim_top, vis_rows)


def test_header_parse(image_path):
    print("== header parsing ==")
    with open(image_path, "rb") as f:
        data = f.read()
    fmt, w, h = parse_image_header(data)
    check(fmt == "PNG", "detected PNG")
    check(w == 1280 and h == 960, "dimensions %dx%d" % (w, h))
    imgdata = ImageData(image_path)
    check(imgdata.ok, "ImageData loads without error")
    check(imgdata.size == (w, h), "ImageData size matches")


def test_transmission_encoding(image_path):
    print("== APC encoding/chunking ==")
    small = b"\x89PNG\r\n\x1a\n" + b"x" * 100
    single = _ctlseqs.kitty_transmission(b"a=T,f=100,c=80,r=30,z=1", small)
    check(single.count(b"\x1b_G") == 1, "single-chunk transmission has one APC")
    check(single.startswith(b"\x1b_Ga=T,f=100,c=80,r=30,z=1;"), "control data correct")
    check(single.endswith(b"\x1b\\"), "ends with ST")
    payload = single.split(b";", 1)[1][:-2]
    check(base64.b64decode(payload) == small, "payload round-trips to original file")

    with open(image_path, "rb") as f:
        data = f.read()
    chunks = _ctlseqs.kitty_transmission(b"a=T,f=100", data, chunk_size=16)
    apcs = chunks.split(b"\x1b\\")[:-1]
    check(len(apcs) > 1, "multi-chunk transmission splits into %d APCs" % len(apcs))
    first, last = apcs[0], apcs[-1]
    heads = [a.split(b";", 1)[0][3:] for a in apcs]
    check(b",m=1;" in first, "first chunk carries control + m=1")
    check(last.startswith(b"\x1b_Gm=0;"), "last chunk carries m=0")
    check(sum(b"a=T" in h for h in heads) == 1, "control data appears only once")
    check(all(h == b"m=1" or h == b"m=0" for h in heads[1:]), "continuation chunks carry only the chunk marker")
    joined_b64 = b"".join(a.split(b";", 1)[1] for a in apcs)
    check(base64.b64decode(joined_b64) == data, "multi-chunk payload reassembles")


_TINY_WEBP = base64.b64decode(
    "UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAUAmJaQAA3AA/vuUAAA=")


def _webp_fixture():
    """Returns (webp_bytes, (width, height)): a 4x4 WebP generated with
    Pillow when available (more representative), else a 1x1 constant."""
    try:
        from PIL import Image
        if _webp_module_available():
            image = Image.new("RGBA", (4, 4))
            for y in range(4):
                for x in range(4):
                    image.putpixel((x, y), (x * 60, y * 60, x * y * 10, 255))
            buf = io.BytesIO()
            image.save(buf, format="WEBP")
            data = buf.getvalue()
            if parse_image_header(data)[0] == "WebP":
                return data, (4, 4)
    except Exception:
        pass
    return _TINY_WEBP, (1, 1)


def _webp_module_available():
    try:
        from PIL import features
        return bool(features.check("webp"))
    except Exception:
        return False


def test_webp_conversion():
    print("== webp conversion ==")
    from nomadnet.ui.textui.images import _webp
    from nomadnet.ui.textui.images._imagedata import MAX_CONVERTED_PAYLOAD_BYTES

    fmt, w, h = parse_image_header(_TINY_WEBP)
    check((fmt, w, h) == ("WebP", 1, 1), "embedded fixture is a 1x1 WebP")

    fixture, dims = _webp_fixture()
    check(parse_image_header(fixture)[1:] == dims,
          "webp fixture has expected dimensions")

    cache_tmp = tempfile.mkdtemp(prefix="imgw-test-cache-")
    prev_cache_env = os.environ.get("NOMADNET_IMAGE_CACHE")
    os.environ["NOMADNET_IMAGE_CACHE"] = cache_tmp
    try:
        # Each available backend must convert the fixture to a valid PNG
        # with matching dimensions. Backends are invoked directly, since
        # the on-disk cache would otherwise mask all but the first one.
        _webp.reset()
        present = [name for name, avail in _webp.available_backends() if avail]
        converted = 0
        for name in present:
            png = _webp._BACKENDS[name](fixture, dims)
            ok = (png is not None and png.startswith(b"\x89PNG")
                  and _webp._png_dims(png) == dims)
            check(ok, "%s backend converts to a valid PNG" % name)
            if ok:
                converted += 1
        check(converted >= 1, "at least one backend converts webp (got %d)" % converted)

        # Repeat conversion is served from the on-disk cache: the backend
        # table is disabled and the conversion still succeeds.
        _webp.reset()
        png1 = _webp.convert_webp_to_png(fixture)
        check(png1 is not None, "first conversion succeeds")
        orig_backends = dict(_webp._BACKENDS)
        _webp._BACKENDS = {name: (lambda *a, **k: None) for name in _webp.BACKENDS}
        png2 = _webp.convert_webp_to_png(fixture)
        check(png1 == png2 and _webp.stats()["cache_hits"] >= 1,
              "repeat conversion served from the on-disk cache")
        _webp._BACKENDS = orig_backends

        # ImageData-level transparency: a webp file loads as a PNG.
        _webp.reset()
        fd, webp_path = tempfile.mkstemp(suffix=".webp")
        with os.fdopen(fd, "wb") as f:
            f.write(fixture)
        d = ImageData(webp_path)
        check(d.ok and d.format == "PNG" and d.size == dims,
              "ImageData converts webp transparently to PNG")
        check(d.data.startswith(b"\x89PNG\r\n\x1a\n") and d.key is not None,
              "converted payload is a keyed PNG")
        check("-> PNG" in d.description(), "description notes the conversion")
        os.unlink(webp_path)

        # Converted-payload cap.
        _webp.reset()
        orig_convert = _webp.convert_webp_to_png
        _webp.convert_webp_to_png = lambda data: b"x" * (MAX_CONVERTED_PAYLOAD_BYTES + 1)
        fd, webp_path = tempfile.mkstemp(suffix=".webp")
        with os.fdopen(fd, "wb") as f:
            f.write(fixture)
        d = ImageData(webp_path)
        check(not d.ok and "converted image too large" in d.error,
              "converted payload capped at %d MiB"
              % (MAX_CONVERTED_PAYLOAD_BYTES // (1024 * 1024)))
        os.unlink(webp_path)
        _webp.convert_webp_to_png = orig_convert

        # Undecodable webp (valid header/dimensions, garbage bitstream).
        _webp.reset()
        junk = (b"RIFF" + struct.pack("<I", 30) + b"WEBP" + b"VP8 "
                + b"\x00" * 10 + b"\x10\x00\x10\x00" + b"\xff" * 12)
        check(parse_image_header(junk)[1:] == (16, 16),
              "junk fixture parses as a 16x16 WebP")
        fd, webp_path = tempfile.mkstemp(suffix=".webp")
        with os.fdopen(fd, "wb") as f:
            f.write(junk)
        d = ImageData(webp_path)
        check(not d.ok and "conversion failed" in d.error,
              "undecodable webp results in the error state")
        os.unlink(webp_path)
    finally:
        if prev_cache_env is not None:
            os.environ["NOMADNET_IMAGE_CACHE"] = prev_cache_env
        else:
            os.environ.pop("NOMADNET_IMAGE_CACHE", None)
        shutil.rmtree(cache_tmp, ignore_errors=True)
        _webp.reset()


def test_winsize_parsing():
    print("== TIOCGWINSZ parsing ==")
    from nomadnet.ui.textui.images import _termlib
    # struct order is (rows, cols, xpixel, ypixel)
    check(_termlib._cell_size_from_winsize([40, 100, 1000, 800]) == (10, 20),
          "correct winsize -> (10, 20)")
    check(_termlib._cell_size_from_winsize([24, 80, 960, 480]) == (12, 20),
          "correct winsize -> (12, 20)")
    check(_termlib._cell_size_from_winsize([24, 80, 0, 0]) is None,
          "zero pixel fields -> None")
    check(_termlib._cell_size_from_winsize([40, 100, 800, 1000]) == (8, 25),
          "portrait window cell keeps valid aspect")
    check(_termlib._cell_size_from_winsize([30, 80, 1200, 240]) is None,
          "implausible aspect (broken reporting) -> None")
    check(_termlib._cell_size_from_winsize([0, 0, 0, 0]) is None,
          "empty winsize -> None")


def test_widget_layout(image_path):
    print("== widget layout ==")
    _termlib.kitty_supported = True
    _termlib.cell_size = CELL_SIZE
    # Force a deterministic terminal size for the height-percent cases.
    _orig_terminal_size = _termlib.get_terminal_size
    _termlib.get_terminal_size = lambda: (80, 24)
    _orig_ui_margin = None
    from nomadnet.ui.textui.images import widget as _widget_mod
    _orig_ui_margin = _widget_mod.UI_MARGIN
    _widget_mod.UI_MARGIN = 8
    try:
        imgdata = ImageData(image_path)
        w = ImageWidget(image_path)
        iw, ih = imgdata.size
        expected_rows = max(1, round(80 * CELL_SIZE[0] * ih / (CELL_SIZE[1] * iw)))
        rows = w.rows((80,))
        check(rows == expected_rows,
              "default: rows((80,)) == %d, got %d" % (expected_rows, rows))
        canvas = w.render((80,))
        check(isinstance(canvas, urwid.SolidCanvas), "render returns a solid canvas")
        check(canvas.rows() == rows and canvas.cols() == 80, "canvas sized 80x%d" % rows)
        check(w._ti_rows == rows and w._ti_cols == 80, "widget stores display size")
        w.close()

        # width as absolute columns (aspect preserved); the canvas fills the
        # allocated width while the image rect is the resolved size.
        w = ImageWidget(image_path, width=40)
        c, r = w._display_size(80)
        check((c, r) == (40, 15), "width=40 -> (40, 15), got (%d, %d)" % (c, r))
        canvas = w.render((80,))
        check((canvas.cols(), canvas.rows()) == (80, 15),
              "width=40 canvas fills the row (80, 15), got (%d, %d)"
              % (canvas.cols(), canvas.rows()))
        check((w._ti_cols, w._ti_rows) == (40, 15),
              "width=40 image rect stored (40, 15)")
        w.close()

        # width as percent of the layout width
        w = ImageWidget(image_path, width="50%")
        c, r = w._display_size(80)
        check((c, r) == (40, 15), "width=50%% -> (40, 15), got (%d, %d)" % (c, r))
        w.close()

        # height as absolute rows (width derived, aspect preserved)
        w = ImageWidget(image_path, height=20)
        c, r = w._display_size(80)
        check(r == 20 and c == 53, "height=20 -> (53, 20), got (%d, %d)" % (c, r))
        w.close()

        # height as percent of the visible page height
        # page = terminal lines (24) - UI_MARGIN (8) = 16; 50% -> 8 rows
        w = ImageWidget(image_path, height="50%")
        c, r = w._display_size(80)
        check(r == 8 and c == 21, "height=50%% -> (21, 8), got (%d, %d)" % (c, r))
        w.close()

        # both given: stretch to the exact rectangle
        w = ImageWidget(image_path, width=40, height=30)
        c, r = w._display_size(80)
        check((c, r) == (40, 30), "width=40,height=30 stretches -> (40, 30), got (%d, %d)" % (c, r))
        w.close()

        # stretching is clamped uniformly when overflowing the space
        w = ImageWidget(image_path, width=400, height=200)
        c, r = w._display_size(80)
        check((c, r) == (80, 40), "overflowing stretch clamped -> (80, 40), got (%d, %d)" % (c, r))
        w.close()

        # BOX layout: the canvas fills the box; the image rect is clamped
        # and re-derived (width from the clamped height).
        w = ImageWidget(image_path, name="box")
        canvas = w.render((80, 10))
        check((canvas.cols(), canvas.rows()) == (80, 10),
              "BOX render((80,10)) canvas fills the box, got (%d, %d)"
              % (canvas.cols(), canvas.rows()))
        check((w._ti_cols, w._ti_rows) == (27, 10),
              "BOX image rect clamped -> (27, 10), got (%d, %d)"
              % (w._ti_cols, w._ti_rows))
        w.close()

        # invalid specifications
        def raises(ctor, want):
            try:
                ctor()
            except want:
                return True
            except Exception:
                return False
            return False
        check(raises(lambda: ImageWidget(image_path, width="xx"), ValueError),
              "width='xx' raises ValueError")
        check(raises(lambda: ImageWidget(image_path, height=0), ValueError),
              "height=0 raises ValueError")
        check(raises(lambda: ImageWidget(image_path, width=1.5), TypeError),
              "width=1.5 raises TypeError")
        check(raises(lambda: ImageWidget(image_path, height="50"), ValueError),
              "height='50' raises ValueError")

        # settable properties re-resolve and invalidate
        w = ImageWidget(image_path)
        w.width = "50%"
        c, r = w._display_size(80)
        check((c, r) == (40, 15), "set width=50%% property -> (40, 15)")
        w.height = 10
        c, r = w._display_size(80)
        check((c, r) == (40, 10), "width+height set -> stretch (40, 10), got (%d, %d)" % (c, r))
        w.width = None
        w.height = 10
        c, r = w._display_size(80)
        check((c, r) == (27, 10), "height-only after reset -> (27, 10), got (%d, %d)" % (c, r))
        w.close()

        # alignment: placement column of a narrowed image inside its canvas
        w = ImageWidget(image_path, width=40)  # default center
        w.render((80,))  # sets _ti_cols/_ti_rows
        check(w._ti_align == "|", "default alignment is center")
        key = screen_probe_placement_key(w, 3, 0, 80, 0, 15)
        check(key == (3, 20, 40, 15, None, None),
              "centered placement col -> %s" % (key,))
        w.align = "left"
        key = screen_probe_placement_key(w, 3, 0, 80, 0, 15)
        check(key == (3, 0, 40, 15, None, None), "left placement col -> 0")
        w.align = "right"
        key = screen_probe_placement_key(w, 3, 0, 80, 0, 15)
        check(key == (3, 40, 40, 15, None, None), "right placement col -> 40")
        check(raises(lambda: ImageWidget(image_path, align="top"), ValueError),
              "align='top' raises ValueError")
        w.close()
    finally:
        _termlib.get_terminal_size = _orig_terminal_size
        if _orig_ui_margin is not None:
            _widget_mod.UI_MARGIN = _orig_ui_margin


def find_image_widget(pile):
    for widget, _opts in pile.contents:
        child = widget
        if isinstance(child, urwid.AttrMap):
            child = child.original_widget
        if isinstance(child, ImageWidget):
            return child
    return None


def run_screen_test(image_path, wrap_attrmap, label):
    print("== screen state machine (%s) ==" % label)
    _termlib.kitty_supported = True
    _termlib.cell_size = CELL_SIZE
    _imagestore.image_store.reset()

    pile = build_pile(image_path, wrap_attrmap=wrap_attrmap)
    scrollable = urwid.Scrollable(pile, force_forward_keypress=True)
    screen = RecordingScreen()

    img_widget = find_image_widget(pile)
    check(img_widget is not None, "image widget found in pile")
    z = img_widget._ti_z
    entry = _imagestore.image_store.entry_for(img_widget._ti_key)
    check(entry is not None and entry["refs"] == 1, "widget registered with image store")
    image_id = entry["image_id"]
    b64 = base64.b64encode(img_widget._ti_data.data).decode("ascii")

    def entries_at(offset):
        scrollable.set_scrollpos(offset)
        canvas = scrollable.render(VIEWPORT)
        return screen._ti_scan(canvas)

    # Build a timeline of image visibility across all scroll offsets.
    # state = (trim_top, row, visible_rows)
    timeline = []
    max_offset = 200
    for off in range(max_offset + 1):
        entries = entries_at(off)
        if not entries:
            timeline.append((off, None))
            continue
        widget, row, col, canvas_cols, trim_top, vis_rows = entries[0]
        timeline.append((off, (trim_top, row, vis_rows)))
    image_rows = img_widget._ti_rows
    visible = [t for t in timeline if t[1] is not None]
    check(len(visible) > 0, "image is visible at some scroll offset")
    if not visible:
        return

    def first_offset(pred):
        for off, state in timeline:
            if state is not None and pred(state):
                return off
        return None

    off_enter = first_offset(lambda s: s[0] == 0)       # trim_top == 0
    off_clip = first_offset(lambda s: s[0] > 0)         # top-clipped
    check(off_enter is not None, "found offset with image fully entered")
    check(off_clip is not None, "found offset with image top-clipped")
    if off_enter is None or off_clip is None:
        return
    # State at the entry offset: (trim_top, row, visible_rows)
    off_enter_vis_rows = timeline[off_enter][1][2]

    last_visible_off = visible[-1][0]
    off_away = last_visible_off + 1 if last_visible_off < max_offset else None
    check(off_away is not None, "found offset past the image")

    def update(offset):
        screen.log = []
        scrollable.set_scrollpos(offset)
        canvas = scrollable.render(VIEWPORT)
        screen._ti_update(canvas)
        return list(screen.log)

    # 1. before the image is visible: nothing
    log = update(0)
    check(not any("a=t" in l or "a=p" in l for l in log),
          "nothing written while out of view")
    check(not screen._ti_images, "nothing tracked while out of view")

    # 2. image entered (bottom-clipped): transmit once, place the visible
    #    slice (y=0 crop) at the bottom.
    log = update(off_enter)
    trans = extract_transmit(log)
    placements = extract_placements(log)
    check(trans is not None, "image data transmitted on entry")
    if trans:
        trans_id, pb64 = trans
        check(trans_id == image_id, "transmit uses the store's image id")
        check(pb64 == b64, "transmitted payload is the original file")
    check(len(placements) == 1, "one placement on entry, got %d" % len(placements))
    if placements:
        ctrl = placements[0]
        check("i=%d" % image_id in ctrl and "p=%d" % z in ctrl,
              "placement references image id and placement id")
        check("c=80" in ctrl and "r=%d" % off_enter_vis_rows in ctrl,
              "placement has display size")
        check("y=0," in ctrl and "h=" in ctrl, "entry slice uses a y=0 crop")
        check("z=%d" % z in ctrl and "C=1" in ctrl and "q=1" in ctrl,
              "placement has z-index, C=1 and quiet mode")
    check(len(screen._ti_images) == 1 and
          screen._ti_images[id(img_widget)]["drawn"] is not None,
          "image tracked as drawn")
    check(entry["transmitted"], "store entry marked transmitted")

    # 3. move while visible: in-place placement update, no re-transmit,
    #    no delete.
    log = update(off_enter + 1)
    check(extract_transmit(log) is None, "position change does not re-transmit")
    check(len(extract_placements(log)) == 1, "position change re-places in place")
    check(not extract_deletes(log), "position change does not delete")

    # 4. top-clipped: placement with a y>0 crop.
    log = update(off_clip)
    placements = extract_placements(log)
    check(len(placements) == 1, "top-clip places a slice, got %d" % len(placements))
    if placements:
        ctrl = placements[0]
        y_px = int(ctrl.split("y=")[1].split(",")[0].split(";")[0])
        check(",y=" in ctrl and "h=" in ctrl and y_px > 0,
              "top-clipped placement has y>0 crop (y=%d)" % y_px)

    # 5. scrolled past: placement deleted, image data kept.
    log = update(off_away)
    deletes = extract_deletes(log)
    check(deletes == ["a=d,d=i,i=%d,p=%d" % (image_id, z)],
          "scroll-away deletes the placement only: %s" % deletes)
    check(extract_transmit(log) is None, "scroll-away does not transmit")
    check(id(img_widget) not in screen._ti_images, "widget untracked after scroll-away")

    # 6. scroll back: re-placed from the kept data, no re-transmission.
    log = update(off_enter)
    check(extract_transmit(log) is None, "scroll-back does not re-transmit")
    check(len(extract_placements(log)) == 1, "scroll-back re-places the image")

    # 7. still visible, unchanged position: nothing written.
    log = update(off_enter)
    check(not extract_placements(log) and not extract_deletes(log),
          "unchanged position writes nothing")

    # 8. widget closed -> orphaned data evicted from the terminal.
    img_widget.close()
    log = update(off_away)
    deletes = extract_deletes(log)
    check("a=d,d=I,i=%d" % image_id in deletes,
          "orphaned image data evicted with d=I")
    check(_imagestore.image_store.entry_for(img_widget._ti_key) is None,
          "evicted entry dropped from the store")


def test_eviction_and_purge(image_path):
    print("== eviction and purge ==")
    _termlib.kitty_supported = True
    _termlib.cell_size = CELL_SIZE
    _imagestore.image_store.reset()

    # Shared source: two widgets with the same file share one store entry.
    w1 = ImageWidget(image_path)
    w2 = ImageWidget(image_path)
    entry = _imagestore.image_store.entry_for(w1._ti_key)
    check(entry["refs"] == 2, "identical sources share one registry entry (refs=%d)"
          % entry["refs"])
    check(w2._ti_key == w1._ti_key, "identical sources have the same content key")

    w1.close()
    check(entry["refs"] == 1, "closing one widget decrements refcount")
    check(entry["transmitted"] is False, "no data transmitted yet")

    # Place w2 via a screen update and verify orphan eviction after close.
    pile = urwid.Pile([urwid.Text("x"), urwid.Divider(" "), w2,
                       urwid.Divider(" "), urwid.Text("y")])
    scrollable = urwid.Scrollable(pile, force_forward_keypress=True)
    screen = RecordingScreen()
    image_id = entry["image_id"]

    def update(offset):
        screen.log = []
        scrollable.set_scrollpos(offset)
        screen._ti_update(scrollable.render(VIEWPORT))
        return list(screen.log)

    log = update(2)
    check(extract_transmit(log) is not None, "image transmitted when widget visible")
    check(entry["transmitted"], "entry marked transmitted")

    w2.close()
    log = update(0)
    deletes = extract_deletes(log)
    check("a=d,d=I,i=%d" % image_id in deletes, "last reference closed -> d=I eviction")
    check(_imagestore.image_store.entry_for(w2._ti_key) is None,
          "entry dropped after eviction")

    # Purge: after transmitting, purge_images() deletes everything and the
    # next redraw re-transmits for still-visible widgets.
    _imagestore.image_store.reset()
    w3 = ImageWidget(image_path)
    pile = urwid.Pile([urwid.Text("x"), urwid.Divider(" "), w3,
                       urwid.Divider(" "), urwid.Text("y")])
    scrollable = urwid.Scrollable(pile, force_forward_keypress=True)
    screen2 = RecordingScreen()

    def update2(offset):
        screen2.log = []
        scrollable.set_scrollpos(offset)
        screen2._ti_update(scrollable.render(VIEWPORT))
        return list(screen2.log)

    log = update2(2)
    check(extract_transmit(log) is not None, "purge-test: image transmitted")
    screen2.log = []
    screen2.purge_images()
    check(any("a=d,d=A" in l for l in screen2.log), "purge deletes all (d=A)")
    check(_imagestore.image_store.transmitted() == [], "purge marks all untransmitted")

    log = update2(2)
    check(extract_transmit(log) is not None, "visible image re-transmitted after purge")
    check(len(extract_placements(log)) == 1, "visible image re-placed after purge")
    w3.close()


def main():
    image_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IMAGE
    print("Using image: %s" % image_path)
    _termlib.reset_caches()
    print("ambient cell size (env): %s" % (_termlib._query_cell_size(),))

    test_header_parse(image_path)
    test_transmission_encoding(image_path)
    test_webp_conversion()
    test_winsize_parsing()
    test_widget_layout(image_path)
    run_screen_test(image_path, wrap_attrmap=False, label="bare widget")
    run_screen_test(image_path, wrap_attrmap=True, label="attrmap-wrapped")
    test_eviction_and_purge(image_path)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
