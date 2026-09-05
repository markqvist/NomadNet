# Kitty Terminal Graphics Protocol control sequences
# 
# Minimal set of control sequences needed for the Kitty graphics protocol
# side-channel image rendering used by the urwid image widget.

from base64 import standard_b64encode
import re

# Basic building blocks
APC = b"\x1b_" # Application Program Command
ST = b"\x1b\\" # String Terminator
CSI = b"\x1b["

# Kitty graphics: transmit-and-display with chunking support.
#   ESC _ G <control-data> ; <base64 payload> ESC \
KITTY_TRANSMISSION = b"\x1b_G%s;%s\x1b\\"

# Delete images: d=A (all placements visible on screen), d=i (one
# placement, data kept), d=I (whole image, data freed).
KITTY_DELETE_ALL = b"\x1b_Ga=d,d=A\x1b\\"
KITTY_DELETE_PLACEMENT = b"\x1b_Ga=d,d=i,i=%d,p=%d\x1b\\"
KITTY_DELETE_IMAGE = b"\x1b_Ga=d,d=I,i=%d\x1b\\"

# Support query (payload is base64 of 4 zero bytes; expects "i=31;OK")
KITTY_QUERY = b"\x1b_Ga=q,t=d,i=31,f=24,s=1,v=1,C=1,c=1,r=1;AAAA\x1b\\"
KITTY_QUERY_RESPONSE_RE = re.compile(b"\x1b_Gi=31;(?P<message>[^\x1b]*)\x1b\\\\")

# Cursor: absolute positioning, erase characters, cursor forward
CURSOR_POSITION = b"\x1b[%d;%dH"
ERASE_CHARS = b"\x1b[%dX"

# Synchronized output (DEC 2026) - reduces flicker/tearing when redrawing
BEGIN_SYNCED_UPDATE = b"\x1b[?2026h"
END_SYNCED_UPDATE = b"\x1b[?2026l"

# Terminal queries: cell size in pixels (XTWINOPS 16) + primary DA
CELL_SIZE_PX = b"\x1b[16t"
DA1 = b"\x1b[c"
# Response: CSI 4 ; <height-px> ; <width-px> t
CELL_SIZE_RESPONSE_RE = re.compile(b"\x1b\\[4;(?P<h>\\d+);(?P<w>\\d+)t")

# Maximum payload (base64) per transmission chunk, as recommended by the
# protocol documentation
CHUNK_SIZE = 4096

# Control data for a transmit-only (a=t) with a quiet mode (q=1)
def kitty_transmit_control(image_id): return b"a=t,i=%d,f=100,t=d,q=1" % image_id

# A placement command (a=p) for a previously transmitted image.
# Re-sending the same (image id, placement id) pair replaces the
# placement in place - used to move/resize/slice without flicker.
# y/h select the source rectangle (image pixels) when a slice of
# the image is displayed.
def kitty_placement(image_id, placement_id, cols, rows, z, y=None, h=None):
    control = b"a=p,i=%d,p=%d,c=%d,r=%d,z=%d,C=1,q=1" % (image_id, placement_id, cols, rows, z)
    if y is not None and h is not None: control += b",y=%d,h=%d" % (y, h)
    return KITTY_TRANSMISSION % (control, b"")

# Encodes a kitty graphics transmission, chunking the base64-encoded
# payload into ``chunk_size``-byte pieces.
def kitty_transmission(control, payload, chunk_size=CHUNK_SIZE):
    encoded = standard_b64encode(payload)
    chunks = [encoded[i:i + chunk_size] for i in range(0, len(encoded), chunk_size)]
    if not chunks:
        chunks = [b""]

    def control_for(index, n_chunks):
        if n_chunks == 1:
            return control
        if index == 0:
            # The control data appears only in the first chunk; the chunk
            # marker says more chunks are coming.
            return control + b",m=1"
        if index == n_chunks - 1:
            return b"m=0"
        return b"m=1"

    return b"".join(KITTY_TRANSMISSION % (control_for(i, len(chunks)), chunk) for i, chunk in enumerate(chunks))
