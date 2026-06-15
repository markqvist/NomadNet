import RNS
import os
import time
import nomadnet
import urwid

from .Transport import TransportDisplay, _get_cols_rows
from .ReadlineEdit import ReadlineEdit
from .FileBrowser import FileBrowser

DEFAULT_PROBE_SIZE = 16
DEFAULT_PROBE_TIMEOUT = 12

def _interface_enabled(iface):
    try:
        return str(iface.get("enabled")).lower() not in ("false", "off", "no", "0") and \
               str(iface.get("interface_enabled")).lower() not in ("false", "off", "no", "0")
    except Exception:
        return True

def _has_active_interfaces(app):
    try:
        interfaces = app.rns.config["interfaces"]
    except Exception:
        return True
    try:
        return any(_interface_enabled(interfaces[name]) for name in interfaces)
    except Exception:
        return True

class UtilityItem(urwid.WidgetWrap):
    def __init__(self, parent, name, description, on_select):
        self.parent = parent
        self.name = name
        self.on_select = on_select
        self._selectable = True

        self.selection_txt = urwid.Text(" ")
        self.title_widget = urwid.Text(("interface_title", name))

        title_row = urwid.Columns([
            (4, self.selection_txt),
            self.title_widget,
        ])
        description_row = urwid.Columns([
            (4, urwid.Text(" ")),
            urwid.Text(("value", description)),
        ])

        box = urwid.LineBox(
            urwid.Padding(urwid.Pile([title_row, description_row]), left=2, right=2),
            title=None,
            tlcorner="╭", tline="─",
            trcorner="╮", lline="│",
            rline="│", blcorner="╰",
            bline="─", brcorner="╯"
        )
        super().__init__(box)

    def selectable(self):
        return True

    def render(self, size, focus=False):
        self.selection_txt.set_text(self.parent.g['selected'] if focus else self.parent.g['unselected'])
        attr = "interface_title_selected" if focus else "interface_title"
        self.title_widget.set_text((attr, self.name))
        return super().render(size, focus=focus)

    def keypress(self, size, key):
        if key == "up":
            if self.parent.landing_listbox.focus_position == 0:
                self.parent.app.ui.main_display.frame.focus_position = "header"
                return None
        elif key == "enter":
            self.on_select()
            return None
        return key

class UtilitiesDisplayShortcuts:
    def __init__(self, app):
        self.app = app
        self.widget = urwid.AttrMap(
            urwid.Text("[Enter] Open  [Up/Down] Navigate"),
            "shortcutbar"
        )

class UtilitiesDisplay:
    def __init__(self, app):
        self.app = app
        self.glyphset = self.app.config["textui"]["glyphs"]
        self.g = self.app.ui.glyphs
        self.active = "landing"
        self.transport = None
        self.probe = None
        self.path = None
        self.identity = None
        self.send = None
        self.speedtest = None

        self.shortcuts_display = UtilitiesDisplayShortcuts(self.app)
        self._build_landing()
        self.widget = self.landing_view

    def _build_landing(self):
        items = [
            UtilityItem(self, "Path Tables", "View routing, announce rate and per-interface tables", self.open_transport),
            UtilityItem(self, "Path Resolver", "Look up or drop the path to a destination", self.open_path),
            UtilityItem(self, "Probe", "Send probes to a destination and measure round trip", self.open_probe),
            UtilityItem(self, "Identity", "Show your addresses and look up a destination's identity", self.open_identity),
            UtilityItem(self, "Send File", "Send a file to a destination over Reticulum to a rncp listener", self.open_send),
            UtilityItem(self, "Speed Test", "Measure throughput to a peer also running this screen", self.open_speedtest),
        ]
        self.landing_listbox = urwid.ListBox(urwid.SimpleFocusListWalker(items))

        _cols, rows = _get_cols_rows()
        box = urwid.BoxAdapter(self.landing_listbox, max(4, rows - 6))

        pile = urwid.Pile([
            ('pack', urwid.Text(("body_text", "Select a utility to open."), align=urwid.CENTER)),
            ('pack', urwid.Divider("─")),
            box,
        ])
        self.landing_view = urwid.Filler(pile, urwid.TOP)

    def shortcuts(self):
        if self.active == "transport" and self.transport is not None:
            return self.transport.shortcuts_display
        if self.active == "probe" and self.probe is not None:
            return self.probe.shortcuts_display
        if self.active == "path" and self.path is not None:
            return self.path.shortcuts_display
        if self.active == "identity" and self.identity is not None:
            return self.identity.shortcuts_display
        if self.active == "send" and self.send is not None:
            return self.send.shortcuts_display
        if self.active == "speedtest" and self.speedtest is not None:
            return self.speedtest.shortcuts_display
        return self.shortcuts_display

    def _leave_speedtest(self):
        if self.speedtest is not None and self.active == "speedtest":
            self.speedtest.stop_listening()

    def start(self):
        self.show_landing()

    def show_landing(self):
        self._leave_speedtest()
        self.active = "landing"
        self.widget = self.landing_view
        self.app.ui.main_display.update_active_sub_display()
        self.app.ui.main_display.frame.focus_position = "body"

    def open_transport(self):
        if self.transport is None:
            self.transport = TransportDisplay(self.app, parent=self)
        self.active = "transport"
        self.widget = self.transport.widget
        self.app.ui.main_display.update_active_sub_display()
        self.app.ui.main_display.frame.focus_position = "body"
        self.transport.start()

    def open_probe(self):
        if self.probe is None:
            self.probe = ProbeView(self.app, parent=self)
        self.probe.update_interface_status()
        self.active = "probe"
        self.widget = self.probe.widget
        self.app.ui.main_display.update_active_sub_display()
        self.app.ui.main_display.frame.focus_position = "body"

    def open_path(self):
        if self.path is None:
            self.path = PathView(self.app, parent=self)
        self.path.update_interface_status()
        self.active = "path"
        self.widget = self.path.widget
        self.app.ui.main_display.update_active_sub_display()
        self.app.ui.main_display.frame.focus_position = "body"

    def open_identity(self):
        if self.identity is None:
            self.identity = IdentityView(self.app, parent=self)
        self.active = "identity"
        self.widget = self.identity.widget
        self.app.ui.main_display.update_active_sub_display()
        self.app.ui.main_display.frame.focus_position = "body"

    def open_send(self):
        if self.send is None:
            self.send = SendFileView(self.app, parent=self)
        self.send.update_interface_status()
        self.active = "send"
        self.widget = self.send.widget
        self.app.ui.main_display.update_active_sub_display()
        self.app.ui.main_display.frame.focus_position = "body"

    def open_speedtest(self):
        if self.speedtest is None:
            self.speedtest = SpeedTestView(self.app, parent=self)
        self.active = "speedtest"
        self.widget = self.speedtest.widget
        self.app.ui.main_display.update_active_sub_display()
        self.app.ui.main_display.frame.focus_position = "body"
        self.speedtest.update_interface_status()
        self.speedtest.start_listening()

