# Multi-backend WebP decoding
# 
# Kitty's graphics protocol decodes PNG natively but not WebP, so WebP
# sources are converted transparently at the ImageData layer. This module
# provides a conversion chain that *should* work almost anywhere with
# zero extra dependencies:
# 
#  - Pillow/PIL, if installed with WebP support
#  - libwebp via ctypes, decoding to RGBA, paired with a pure-Python PNG
#    encoder. The system libwebp is present on most Linux/macOS systems
#    as a transitive dependency of common graphics stacks and browsers
#  - sips - the macOS built-in image tool
#  - dwebp - from the system PATH (the "official" WebP tool)
#  - ImageMagick / GraphicsMagick (magick, convert, gm convert)
#  - ffmpeg / avconv
#  - gdk-pixbuf-thumbnailer (GTK/GNOME systems)
# 
# Every backend's output is validated (it must be a valid PNG with the same
# dimensions as the source WebP), so missing tools, or tools built without
# WebP support, are simply skipped. The first backend that produces a valid
# conversion is remembered and preferred for subsequent conversions, but the
# preference is replaced whenever a different backend wins for a particular
# image.
# 
# Environment overrides:
# 
#     NOMADNET_IMAGE_BACKEND   force a specific backend (strict)

import ctypes
import ctypes.util
import hashlib
import io
import os
import shutil
import struct
import subprocess
import tempfile
import zlib

MAX_CACHE_BYTES = 192 * 1024 * 1024
MAX_CACHE_FILES = 512
CONVERSION_TIMEOUT = 5

# libwebp soname candidates, in order of preference.
_LIBWEBP_NAMES = [ "libwebp.so.7",
                   "libwebp.so.6",
                   "libwebp.so.5",
                   "libwebp.so",
                   "libwebp.dylib",
                   "libwebp-7.dll",
                   "libwebp.dll" ]

# The built-in backend chain, in preference order.
BACKENDS = ( "pil",
             "libwebp-ctypes",
             "sips",
             "dwebp",
             "magick",
             "convert",
             "gm",
             "ffmpeg",
             "avconv",
             "gdk-pixbuf" )

_ENV_BACKEND = os.environ.get("NOMADNET_IMAGE_BACKEND")
_winner = None        # name of the currently preferred backend
_last_backend = None  # backend used for the most recent conversion
_convert_count = 0
_cache_hits = 0

_libwebp_cache = {"lib": None, "probed": False}

###############################
# PNG validation and encoding #
###############################

# Returns (width, height) if png is a valid PNG, else None
def _png_dims(png):
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) < 24:
        return None
    if png[12:16] != b"IHDR":
        return None
    width = int.from_bytes(png[16:20], "big")
    height = int.from_bytes(png[20:24], "big")
    if not (width > 0 and height > 0):
        return None
    return (width, height)


# Encodes RGBA pixel data as a PNG (8-bit RGBA, no filtering)
def _encode_png_rgba(rgba, width, height):
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    stride = width * 4
    raw = bytearray(height * (stride + 1))
    pos = 0
    for row in range(height):
        raw[pos] = 0  # filter type: none
        pos += 1
        start = row * stride
        raw[pos:pos + stride] = rgba[start:start + stride]
        pos += stride
    
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
            chunk(b"IEND", b""))


####################
# Conversion cache #
####################

CONV_CACHE_BASE = None
def cache_dir():
    global CONV_CACHE_BASE
    if not CONV_CACHE_BASE:
        from nomadnet.NomadNetworkApp import NomadNetworkApp
        CONV_CACHE_BASE = NomadNetworkApp._shared_instance.dispcachepath
    return CONV_CACHE_BASE

def _cache_path(source_data):
    return os.path.join(cache_dir(), hashlib.sha256(source_data).hexdigest() + ".png")

def _cache_get(source_data):
    try:
        with open(_cache_path(source_data), "rb") as f: png = f.read()
        if _png_dims(png) is not None: return png
    except OSError: pass
    return None

