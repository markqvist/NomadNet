import sys
import base64
import urwid
import RNS


def osc52_copy(text):
    if not text:
        return False
    try:
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        sys.stdout.write("\x1b]52;c;" + encoded + "\x07")
        sys.stdout.flush()
        return True
    except Exception as e:
        RNS.log("Could not emit clipboard escape sequence: "+str(e), RNS.LOG_ERROR)
        return False


def qr_ascii(data):
    try:
        import qrcode
        import io
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=1, border=1)
        qr.add_data(data)
        qr.make()
        buf = io.StringIO()
        qr.print_ascii(out=buf, invert=False)
        return buf.getvalue().rstrip("\n")
    except Exception as e:
        RNS.log("QR generation failed: "+str(e), RNS.LOG_ERROR)
        return None


class ClickableIcon(urwid.Text):
    _selectable = False

    def __init__(self, text, on_click=None):
        super().__init__(text)
        self._on_click = on_click

    def mouse_event(self, size, event, button, x, y, focus):
        if button == 1 and "press" in event and self._on_click is not None:
            self._on_click()
            return True
        return False