class ProbeShortcuts:
    def __init__(self, app):
        self.app = app
        self.widget = urwid.AttrMap(
            urwid.Text("[Up/Down] Navigate  [Enter] Probe / Activate  [Esc] Back"),
            "shortcutbar"
        )

class UtilityViewFiller(urwid.WidgetWrap):
    def __init__(self, body, view):
        self.view = view
        super().__init__(body)

    def keypress(self, size, key):
        if key == "esc":
            self.view.go_back()
            return None
        result = super().keypress(size, key)
        if key == "up" and result == "up":
            self.view.go_back_to_header()
            return None
        return result

class ProbeView:
    def __init__(self, app, parent=None):
        self.app = app
        self.parent = parent
        self.glyphset = self.app.config["textui"]["glyphs"]
        self.g = self.app.ui.glyphs

        self.shortcuts_display = ProbeShortcuts(self.app)

        self._probing = False
        self._concluded = False
        self._remaining = 0
        self._sent = 0
        self._replies = 0
        self._cur_receipt = None

        self.name_edit = ReadlineEdit("", "rnstransport.probe")
        self.hash_edit = ReadlineEdit("", "")
        self.size_edit = ReadlineEdit("", str(DEFAULT_PROBE_SIZE))
        self.count_edit = ReadlineEdit("", "1")

        self.probe_button = urwid.AttrMap(urwid.Button("Probe", on_press=self.on_probe), "button_normal", focus_map="button_focus")
        self.back_button = urwid.AttrMap(urwid.Button("Back", on_press=lambda b: self.go_back()), "button_normal", focus_map="button_focus")
        button_row = urwid.Columns([
            (urwid.WEIGHT, 0.45, self.probe_button),
            (urwid.WEIGHT, 0.1, urwid.Text("")),
            (urwid.WEIGHT, 0.45, self.back_button),
        ])

        self.status_text = urwid.Text("")

        rows = [
            urwid.Text(("form_title", "Probe a destination"), align=urwid.CENTER),
            urwid.Divider("─"),
            self.status_text,
            self._field_row("Destination name:", self.name_edit),
            urwid.Padding(urwid.Text(("inactive_text", "Full dotted name for example rnstransport.probe")), left=22),
            self._field_row("Destination hash:", self.hash_edit),
            self._field_row("Payload size:", self.size_edit),
            self._field_row("Probe count:", self.count_edit),
            urwid.Divider(),
            button_row,
            urwid.Divider("─"),
            urwid.Text(("key", "Output")),
        ]
        self.walker = urwid.SimpleFocusListWalker(rows)
        self.listbox = urwid.ListBox(self.walker)
        self.widget = UtilityViewFiller(self.listbox, self)
        self.update_interface_status()

    def _field_row(self, label, edit):
        return urwid.Columns([
            (20, urwid.Text(("key", label), align=urwid.RIGHT)),
            urwid.AttrMap(edit, "list_normal", focus_map="list_focus"),
        ], dividechars=1)

    def update_interface_status(self):
        if _has_active_interfaces(self.app):
            self.status_text.set_text("")
        else:
            self.status_text.set_text(("warning_text", "(!) No interfaces are active"))

    def go_back(self):
        if self.parent is not None:
            self.parent.show_landing()

    def go_back_to_header(self):
        try:
            self.app.ui.main_display.frame.focus_position = "header"
        except Exception:
            pass

    def _log(self, message, attr="body_text"):
        self.walker.append(urwid.Text((attr, message)))
        try:
            self.listbox.set_focus(len(self.walker) - 1)
        except Exception:
            pass

    def _draw(self):
        try:
            self.app.ui.loop.draw_screen()
        except Exception:
            pass

    def _schedule(self, fn):
        try:
            self.app.ui.loop.set_alarm_in(0, lambda *a: (fn(), self._draw()))
        except Exception:
            try:
                fn()
            except Exception:
                pass

    def on_probe(self, button=None):
        if self._probing:
            return

        self.update_interface_status()

        full_name = self.name_edit.edit_text.strip()
        hexhash = self.hash_edit.edit_text.strip()

        if not full_name:
            self._log("Enter a destination name (e.g. rnstransport.probe)", "error_text")
            return

        try:
            app_name, aspects = RNS.Destination.app_and_aspects_from_name(full_name)
        except Exception as e:
            self._log("Invalid destination name: %s" % str(e), "error_text")
            return

        dest_len = (RNS.Reticulum.TRUNCATED_HASHLENGTH // 8) * 2
        if len(hexhash) != dest_len:
            self._log("Destination hash must be %d hex characters" % dest_len, "error_text")
            return
        try:
            destination_hash = bytes.fromhex(hexhash)
        except Exception:
            self._log("Invalid destination hash", "error_text")
            return

        try:
            size = int(self.size_edit.edit_text.strip() or str(DEFAULT_PROBE_SIZE))
        except ValueError:
            size = DEFAULT_PROBE_SIZE
        try:
            count = int(self.count_edit.edit_text.strip() or "1")
        except ValueError:
            count = 1
        if count < 1:
            count = 1

        self._app_name = app_name
        self._aspects = aspects
        self._dest_hash = destination_hash
        self._size = max(1, size)
        self._remaining = count
        self._sent = 0
        self._replies = 0
        self._probing = True
        self.probe_button.original_widget.set_label("Probing…")
        self._begin_probe()

    def _begin_probe(self):
        dest_hash = self._dest_hash
        if not RNS.Transport.has_path(dest_hash):
            try:
                RNS.Transport.request_path(dest_hash)
            except Exception:
                pass
            self._log("Requesting path to %s …" % RNS.prettyhexrep(dest_hash))
            self._path_deadline = time.time() + self._timeout()
            self.app.ui.loop.set_alarm_in(0.25, self._await_path)
        else:
            self._send_one()

    def _timeout(self):
        try:
            return DEFAULT_PROBE_TIMEOUT + self.app.rns.get_first_hop_timeout(self._dest_hash)
        except Exception:
            return DEFAULT_PROBE_TIMEOUT

    def _await_path(self, loop, user_data):
        if RNS.Transport.has_path(self._dest_hash):
            self._send_one()
        elif time.time() > self._path_deadline:
            self._log("Path request timed out", "warning_text")
            self._finish()
        else:
            loop.set_alarm_in(0.25, self._await_path)

    def _send_one(self):
        dest_hash = self._dest_hash
        identity = RNS.Identity.recall(dest_hash)
        if identity is None:
            self._log("Could not recall identity for destination", "error_text")
            self._finish()
            return

        try:
            request_destination = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, self._app_name, *self._aspects)
            probe = RNS.Packet(request_destination, os.urandom(self._size))
            probe.pack()
        except OSError:
            self._log("Probe payload of %d bytes exceeds the MTU" % self._size, "error_text")
            self._finish()
            return
        except Exception as e:
            self._log("Could not create probe: %s" % str(e), "error_text")
            self._finish()
            return

        self._concluded = False
        receipt = probe.send()
        self._cur_receipt = receipt
        self._sent += 1
        self._log("Sent probe %d (%d bytes) to %s …" % (self._sent, self._size, RNS.prettyhexrep(dest_hash)))

        try:
            receipt.set_delivery_callback(self._on_delivered)
        except Exception:
            pass
        self.app.ui.loop.set_alarm_in(self._timeout(), self._on_timeout)

    def _on_delivered(self, receipt):
        self._schedule(lambda: self._conclude(receipt, True))

    def _on_timeout(self, loop, user_data):
        self._conclude(self._cur_receipt, False)

    def _conclude(self, receipt, delivered):
        if self._concluded:
            return
        self._concluded = True

        is_delivered = delivered
        if not is_delivered and receipt is not None:
            try:
                is_delivered = receipt.status == RNS.PacketReceipt.DELIVERED
            except Exception:
                is_delivered = False

        if is_delivered and receipt is not None:
            self._replies += 1
            try:
                hops = RNS.Transport.hops_to(self._dest_hash)
            except Exception:
                hops = 0
            try:
                rtt = receipt.get_rtt()
                rtt_str = "%.0f ms" % (rtt * 1000) if rtt < 1 else "%.3f s" % rtt
            except Exception:
                rtt_str = "?"
            hop_str = "%d hop%s" % (hops, "" if hops == 1 else "s")
            self._log("Reply from %s %s over %s%s" % (
                RNS.prettyhexrep(receipt.destination.hash), rtt_str, hop_str, self._reception_stats(receipt)),
                "connected_status")
        else:
            self._log("Probe %d timed out" % self._sent, "warning_text")

        self._next()

    def _reception_stats(self, receipt):
        stats = ""
        try:
            proof_packet = getattr(receipt, "proof_packet", None)
            if proof_packet is None:
                return ""
            if getattr(self.app.rns, "is_connected_to_shared_instance", False):
                packet_hash = proof_packet.packet_hash
                rssi = self.app.rns.get_packet_rssi(packet_hash)
                snr = self.app.rns.get_packet_snr(packet_hash)
                q = self.app.rns.get_packet_q(packet_hash)
            else:
                rssi = getattr(proof_packet, "rssi", None)
                snr = getattr(proof_packet, "snr", None)
                q = None
            if rssi is not None:
                stats += " [RSSI %s dBm]" % rssi
            if snr is not None:
                stats += " [SNR %s dB]" % snr
            if q is not None:
                stats += " [Q %s%%]" % q
        except Exception:
            pass
        return stats

    def _next(self):
        self._remaining -= 1
        if self._remaining > 0:
            self._send_one()
        else:
            self._finish()

    def _finish(self):
        if self._sent > 0:
            loss = round((1 - (self._replies / self._sent)) * 100, 1)
            self._log("Sent %d, received %d, packet loss %s%%" % (self._sent, self._replies, loss), "key")
        self._probing = False
        self.probe_button.original_widget.set_label("Probe")
        self._draw()

