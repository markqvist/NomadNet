# Image file handling for the side-channel renderer
#
# The Kitty graphics protocol can decode and scale images in the terminal
# itself (data format ``f=100``), which means the widget needs no image
# decoding library at all. It only needs the *dimensions* of the image to lay
# it out correctly in the urwid canvas; those are trivially parseable from the
# file headers of the supported formats.
# 
# Supported source formats:
#  - WebP (VP8, VP8L and VP8X)
#  - PNG
# 
# The payload transmitted to the terminal is always a PNG file: PNG sources
# are passed through verbatim, and WebP sources are converted transparently
# by the multi-backend conversion chain in :mod:`._webp` (no required
# dependencies). The conversion result is cached on disk, so each unique
# WebP is converted at most once per system.

import hashlib
import os

MAX_PAYLOAD_BYTES           = 8 * 1024 * 1024
MAX_CONVERTED_PAYLOAD_BYTES = 16 * 1024 * 1024
_PNG_SIGNATURE              = b"\x89PNG\r\n\x1a\n"

# Returns (width, height) from a PNG file.
def _parse_png(data):
    if not data.startswith(_PNG_SIGNATURE): raise ValueError("not a PNG")
    if len(data) < 24 or data[12:16] != b"IHDR": raise ValueError("PNG missing IHDR chunk")
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if not (width > 0 and height > 0): raise ValueError("PNG has null dimensions")
    return width, height

# Returns (width, height) from a WebP file (VP8, VP8L or VP8X).
def _parse_webp(data):
    if not data.startswith(b"RIFF") or data[8:12] != b"WEBP": raise ValueError("not a WebP")
    if len(data) < 30: raise ValueError("WebP file too short")
    fourcc = data[12:16]
    if fourcc == b"VP8X":
        # 10-byte chunk: flags(1) reserved(3) canvas-w-1(3 LE) canvas-h-1(3 LE)
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
    elif fourcc == b"VP8 ":
        # frame tag(3) start code 0x9d012a(3) width(2 LE, 14 bits) height(2 LE, 14 bits)
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
    elif fourcc == b"VP8L":
        # signature(1) then 4 bytes: w-1 (14 bits) | h-1 (14 bits) | ...
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
    else: raise ValueError("unsupported WebP variant %r" % fourcc)
    if not (width > 0 and height > 0): raise ValueError("WebP has null dimensions")
    return width, height


def parse_image_header(data):
    if data[:8] == _PNG_SIGNATURE:
        w, h = _parse_png(data)
        return "PNG", w, h
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        w, h = _parse_webp(data)
        return "WebP", w, h
    raise ValueError("unsupported image format (only PNG and WebP)")

# Loads an image file and exposes its PNG bytes and dimensions.
# The payload is always a PNG file, transmitted verbatim to the terminal
# (Kitty's f=100 data format). The dimensions are used only for layout.
# WebP sources are converted transparently to PNG on load.
class ImageData(object):
    def __init__(self, path, max_bytes=MAX_PAYLOAD_BYTES, remote_source=False):
        self.path = path
        self.error = None
        self.format = None
        self.source_format = None
        self.conversion_backend = None
        self.width = 0
        self.height = 0
        self.data = None
        try:
            with open(path, "rb") as f: data = f.read()
        except OSError as e:
            self.error = "Could not read file: %s" % e
            return
        
        if len(data) > max_bytes:
            self.error = "File too large (%.1f MiB > %d MiB)" % (len(data) / (1024 * 1024), max_bytes // (1024 * 1024))
            return
        
        if not data:
            self.error = "Empty file"
            return
        
        try: self.format, self.width, self.height = parse_image_header(data)
        except ValueError as e:
            self.error = str(e)
            return
        
        self.source_format = self.format
        if self.format == "WebP":
            from . import _webp
            png = _webp.convert_webp_to_png(data)
            if png is None:
                self.error = "WebP conversion failed (no working backend available)"
                return
            if len(png) > MAX_CONVERTED_PAYLOAD_BYTES:
                self.error = "Converted image too large (%.1f MiB > %d MiB)" % (len(png) / (1024 * 1024), MAX_CONVERTED_PAYLOAD_BYTES // (1024 * 1024))
                return

            self.data = png
            self.format = "PNG"
            self.conversion_backend = _webp.last_backend()
        
        else:
            if remote_source:
                self.error = "Invalid image format, remote images must be WebP"
                return
            else:
                self.data = data
        
        # Content key for de-duplication: identical bytes = same key, so
        # the same image transmitted once can be placed many times.
        self._key = hashlib.sha256(self.data).hexdigest()

    @property
    def ok(self): return self.data is not None

    @property
    def key(self): return getattr(self, "_key", None)

    @property
    def size(self): return (self.width, self.height)

    def description(self):
        if self.ok:
            if self.source_format == "WebP":
                return "WebP %dx%d -> PNG (%s)" % (self.width, self.height, self.conversion_backend or "cached")
            else:
                return "%s %dx%d" % (self.format, self.width, self.height)

        return self.error