def _cache_put(source_data, png):
    try:
        directory = cache_dir()
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as f: f.write(png)
            os.replace(tmp_path, _cache_path(source_data))
        except OSError:
            try: os.unlink(tmp_path)
            except OSError: pass
        _prune_cache()
    except OSError: pass

# Evicts least-recently-used entries beyond the size/file limits
def _prune_cache():
    try:
        entries = []
        for name in os.listdir(cache_dir()):
            path = os.path.join(cache_dir(), name)
            try:
                st = os.stat(path)
                if st.st_size > 0:
                    entries.append((st.st_mtime, st.st_size, path))
            except OSError: pass

        total = sum(e[1] for e in entries)
        entries.sort()
        while len(entries) > MAX_CACHE_FILES or total > MAX_CACHE_BYTES:
            _, size, path = entries.pop(0)
            total -= size
            try: os.unlink(path)
            except OSError: pass
    except OSError: pass

#######################
# Individual backends #
#######################

# Runs a conversion CLI over temp files
def _run_cli(argv, data):
    if shutil.which(argv[0]) is None: return None
    try:
        with tempfile.TemporaryDirectory(prefix="nomadnet-img-") as td:
            src = os.path.join(td, "source.webp")
            dst = os.path.join(td, "output.png")
            with open(src, "wb") as f: f.write(data)
            args = [a.replace("{src}", src).replace("{dst}", dst) for a in argv]
            subprocess.run(
                args,
                timeout=CONVERSION_TIMEOUT,
                # stdin must be closed: some tools (e.g. ffmpeg) block
                # on inherited stdin otherwise.
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with open(dst, "rb") as f: return f.read()
    except (OSError, subprocess.TimeoutExpired, ValueError): return None

def _backend_pil(data, dims):
    try:
        from PIL import Image
        from PIL import features
        if not features.check("webp"): return None
    except ImportError: return None
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception: return None

# Loads the system libwebp via ctypes, caching the result.
def _get_libwebp():
    if _libwebp_cache["probed"]: return _libwebp_cache["lib"]
    _libwebp_cache["probed"] = True
    lib = None
    names = list(_LIBWEBP_NAMES)
    found = ctypes.util.find_library("webp")
    if found and found not in names: names.insert(0, found)
    for name in names:
        try:
            lib = ctypes.CDLL(name)
            break
        except OSError: continue
    
    if lib is not None:
        lib.WebPGetInfo.restype = ctypes.c_int
        lib.WebPGetInfo.argtypes = [ ctypes.c_char_p, ctypes.c_size_t,
                                     ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int) ]

        lib.WebPDecodeRGBA.restype = ctypes.c_void_p
        lib.WebPDecodeRGBA.argtypes = [ ctypes.c_char_p, ctypes.c_size_t,
                                        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int) ]
        lib.WebPFree.restype = None
        lib.WebPFree.argtypes = [ctypes.c_void_p]

    _libwebp_cache["lib"] = lib
    return lib

def _backend_ctypes(data, dims):
    lib = _get_libwebp()
    if lib is None: return None
    try:
        buf = ctypes.create_string_buffer(data, len(data))
        width = ctypes.c_int(0)
        height = ctypes.c_int(0)
        if not lib.WebPGetInfo(buf, len(data), ctypes.byref(width), ctypes.byref(height)): return None
        if width.value <= 0 or height.value <= 0: return None
        ptr = lib.WebPDecodeRGBA(buf, len(data), ctypes.byref(width), ctypes.byref(height))
        if not ptr: return None
        try: rgba = ctypes.string_at(ptr, width.value * height.value * 4)
        finally: lib.WebPFree(ptr)
        return _encode_png_rgba(rgba, width.value, height.value)
    except Exception: return None

def _backend_gdkpixbuf(data, dims):
    if dims is None: return None
    width, height = dims
    return _run_cli(["gdk-pixbuf-thumbnailer", "-s", "%dx%d" % (width, height), "{src}", "{dst}"], data)