class PathShortcuts:
    def __init__(self, app):
        self.app = app
        self.widget = urwid.AttrMap(
            urwid.Text("[Up/Down] Navigate  [Enter] Resolve / Activate  [Esc] Back"),
            "shortcutbar"
        )

class PathView:
    def __init__(self, app, parent=None):
        self.app = app
        self.parent = parent
        self.glyphset = self.app.config["textui"]["glyphs"]
        self.g = self.app.ui.glyphs

        self.shortcuts_display = PathShortcuts(self.app)

        self._resolving = False

        self.hash_edit = ReadlineEdit("", "")

        self.resolve_button = urwid.AttrMap(urwid.Button("Resolve", on_press=self.on_resolve), "button_normal", focus_map="button_focus")
        self.drop_button = urwid.AttrMap(urwid.Button("Drop path", on_press=self.on_drop), "button_normal", focus_map="button_focus")
        self.back_button = urwid.AttrMap(urwid.Button("Back", on_press=lambda b: self.go_back()), "button_normal", focus_map="button_focus")
        button_row = urwid.Columns([
            (urwid.WEIGHT, 0.3, self.resolve_button),
            (urwid.WEIGHT, 0.05, urwid.Text("")),
            (urwid.WEIGHT, 0.3, self.drop_button),
            (urwid.WEIGHT, 0.05, urwid.Text("")),
            (urwid.WEIGHT, 0.3, self.back_button),
        ])

        self.status_text = urwid.Text("")

        rows = [
            urwid.Text(("form_title", "Resolve a path"), align=urwid.CENTER),
            urwid.Divider("─"),
            self.status_text,
            urwid.Columns([
                (20, urwid.Text(("key", "Destination hash:"), align=urwid.RIGHT)),
                urwid.AttrMap(self.hash_edit, "list_normal", focus_map="list_focus"),
            ], dividechars=1),
            urwid.Padding(urwid.Text(("inactive_text", "Requests the path from the network if it is not already known.")), left=22),
            urwid.Divider(),
            button_row,
            urwid.Divider("─"),
            urwid.Text(("key", "Output")),
        ]
        self.walker = urwid.SimpleFocusListWalker(rows)
        self.listbox = urwid.ListBox(self.walker)
        self.widget = UtilityViewFiller(self.listbox, self)
        self.update_interface_status()

    def update_interface_status(self):
        if _has_active_interfaces(self.app):
            self.status_text.set_text("")
        else:
            self.status_text.set_text(("warning_text", "(!) No interfaces are active"))

    def go_back(self):
        if self.parent is not None:
            self.parent.show_landing()

    def go_back_to_header(self):
        try:
            self.app.ui.main_display.frame.focus_position = "header"
        except Exception:
            pass

    def _log(self, message, attr="body_text"):
        self.walker.append(urwid.Text((attr, message)))
        try:
            self.listbox.set_focus(len(self.walker) - 1)
        except Exception:
            pass

    def _draw(self):
        try:
            self.app.ui.loop.draw_screen()
        except Exception:
            pass

    def _validate_hash(self):
        hexhash = self.hash_edit.edit_text.strip()
        dest_len = (RNS.Reticulum.TRUNCATED_HASHLENGTH // 8) * 2
        if len(hexhash) != dest_len:
            self._log("Destination hash must be %d hex characters" % dest_len, "error_text")
            return None
        try:
            return bytes.fromhex(hexhash)
        except Exception:
            self._log("Invalid destination hash", "error_text")
            return None

    def _timeout(self):
        try:
            return DEFAULT_PROBE_TIMEOUT + self.app.rns.get_first_hop_timeout(self._dest_hash)
        except Exception:
            return DEFAULT_PROBE_TIMEOUT

    def on_resolve(self, button=None):
        if self._resolving:
            return
        self.update_interface_status()
        dest_hash = self._validate_hash()
        if dest_hash is None:
            return
        self._dest_hash = dest_hash
        if RNS.Transport.has_path(dest_hash):
            self._show_path()
            return
        try:
            RNS.Transport.request_path(dest_hash)
        except Exception:
            pass
        self._resolving = True
        self.resolve_button.original_widget.set_label("Resolving…")
        self._log("Requesting path to %s …" % RNS.prettyhexrep(dest_hash))
        self._deadline = time.time() + self._timeout()
        self.app.ui.loop.set_alarm_in(0.25, self._await_path)

    def _await_path(self, loop, user_data):
        if RNS.Transport.has_path(self._dest_hash):
            self._resolving = False
            self.resolve_button.original_widget.set_label("Resolve")
            self._show_path()
            self._draw()
        elif time.time() > self._deadline:
            self._resolving = False
            self.resolve_button.original_widget.set_label("Resolve")
            self._log("Path not found", "warning_text")
            self._draw()
        else:
            loop.set_alarm_in(0.25, self._await_path)

    def _show_path(self):
        dest_hash = self._dest_hash
        try:
            hops = RNS.Transport.hops_to(dest_hash)
            next_hop_bytes = self.app.rns.get_next_hop(dest_hash)
        except Exception:
            next_hop_bytes = None
            hops = 0
        if not next_hop_bytes:
            self._log("Path data unavailable", "warning_text")
            return
        try:
            interface = self.app.rns.get_next_hop_if_name(dest_hash)
        except Exception:
            interface = "?"
        hop_str = "%d hop%s" % (hops, "" if hops == 1 else "s")
        self._log("Path found: %s is %s away via %s on %s" % (
            RNS.prettyhexrep(dest_hash), hop_str, RNS.prettyhexrep(next_hop_bytes), interface),
            "connected_status")

    def on_drop(self, button=None):
        dest_hash = self._validate_hash()
        if dest_hash is None:
            return
        try:
            dropped = self.app.rns.drop_path(dest_hash)
        except Exception as e:
            self._log("Could not drop path: %s" % str(e), "error_text")
            return
        if dropped:
            self._log("Dropped path to %s" % RNS.prettyhexrep(dest_hash))
        else:
            self._log("No path to %s to drop" % RNS.prettyhexrep(dest_hash), "warning_text")

class IdentityShortcuts:
    def __init__(self, app):
        self.app = app
        self.widget = urwid.AttrMap(
            urwid.Text("[Up/Down] Navigate  [Enter] Look up / Activate  [Esc] Back"),
            "shortcutbar"
        )

class IdentityView:
    def __init__(self, app, parent=None):
        self.app = app
        self.parent = parent
        self.glyphset = self.app.config["textui"]["glyphs"]
        self.g = self.app.ui.glyphs
        self.shortcuts_display = IdentityShortcuts(self.app)
        self._resolving = False

        self.hash_edit = ReadlineEdit("", "")
        self.lookup_button = urwid.AttrMap(urwid.Button("Look up", on_press=self.on_lookup), "button_normal", focus_map="button_focus")
        self.back_button = urwid.AttrMap(urwid.Button("Back", on_press=lambda b: self.go_back()), "button_normal", focus_map="button_focus")
        button_row = urwid.Columns([
            (urwid.WEIGHT, 0.45, self.lookup_button),
            (urwid.WEIGHT, 0.1, urwid.Text("")),
            (urwid.WEIGHT, 0.45, self.back_button),
        ])

        rows = [
            urwid.Text(("form_title", "Identity"), align=urwid.CENTER),
            urwid.Divider("─"),
            urwid.Text(("key", "Your addresses")),
        ]
        rows += self._address_rows()
        rows += [
            urwid.Divider(),
            urwid.Text(("key", "Look up a destination")),
            urwid.Columns([
                (20, urwid.Text(("key", "Destination hash:"), align=urwid.RIGHT)),
                urwid.AttrMap(self.hash_edit, "list_normal", focus_map="list_focus"),
            ], dividechars=1),
            urwid.Padding(urwid.Text(("inactive_text", "Recalls the identity, requesting it from the network if needed.")), left=22),
            urwid.Divider(),
            button_row,
            urwid.Divider("─"),
            urwid.Text(("key", "Output")),
        ]
        self.walker = urwid.SimpleFocusListWalker(rows)
        self.listbox = urwid.ListBox(self.walker)
        self.widget = UtilityViewFiller(self.listbox, self)

    def _addr(self, obj):
        try:
            return RNS.prettyhexrep(obj.hash) if obj is not None else ""
        except Exception:
            return ""

    def _address_rows(self):
        rows = []

        def row(label, value):
            return urwid.Columns([
                (18, urwid.Text(("key", label), align=urwid.RIGHT)),
                urwid.Text(("value", value)),
            ], dividechars=1)

        rows.append(row("Identity:", self._addr(getattr(self.app, "identity", None))))
        rows.append(row("LXMF address:", self._addr(getattr(self.app, "lxmf_destination", None))))
        node = getattr(self.app, "node", None)
        if node is not None:
            rows.append(row("Node:", self._addr(getattr(node, "destination", None))))
        return rows

    def go_back(self):
        if self.parent is not None:
            self.parent.show_landing()

    def go_back_to_header(self):
        try:
            self.app.ui.main_display.frame.focus_position = "header"
        except Exception:
            pass

    def _log(self, message, attr="body_text"):
        self.walker.append(urwid.Text((attr, message)))
        try:
            self.listbox.set_focus(len(self.walker) - 1)
        except Exception:
            pass

    def _draw(self):
        try:
            self.app.ui.loop.draw_screen()
        except Exception:
            pass

    def on_lookup(self, button=None):
        if self._resolving:
            return
        hexhash = self.hash_edit.edit_text.strip()
        dest_len = (RNS.Reticulum.TRUNCATED_HASHLENGTH // 8) * 2
        if len(hexhash) != dest_len:
            self._log("Destination hash must be %d hex characters" % dest_len, "error_text")
            return
        try:
            dest_hash = bytes.fromhex(hexhash)
        except Exception:
            self._log("Invalid destination hash", "error_text")
            return

        self._dest_hash = dest_hash
        identity = RNS.Identity.recall(dest_hash)
        if identity is not None:
            self._show_identity(identity)
            return

        try:
            RNS.Transport.request_path(dest_hash)
        except Exception:
            pass
        self._resolving = True
        self.lookup_button.original_widget.set_label("Looking up…")
        self._log("Identity unknown, requesting from the network …")
        try:
            self._deadline = time.time() + DEFAULT_PROBE_TIMEOUT + self.app.rns.get_first_hop_timeout(dest_hash)
        except Exception:
            self._deadline = time.time() + DEFAULT_PROBE_TIMEOUT
        self.app.ui.loop.set_alarm_in(0.25, self._await_identity)

    def _await_identity(self, loop, user_data):
        identity = RNS.Identity.recall(self._dest_hash)
        if identity is not None:
            self._resolving = False
            self.lookup_button.original_widget.set_label("Look up")
            self._show_identity(identity)
            self._draw()
        elif time.time() > self._deadline:
            self._resolving = False
            self.lookup_button.original_widget.set_label("Look up")
            self._log("Identity not found", "warning_text")
            self._draw()
        else:
            loop.set_alarm_in(0.25, self._await_identity)

    def _show_identity(self, identity):
        self._log("kno wn %s resolves to identity %s" % (
            RNS.prettyhexrep(self._dest_hash), RNS.prettyhexrep(identity.hash)), "connected_status")

RNCP_APP_NAME = "rncp"

class SendFileShortcuts:
    def __init__(self, app):
        self.app = app
        self.widget = urwid.AttrMap(
            urwid.Text("[Up/Down] Navigate  [Enter] Choose / Send  [Esc] Back"),
            "shortcutbar"
        )

class SendFileView:
    def __init__(self, app, parent=None):
        self.app = app
        self.parent = parent
        self.glyphset = self.app.config["textui"]["glyphs"]
        self.g = self.app.ui.glyphs
        self.shortcuts_display = SendFileShortcuts(self.app)

        self._sending = False
        self._concluded = False
        self._link = None
        self._resource = None
        self.file_path = None

        self.hash_edit = ReadlineEdit("", "")
        self.file_label = urwid.Text(("inactive_text", "No file selected"))
        self.status_text = urwid.Text("")
        self.progress_text = urwid.Text("")

        self.choose_button = urwid.AttrMap(urwid.Button("Choose file…", on_press=self.choose_file), "button_normal", focus_map="button_focus")
        self.send_button = urwid.AttrMap(urwid.Button("Send", on_press=self.on_send), "button_normal", focus_map="button_focus")
        self.back_button = urwid.AttrMap(urwid.Button("Back", on_press=lambda b: self.go_back()), "button_normal", focus_map="button_focus")
        button_row = urwid.Columns([
            (urwid.WEIGHT, 0.45, self.send_button),
            (urwid.WEIGHT, 0.1, urwid.Text("")),
            (urwid.WEIGHT, 0.45, self.back_button),
        ])

        rows = [
            urwid.Text(("form_title", "Send a file"), align=urwid.CENTER),
            urwid.Divider("─"),
            self.status_text,
            urwid.Columns([
                (20, urwid.Text(("key", "File:"), align=urwid.RIGHT)),
                urwid.AttrMap(self.choose_button, "button_normal", focus_map="button_focus"),
            ], dividechars=1),
            urwid.Padding(self.file_label, left=22),
            urwid.Columns([
                (20, urwid.Text(("key", "Destination hash:"), align=urwid.RIGHT)),
                urwid.AttrMap(self.hash_edit, "list_normal", focus_map="list_focus"),
            ], dividechars=1),
            urwid.Padding(urwid.Text(("inactive_text", "The receiver must be running 'rncp --listen' and have your identity hash in the allow list.")), left=22),
            urwid.Divider(),
            button_row,
            urwid.Divider("─"),
            self.progress_text,
            urwid.Text(("key", "Output")),
        ]
        self.walker = urwid.SimpleFocusListWalker(rows)
        self.listbox = urwid.ListBox(self.walker)
        self.widget = UtilityViewFiller(self.listbox, self)
        self.update_interface_status()

    def update_interface_status(self):
        if _has_active_interfaces(self.app):
            self.status_text.set_text("")
        else:
            self.status_text.set_text(("warning_text", "(!) No interfaces are active"))

    def go_back(self):
        if self.parent is not None:
            self.parent.show_landing()

    def go_back_to_header(self):
        try:
            self.app.ui.main_display.frame.focus_position = "header"
        except Exception:
            pass

    def _log(self, message, attr="body_text"):
        self.walker.append(urwid.Text((attr, message)))
        try:
            self.listbox.set_focus(len(self.walker) - 1)
        except Exception:
            pass

    def _draw(self):
        try:
            self.app.ui.loop.draw_screen()
        except Exception:
            pass

    def _schedule(self, fn):
        try:
            self.app.ui.loop.set_alarm_in(0, lambda *a: (fn(), self._draw()))
        except Exception:
            try:
                fn()
            except Exception:
                pass

    def choose_file(self, button=None):
        def on_done(selected):
            if selected:
                self.file_path = selected[0]
                self.file_label.set_text(("value", os.path.basename(self.file_path)))
            self._close_browser()

        def on_cancel():
            self._close_browser()

        browser = FileBrowser(on_done=on_done, on_cancel=on_cancel, title="Select File to Send", multi_select=False)
        overlay = urwid.Overlay(browser, self.widget, align=urwid.CENTER, width=("relative", 90), valign=urwid.MIDDLE, height=("relative", 80), left=2, right=2)
        self.parent.widget = overlay
        self.app.ui.main_display.update_active_sub_display()
        self.app.ui.main_display.frame.focus_position = "body"

    def _close_browser(self):
        self.parent.widget = self.widget
        self.app.ui.main_display.update_active_sub_display()
        self.app.ui.main_display.frame.focus_position = "body"
        self._draw()

    def _timeout(self):
        try:
            return DEFAULT_PROBE_TIMEOUT + self.app.rns.get_first_hop_timeout(self._dest_hash)
        except Exception:
            return DEFAULT_PROBE_TIMEOUT

    def on_send(self, button=None):
        if self._sending:
            return
        self.update_interface_status()

        if not self.file_path or not os.path.isfile(self.file_path):
            self._log("Choose a file to send first", "error_text")
            return

        hexhash = self.hash_edit.edit_text.strip()
        dest_len = (RNS.Reticulum.TRUNCATED_HASHLENGTH // 8) * 2
        if len(hexhash) != dest_len:
            self._log("Destination hash must be %d hex characters" % dest_len, "error_text")
            return
        try:
            dest_hash = bytes.fromhex(hexhash)
        except Exception:
            self._log("Invalid destination hash", "error_text")
            return

        self._dest_hash = dest_hash
        self._sending = True
        self._concluded = False
        self._resource = None
        self.send_button.original_widget.set_label("Sending…")
        self.progress_text.set_text("")

        if RNS.Transport.has_path(dest_hash):
            self._establish_link()
        else:
            try:
                RNS.Transport.request_path(dest_hash)
            except Exception:
                pass
            self._log("Requesting path to %s …" % RNS.prettyhexrep(dest_hash))
            self._deadline = time.time() + self._timeout()
            self.app.ui.loop.set_alarm_in(0.25, self._await_path)

    def _await_path(self, loop, user_data):
        if RNS.Transport.has_path(self._dest_hash):
            self._establish_link()
        elif time.time() > self._deadline:
            self._log("Path not found", "warning_text")
            self._finish()
        else:
            loop.set_alarm_in(0.25, self._await_path)

    def _establish_link(self):
        identity = RNS.Identity.recall(self._dest_hash)
        if identity is None:
            self._log("Could not recall identity for destination", "error_text")
            self._finish()
            return
        try:
            destination = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, RNCP_APP_NAME, "receive")
            self._log("Establishing link with %s …" % RNS.prettyhexrep(self._dest_hash))
            self._link = RNS.Link(destination, established_callback=self._on_link_up, closed_callback=self._on_link_closed)
        except Exception as e:
            self._log("Could not establish link: %s" % str(e), "error_text")
            self._finish()
            return
        self._link_deadline = time.time() + self._timeout()
        self.app.ui.loop.set_alarm_in(0.5, self._check_link)

    def _check_link(self, loop, user_data):
        if not self._sending or self._resource is not None:
            return
        try:
            active = self._link is not None and self._link.status == RNS.Link.ACTIVE
        except Exception:
            active = False
        if active:
            return
        if time.time() > self._link_deadline:
            self._log("Link establishment timed out", "warning_text")
            try:
                self._link.teardown()
            except Exception:
                pass
            self._finish()
        else:
            loop.set_alarm_in(0.5, self._check_link)

    def _on_link_up(self, link):
        self._schedule(lambda: self._start_resource(link))

    def _start_resource(self, link):
        if not self._sending or self._resource is not None:
            return
        try:
            link.identify(self.app.identity)
            metadata = {"name": os.path.basename(self.file_path).encode("utf-8")}
            self._resource = RNS.Resource(open(self.file_path, "rb"), link, metadata=metadata,
                                          callback=self._on_resource_done, progress_callback=self._on_progress, auto_compress=True)
            self._log("Advertising %s …" % os.path.basename(self.file_path))
        except Exception as e:
            self._log("Could not start transfer: %s" % str(e), "error_text")
            self._finish()

    def _on_progress(self, resource):
        self._schedule(lambda: self._show_progress(resource))

    def _show_progress(self, resource):
        try:
            pct = int(resource.get_progress() * 100)
        except Exception:
            pct = 0
        self.progress_text.set_text(("body_text", "Transferring… %d%%" % pct))

    def _on_resource_done(self, resource):
        self._schedule(lambda: self._resource_done(resource))

    def _resource_done(self, resource):
        if self._concluded:
            return
        self._concluded = True
        try:
            complete = resource.status == RNS.Resource.COMPLETE
        except Exception:
            complete = False
        if complete:
            self.progress_text.set_text(("connected_status", "Transferring… 100%"))
            self._log("Transfer complete", "connected_status")
        else:
            self._log("Transfer failed or the file was not accepted ,", "warning_text")
        try:
            if self._link is not None:
                self._link.teardown()
        except Exception:
            pass
        self._finish()

    def _on_link_closed(self, link):
        self._schedule(self._link_closed)

    def _link_closed(self):
        if self._sending and self._resource is None and not self._concluded:
            self._log("Link closed before the transfer started", "warning_text")
            self._finish()

    def _finish(self):
        self._sending = False
        self.send_button.original_widget.set_label("Send")
        self._draw()

SPEEDTEST_APP_NAME = "nomadnetwork"
SPEEDTEST_ASPECTS = ("utilities", "speedtest")
DEFAULT_SPEEDTEST_MB = 1
MAX_SPEEDTEST_MB = 50

def _fmt_bitrate(bytes_per_sec):
    bits = float(bytes_per_sec) * 8
    for unit in ("bps", "Kbps", "Mbps", "Gbps"):
        if bits < 1000:
            return "%.1f %s" % (bits, unit)
        bits /= 1000
    return "%.1f Tbps" % bits

class SpeedTestShortcuts:
    def __init__(self, app):
        self.app = app
        self.widget = urwid.AttrMap(
            urwid.Text("[Up/Down] Navigate  [Enter] Start / Activate  [Esc] Back"),
            "shortcutbar"
        )

class SpeedTestView:
    def __init__(self, app, parent=None):
        self.app = app
        self.parent = parent
        self.glyphset = self.app.config["textui"]["glyphs"]
        self.g = self.app.ui.glyphs
        self.shortcuts_display = SpeedTestShortcuts(self.app)

        self.server_destination = None
        self._listening = False
        self._incoming_link = None
        self._recv_link = None
        self._recv_started = None
        self._recv_bytes = 0

        self._sending = False
        self._client_link = None
        self._client_resource = None
        self._send_started = None
        self._send_bytes = 0

        self.hash_edit = ReadlineEdit("", "")
        self.size_edit = ReadlineEdit("", str(DEFAULT_SPEEDTEST_MB))
        self.address_text = urwid.Text(("value", "—"))
        self.status_text = urwid.Text("")
        self.progress_text = urwid.Text("")

        self.start_button = urwid.AttrMap(urwid.Button("Start test", on_press=self.on_start), "button_normal", focus_map="button_focus")
        self.back_button = urwid.AttrMap(urwid.Button("Back", on_press=lambda b: self.go_back()), "button_normal", focus_map="button_focus")
        button_row = urwid.Columns([
            (urwid.WEIGHT, 0.45, self.start_button),
            (urwid.WEIGHT, 0.1, urwid.Text("")),
            (urwid.WEIGHT, 0.45, self.back_button),
        ])

        rows = [
            urwid.Text(("form_title", "Speed test"), align=urwid.CENTER),
            urwid.Divider("─"),
            self.status_text,
            urwid.Columns([
                (22, urwid.Text(("key", "Your speedtest hash:"), align=urwid.RIGHT)),
                self.address_text,
            ], dividechars=1),
            urwid.Padding(urwid.Text(("inactive_text", "Both sides open this screen and enter each other's hash; then one presses Start.")), left=24),
            urwid.Columns([
                (22, urwid.Text(("key", "Peer hash:"), align=urwid.RIGHT)),
                urwid.AttrMap(self.hash_edit, "list_normal", focus_map="list_focus"),
            ], dividechars=1),
            urwid.Columns([
                (22, urwid.Text(("key", "Test size (MB):"), align=urwid.RIGHT)),
                urwid.AttrMap(self.size_edit, "list_normal", focus_map="list_focus"),
            ], dividechars=1),
            urwid.Divider(),
            button_row,
            urwid.Divider("─"),
            self.progress_text,
            urwid.Text(("key", "Output")),
        ]
        self.walker = urwid.SimpleFocusListWalker(rows)
        self.listbox = urwid.ListBox(self.walker)
        self.widget = UtilityViewFiller(self.listbox, self)

    def update_interface_status(self):
        if _has_active_interfaces(self.app):
            self.status_text.set_text("")
        else:
            self.status_text.set_text(("warning_text", "(!) No interfaces are active"))

    def _update_address(self):
        if self.server_destination is not None:
            self.address_text.set_text(("value", RNS.prettyhexrep(self.server_destination.hash)))
        else:
            self.address_text.set_text(("value", "—"))

    def start_listening(self):
        if self.server_destination is None:
            try:
                self.server_destination = RNS.Destination(self.app.identity, RNS.Destination.IN, RNS.Destination.SINGLE, SPEEDTEST_APP_NAME, *SPEEDTEST_ASPECTS)
                self.server_destination.set_link_established_callback(self._on_incoming_link)
                try:
                    self.server_destination.accepts_links(True)
                except Exception:
                    pass
            except Exception as e:
                self._log("Could not start listener: %s" % str(e), "error_text")
                self.server_destination = None
        self._listening = True
        self._update_address()

    def stop_listening(self):
        self._listening = False
        try:
            if self._incoming_link is not None:
                self._incoming_link.teardown()
        except Exception:
            pass
        self._incoming_link = None
        self._recv_link = None
        try:
            if self.server_destination is not None:
                RNS.Transport.deregister_destination(self.server_destination)
        except Exception:
            pass
        self.server_destination = None
        self._update_address()

    def _is_active(self):
        try:
            md = self.app.ui.main_display
            return self._listening and md.sub_displays.active_display is self.parent and getattr(self.parent, "active", None) == "speedtest"
        except Exception:
            return False

    def _peer_identity(self):
        hexhash = self.hash_edit.edit_text.strip()
        dest_len = (RNS.Reticulum.TRUNCATED_HASHLENGTH // 8) * 2
        if len(hexhash) != dest_len:
            return None
        try:
            return RNS.Identity.recall(bytes.fromhex(hexhash))
        except Exception:
            return None

    def go_back(self):
        self.stop_listening()
        if self.parent is not None:
            self.parent.show_landing()

    def go_back_to_header(self):
        try:
            self.app.ui.main_display.frame.focus_position = "header"
        except Exception:
            pass

    def _log(self, message, attr="body_text"):
        self.walker.append(urwid.Text((attr, message)))
        try:
            self.listbox.set_focus(len(self.walker) - 1)
        except Exception:
            pass

    def _draw(self):
        try:
            self.app.ui.loop.draw_screen()
        except Exception:
            pass

    def _schedule(self, fn):
        try:
            self.app.ui.loop.set_alarm_in(0, lambda *a: (fn(), self._draw()))
        except Exception:
            try:
                fn()
            except Exception:
                pass

    def _on_incoming_link(self, link):
        if not self._is_active():
            try:
                link.teardown()
            except Exception:
                pass
            return
        self._incoming_link = link
        link.set_remote_identified_callback(self._on_remote_identified)
        self.app.ui.loop.set_alarm_in(8, lambda l, u: self._incoming_timeout(link))

    def _incoming_timeout(self, link):
        if self._recv_link is link:
            return
        try:
            link.teardown()
        except Exception:
            pass

    def _on_remote_identified(self, link, identity):
        self._schedule(lambda: self._verify_incoming(link, identity))

    def _verify_incoming(self, link, identity):
        peer_identity = self._peer_identity()
        if peer_identity is None or peer_identity.hash != identity.hash:
            self._log("Rejected speed test from unauthorized peer", "warning_text")
            try:
                link.teardown()
            except Exception:
                pass
            return
        self._recv_link = link
        self._recv_started = None
        self._recv_bytes = 0
        link.set_resource_strategy(RNS.Link.ACCEPT_ALL)
        link.set_resource_started_callback(self._on_recv_started)
        link.set_resource_concluded_callback(self._on_recv_concluded)
        self._log("Incoming speed test from %s" % RNS.prettyhexrep(identity.hash), "connected_status")

    def _on_recv_started(self, resource):
        self._schedule(self._recv_started_now)

    def _recv_started_now(self):
        self._recv_started = time.time()
        self.progress_text.set_text(("body_text", "Receiving…"))

    def _on_recv_concluded(self, resource):
        self._schedule(lambda: self._recv_concluded(resource))

    def _recv_concluded(self, resource):
        try:
            complete = resource.status == RNS.Resource.COMPLETE
        except Exception:
            complete = False
        if not complete:
            self._log("Incoming transfer failed", "warning_text")
            return
        size = self._resource_size(resource)
        elapsed = max(0.001, time.time() - (self._recv_started or time.time()))
        self._log("Download: %s (%s in %.2fs)" % (_fmt_bitrate(size / elapsed), _size_str(size), elapsed), "connected_status")
        self.progress_text.set_text("")

    def _resource_size(self, resource):
        for getter in ("get_transfer_size", "getTransferSize"):
            try:
                fn = getattr(resource, getter, None)
                if fn:
                    v = fn()
                    if v:
                        return v
            except Exception:
                pass
        try:
            return getattr(resource, "size", 0) or len(resource.data)
        except Exception:
            return 0

    def on_start(self, button=None):
        if self._sending:
            return
        self.update_interface_status()

        peer_identity = self._peer_identity()
        dest_len = (RNS.Reticulum.TRUNCATED_HASHLENGTH // 8) * 2
        hexhash = self.hash_edit.edit_text.strip()
        if len(hexhash) != dest_len:
            self._log("Peer hash must be %d hex characters" % dest_len, "error_text")
            return
        try:
            self._dest_hash = bytes.fromhex(hexhash)
        except Exception:
            self._log("Invalid peer hash", "error_text")
            return

        try:
            mb = float(self.size_edit.edit_text.strip() or str(DEFAULT_SPEEDTEST_MB))
        except ValueError:
            mb = DEFAULT_SPEEDTEST_MB
        mb = max(0.01, min(MAX_SPEEDTEST_MB, mb))
        self._send_bytes = int(mb * 1024 * 1024)

        self._sending = True
        self.start_button.original_widget.set_label("Testing…")
        self.progress_text.set_text("")

        if RNS.Transport.has_path(self._dest_hash):
            self._establish_link()
        else:
            try:
                RNS.Transport.request_path(self._dest_hash)
            except Exception:
                pass
            self._log("Requesting path to %s …" % RNS.prettyhexrep(self._dest_hash))
            self._deadline = time.time() + self._timeout()
            self.app.ui.loop.set_alarm_in(0.25, self._await_path)

    def _timeout(self):
        try:
            return DEFAULT_PROBE_TIMEOUT + self.app.rns.get_first_hop_timeout(self._dest_hash)
        except Exception:
            return DEFAULT_PROBE_TIMEOUT

    def _await_path(self, loop, user_data):
        if RNS.Transport.has_path(self._dest_hash):
            self._establish_link()
        elif time.time() > self._deadline:
            self._log("Path not found", "warning_text")
            self._finish()
        else:
            loop.set_alarm_in(0.25, self._await_path)

    def _establish_link(self):
        identity = RNS.Identity.recall(self._dest_hash)
        if identity is None:
            self._log("Could not recall identity for peer", "error_text")
            self._finish()
            return
        try:
            destination = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, SPEEDTEST_APP_NAME, *SPEEDTEST_ASPECTS)
            self._log("Establishing link with %s …" % RNS.prettyhexrep(self._dest_hash))
            self._client_link = RNS.Link(destination, established_callback=self._on_client_link_up, closed_callback=self._on_client_link_closed)
        except Exception as e:
            self._log("Could not establish link: %s" % str(e), "error_text")
            self._finish()
            return
        self._link_deadline = time.time() + self._timeout()
        self.app.ui.loop.set_alarm_in(0.5, self._check_link)

    def _check_link(self, loop, user_data):
        if not self._sending or self._client_resource is not None:
            return
        try:
            active = self._client_link is not None and self._client_link.status == RNS.Link.ACTIVE
        except Exception:
            active = False
        if active:
            return
        if time.time() > self._link_deadline:
            self._log("Link establishment timed out", "warning_text")
            try:
                self._client_link.teardown()
            except Exception:
                pass
            self._finish()
        else:
            loop.set_alarm_in(0.5, self._check_link)

    def _on_client_link_up(self, link):
        self._schedule(lambda: self._client_ready(link))

    def _client_ready(self, link):
        if not self._sending:
            return
        try:
            link.identify(self.app.identity)
        except Exception:
            pass
        self.app.ui.loop.set_alarm_in(0.6, lambda l, u: self._send_resource(link))

    def _send_resource(self, link):
        if not self._sending or self._client_resource is not None:
            return
        try:
            data = os.urandom(self._send_bytes)
            self._send_started = time.time()
            self._client_resource = RNS.Resource(data, link, callback=self._on_send_done, progress_callback=self._on_send_progress, auto_compress=False)
            self._log("Sending %s test payload …" % _size_str(self._send_bytes))
        except Exception as e:
            self._log("Could not start transfer: %s" % str(e), "error_text")
            self._finish()

    def _on_send_progress(self, resource):
        self._schedule(lambda: self._send_progress(resource))

    def _send_progress(self, resource):
        try:
            pct = int(resource.get_progress() * 100)
        except Exception:
            pct = 0
        self.progress_text.set_text(("body_text", "Uploading… %d%%" % pct))

    def _on_send_done(self, resource):
        self._schedule(lambda: self._send_done(resource))

    def _send_done(self, resource):
        try:
            complete = resource.status == RNS.Resource.COMPLETE
        except Exception:
            complete = False
        if complete:
            elapsed = max(0.001, time.time() - (self._send_started or time.time()))
            self._log("Upload: %s (%s in %.2fs)" % (_fmt_bitrate(self._send_bytes / elapsed), _size_str(self._send_bytes), elapsed), "connected_status")
        else:
            self._log("Transfer failed or was not accepted", "warning_text")
        try:
            if self._client_link is not None:
                self._client_link.teardown()
        except Exception:
            pass
        self.progress_text.set_text("")
        self._finish()

    def _on_client_link_closed(self, link):
        self._schedule(self._client_closed)

    def _client_closed(self):
        if self._sending and self._client_resource is None:
            self._log("Link closed before the test started", "warning_text")
            self._finish()

    def _finish(self):
        self._sending = False
        self.start_button.original_widget.set_label("Start test")
        self._draw()

def _size_str(num, suffix="B"):
    units = ["", "K", "M", "G", "T"]
    num = float(num)
    for unit in units:
        if abs(num) < 1024.0:
            return "%.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f P%s" % (num, suffix)
