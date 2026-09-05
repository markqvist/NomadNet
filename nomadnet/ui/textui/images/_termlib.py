# Terminal queries for capability detection and layout metrics.
# 
# All values are resolved once and cached; subsequent calls are instant.
# Queries should be performed *before* starting the urwid main loop, because
# they read directly from the terminal and would otherwise race with urwid's
# own input handling. If no terminal is available, or the queries time out,
# sensible fallbacks are used.

import os
import select
import shutil
import sys
import termios
import time

from . import _ctlseqs

QUERY_TIMEOUT = 0.3

kitty_supported = None
cell_size = None

# Last raw terminal query response (bytes), for diagnostics.
last_query_response = bytearray()
last_kitty_response = bytearray()

# Last TIOCGWINSZ buffer (rows, cols, xpixel, ypixel), for diagnostics.
winsize = [0, 0, 0, 0]

# Number of times a query attempt has been made; used to avoid repeated
# slow queries in a broken environment.
_query_failed = False

def _open_tty():
    # Opens the active terminal for reading and writing.
    for stream in ("out", "in", "err"):
        try: return os.open(os.ttyname(getattr(sys, "__std%s__" % stream).fileno()), os.O_RDWR)
        except (OSError, AttributeError): continue
    try: return os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError: return -1


def query_tty(request, timeout=QUERY_TIMEOUT):
    # Sends a query to the terminal and returns the raw response.
    global _query_failed
    if _query_failed: return b""

    fd = _open_tty()
    if fd == -1:
        _query_failed = True
        return b""

    # Never block indefinitely, even on a broken pseudo-terminal,
    # select has a deadline and reads are non-blocking.
    try: os.set_blocking(fd, False)
    except OSError:  pass

    old_attr = termios.tcgetattr(fd)
    new_attr = termios.tcgetattr(fd)
    # Raw-ish mode; disable canonical mode and echo. In canonical mode the
    # terminal buffers input until a newline, which terminal query responses
    # (for example. kitty's "i=31;OK") never contain. The read would block until
    # timeout and the query would always "fail".
    new_attr[3] &= ~(termios.ECHO | termios.ICANON)
    new_attr[6][termios.VMIN] = 0
    new_attr[6][termios.VTIME] = 0
    try:
        # TCSANOW (not TCSAFLUSH): TCSAFLUSH drains the output queue first,
        # which can block indefinitely on some pseudo-terminals.
        termios.tcsetattr(fd, termios.TCSANOW, new_attr)
        try: os.write(fd, request)
        except (BlockingIOError, OSError): return b""
        response = bytearray()
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: break
            try: ready, _, _ = select.select([fd], [], [], remaining)
            except (OSError, ValueError): break
            if not ready: break
            try: chunk = os.read(fd, 4096)
            except (BlockingIOError, OSError): continue
            if not chunk: break
            response += chunk
            if response.endswith(b"\x1b\\") or response.endswith(b"c"): break
        last_query_response[:] = response
        return bytes(response)
    
    finally:
        try: termios.tcsetattr(fd, termios.TCSANOW, old_attr)
        except termios.error: pass
        finally: os.close(fd)

def is_kitty_supported():
    global kitty_supported
    if kitty_supported is None:
        response = query_tty(_ctlseqs.KITTY_QUERY)
        last_kitty_response[:] = response
        kitty_supported = bool(response and _ctlseqs.KITTY_QUERY_RESPONSE_RE.search(response))
    return kitty_supported

def force_kitty_supported(status):
    # Forces the support status (used by tests).
    global kitty_supported
    kitty_supported = bool(status)

def _cell_size_from_winsize(buf):
    # Interprets a TIOCGWINSZ buffer as (cell_width_px, cell_height_px).
    # The struct layout is (rows, cols, xpixel, ypixel). Returns None if the
    # terminal does not report pixel dimensions, or if the result is
    # implausible (e.g. several times wider than tall - a sign of broken
    # winsize reporting).
    rows, cols, xpix, ypix = buf
    if not (cols and rows and xpix and ypix): return None
    cell_w, cell_h = max(1, xpix // cols), max(1, ypix // rows)
    if not (0.1 <= cell_w / cell_h <= 1.5):
        # Real terminal cells should be as wide as, or narrower than,
        # they are tall; anything far outside that range is bogus.
        return None
    return (cell_w, cell_h)

def _query_cell_size():
    # Determines the current cell size in pixels, or None if unknown.
    fd = _open_tty()
    if fd != -1:
        # First, try the TIOCGWINSZ pixel fields (fast, no query)
        import array
        import fcntl
        try:
            buf = array.array("H", [0, 0, 0, 0])
            fcntl.ioctl(fd, termios.TIOCGWINSZ, buf)
            winsize[:] = buf
            cell = _cell_size_from_winsize(buf)
            if cell is not None: return cell
        
        except OSError: pass
        finally: os.close(fd)

    # Fall back to XTWINOPS 16 (cell size in pixels); DA1 is appended to
    # speed up the response (terminals treat queries as FIFO).
    response = query_tty(_ctlseqs.CELL_SIZE_PX + _ctlseqs.DA1)
    if response:
        match = _ctlseqs.CELL_SIZE_RESPONSE_RE.search(response)
        if match: return (int(match.group("w")), int(match.group("h")))
    return None

def get_cell_size():
    # Returns the terminal cell size in pixels as (width, height), or None
    # if it could not be determined.
    global cell_size
    if cell_size is None: cell_size = _query_cell_size()
    return cell_size


def get_terminal_size():
    # Returns the active terminal size as (columns, lines).
    # Uses the tty directly when available (correct even with redirected
    # output), falling back to shutil.get_terminal_size.
    
    fd = _open_tty()
    if fd != -1:
        try:
            size = os.get_terminal_size(fd)
            return (size.columns, size.lines)
        except OSError: pass
        finally: os.close(fd)
    size = shutil.get_terminal_size(fallback=(80, 24))
    return (size.columns, size.lines)

def reset_caches():
    # Clears all cached capability/metric values (used by tests).
    global kitty_supported, cell_size, _query_failed
    kitty_supported = None
    cell_size = None
    _query_failed = False
    last_query_response[:] = b""
    last_kitty_response[:] = b""
    winsize[:] = (0, 0, 0, 0)

def diagnostics():
    # Returns a list of diagnostic strings about the terminal environment,
    # for display/debugging.
    import os
    lines = [ "TERM=%r" % os.environ.get("TERM"),
              "TERM_PROGRAM=%r TERM_PROGRAM_VERSION=%r" % (os.environ.get("TERM_PROGRAM"), os.environ.get("TERM_PROGRAM_VERSION")),
              "kitty graphics protocol supported: %s" % is_kitty_supported(),
              "kitty query response: %r" % bytes(last_kitty_response),
              "cell size (px): %s" % (get_cell_size(),),
              "cell size query response: %r" % bytes(last_query_response),
              "winsize (rows, cols, xpix, ypix): %r" % (tuple(winsize),) ]
    try:
        from . import _webp
        lines.append("webp conversion: %s" % _webp.describe())
    except Exception: pass

    return lines