def _backend_sips(data, dims):    return _run_cli(["sips", "-s", "format", "png", "{src}", "--out", "{dst}"], data)
def _backend_dwebp(data, dims):   return _run_cli(["dwebp", "{src}", "-o", "{dst}"], data)
def _backend_magick(data, dims):  return _run_cli(["magick", "{src}", "{dst}"], data)
def _backend_convert(data, dims): return _run_cli(["convert", "{src}", "{dst}"], data)
def _backend_gm(data, dims):      return _run_cli(["gm", "convert", "{src}", "{dst}"], data)
def _backend_ffmpeg(data, dims):  return _run_cli(["ffmpeg", "-y", "-loglevel", "error", "-i", "{src}", "-frames:v", "1", "{dst}"], data)
def _backend_avconv(data, dims):  return _run_cli(["avconv", "-y", "-loglevel", "error", "-i", "{src}", "-frames:v", "1", "{dst}"], data)

_BACKENDS = { "pil": _backend_pil,
              "libwebp-ctypes": _backend_ctypes,
              "sips": _backend_sips,
              "dwebp": _backend_dwebp,
              "magick": _backend_magick,
              "convert": _backend_convert,
              "gm": _backend_gm,
              "ffmpeg": _backend_ffmpeg,
              "avconv": _backend_avconv,
              "gdk-pixbuf": _backend_gdkpixbuf }

#####################
# Conversion driver #
#####################

def _webp_dims(data):
    from ._imagedata import parse_image_header
    try: fmt, width, height = parse_image_header(data)
    except ValueError: return None
    if fmt != "WebP": return None
    return (width, height)

def _backend_order():
    if _ENV_BACKEND: return [_ENV_BACKEND] if _ENV_BACKEND in BACKENDS else []
    order = list(BACKENDS)
    if _winner in order:
        order.remove(_winner)
        order.insert(0, _winner)
    return order

# Converts WebP data to PNG bytes, or None on failure
def convert_webp_to_png(data):
    global _cache_hits
    png = _cache_get(data)
    if png is not None:
        _cache_hits += 1
        return png
    return _convert_uncached(data)

def _convert_uncached(data):
    global _convert_count, _winner, _last_backend
    dims = _webp_dims(data)
    if dims is None: return None
    for name in _backend_order():
        try: png = _BACKENDS[name](data, dims)
        except Exception: png = None
        if png is not None and _png_dims(png) == dims:
            _convert_count += 1
            _last_backend = name
            if not _ENV_BACKEND: _winner = name
            _cache_put(data, png)
            return png

    return None

##################################
# Introspection and test support #
##################################

# Returns [(name, available), ...] for the built-in chain
def available_backends():
    out = []
    for name in BACKENDS:
        if name == "pil":
            try:
                from PIL import features
                out.append((name, bool(features.check("webp"))))
            except Exception: out.append((name, False))
        elif name == "libwebp-ctypes": out.append((name, _get_libwebp() is not None))
        elif name == "gdk-pixbuf":     out.append((name, shutil.which("gdk-pixbuf-thumbnailer") is not None))
        else:                          out.append((name, shutil.which(name) is not None))

    return out

# A diagnostic string describing the conversion setup
def describe():
    if _ENV_BACKEND: return "backend forced via NOMADNET_IMAGE_BACKEND: %s" % _ENV_BACKEND
    present = [name for name, avail in available_backends() if avail]
    if not present: return "no conversion backend available (WebP images will not render)"
    return "backend(s) available: %s; preferred: %s" % (", ".join(present), _last_backend or _winner or "none yet")

# Usage statistics for diagnostics
def stats():
    return { "backend": _last_backend, "conversions": _convert_count,
             "cache_hits": _cache_hits, "cache_dir": cache_dir() }

def last_backend(): return _last_backend

# Forces a specific backend name (testing/debugging); None to clear.
def force_backend(name):
    global _ENV_BACKEND
    _ENV_BACKEND = name if name in BACKENDS else None

# Clears dynamic state (winner, counters); used by tests.
def reset():
    global _winner, _last_backend, _convert_count, _cache_hits
    _winner = None
    _last_backend = None
    _convert_count = 0
    _cache_hits = 0
    _libwebp_cache["lib"] = None
    _libwebp_cache["probed"] = False
