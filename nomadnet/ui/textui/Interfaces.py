import RNS
import time
import nomadnet
from math import log10, pow

from nomadnet.vendor.additional_urwid_widgets.FormWidgets import *
from nomadnet.vendor.AsciiChart import AsciiChart

### GYLPHS ###
INTERFACE_GLYPHS = {
    # Glyph name                # Plain          # Unicode              # Nerd Font
    ("NetworkInterfaceType",    "(IP)",          "\U0001f5a7",          "\U000f0200"),
    ("SerialInterfaceType",     "(<->)",         "\u2194",              "\U000f065c"),
    ("RNodeInterfaceType",      "(R)" ,          "\u16b1",              "\U000f043a"),
    ("OtherInterfaceType",      "(#)" ,          "\U0001f67e",          "\ued95"),
}

### HELPER ###
PLATFORM_IS_LINUX = False
try:
    PLATFORM_IS_LINUX = (RNS.vendor.platformutils.is_android() or
                         RNS.vendor.platformutils.is_linux())
except Exception:
    pass

def _get_interface_icon(glyphset, iface_type):
    glyphset_index = 1  # Default to unicode
    if glyphset == "plain":
        glyphset_index = 0  # plain
    elif glyphset == "nerdfont":
        glyphset_index = 2  # nerdfont

    type_to_glyph_tuple = {
        "BackboneInterface": "NetworkInterfaceType",
        "AutoInterface": "NetworkInterfaceType",
        "TCPClientInterface": "NetworkInterfaceType",
        "TCPServerInterface": "NetworkInterfaceType",
        "UDPInterface": "NetworkInterfaceType",
        "I2PInterface": "NetworkInterfaceType",

        "RNodeInterface": "RNodeInterfaceType",
        "RNodeMultiInterface": "RNodeInterfaceType",

        "SerialInterface": "SerialInterfaceType",
        "KISSInterface": "SerialInterfaceType",
        "AX25KISSInterface": "SerialInterfaceType",

        "PipeInterface": "OtherInterfaceType"
    }

    glyph_tuple_name = type_to_glyph_tuple.get(iface_type, "OtherInterfaceType")

    for glyph_tuple in INTERFACE_GLYPHS:
        if glyph_tuple[0] == glyph_tuple_name:
            return glyph_tuple[glyphset_index + 1]

    # Fallback
    return "(#)" if glyphset == "plain" else "\U0001f67e" if glyphset == "unicode" else "\ued95"

def format_bytes(bytes_value):
    units = ['bytes', 'KB', 'MB', 'GB', 'TB']
    size = float(bytes_value)
    unit_index = 0

    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"

def _get_cols_rows():
    return nomadnet.NomadNetworkApp.get_shared_instance().ui.screen.get_cols_rows()


### PORT FUNCTIONS ###
PYSERIAL_AVAILABLE = False # If NomadNet is installed on environments with rnspure instead of rns, pyserial won't be available
try:
    import serial.tools.list_ports
    PYSERIAL_AVAILABLE = True
except ImportError:
    class DummyPort:
        def __init__(self, device, description=None, manufacturer=None, hwid=None):
            self.device = device
            self.description = description or device
            self.manufacturer = manufacturer
            self.hwid = hwid
            self.vid = None
            self.pid = None

def get_port_info():
    if not PYSERIAL_AVAILABLE:
        return []

    try:
        ports = serial.tools.list_ports.comports()
        port_info = []

        # Ports are sorted into categories for dropdown, priority ports appear first
        priority_ports = []  # USB, ACM, bluetooth, etc
        standard_ports = []  # COM, tty/s ports

        for port in ports:
            desc = f"{port.device}"
            if port.description and port.description != port.device:
                desc += f" ({port.description})"
            if port.manufacturer:
                desc += f" - {port.manufacturer}"

            is_standard = (
                    port.device.startswith("COM") or  # windows
                    "/dev/ttyS" in port.device or  # Linux
                    "Serial" in port.description
            )

            port_data = {
                'device': port.device,
                'description': desc,
                'hwid': port.hwid,
                'vid': port.vid,
                'pid': port.pid,
                'is_standard': is_standard
            }

            if is_standard:
                standard_ports.append(port_data)
            else:
                priority_ports.append(port_data)

        priority_ports.sort(key=lambda x: x['device'])
        standard_ports.sort(key=lambda x: x['device'])

        return priority_ports + standard_ports
    except Exception as e:
        RNS.log(f"error accessing serial ports: {str(e)}", RNS.LOG_ERROR)
        return []

def get_port_field():
    if not PYSERIAL_AVAILABLE:
        return {
            "config_key": "port",
            "type": "edit",
            "label": "Port: ",
            "default": "",
            "placeholder": "/dev/ttyUSB0 or COM port (pyserial not installed)",
            "validation": ["required"],
            "transform": lambda x: x.strip()
        }

    port_info = get_port_info()

    if len(port_info) > 1:
        options = [p['description'] for p in port_info]
        device_map = {p['description']: p['device'] for p in port_info}

        return {
            "config_key": "port",
            "type": "dropdown",
            "label": "Port: ",
            "options": options,
            "default": options[0] if options else "",
            "validation": ["required"],
            "transform": lambda x: device_map[x]
        }
    else:
        # single or no ports - use text field
        default = port_info[0]['device'] if port_info else ""
        placeholder = "/dev/ttyXXX (or COM port on Windows)"

        return {
            "config_key": "port",
            "type": "edit",
            "label": "Port: ",
            "default": default,
            "placeholder": placeholder,
            "validation": ["required"],
            "transform": lambda x: x.strip()
        }

### RNODE ####
def calculate_rnode_parameters(bandwidth, spreading_factor, coding_rate, noise_floor=6, antenna_gain=0,
                               transmit_power=17):
    crn = {
        5: 1,
        6: 2,
        7: 3,
        8: 4,
    }
    coding_rate_n = crn.get(coding_rate, 1)

    sfn = {
        5: -2.5,
        6: -5,
        7: -7.5,
        8: -10,
        9: -12.5,
        10: -15,
        11: -17.5,
        12: -20
    }

    data_rate = spreading_factor * (
                (4 / (4 + coding_rate_n)) / (pow(2, spreading_factor) / (bandwidth / 1000))) * 1000

    sensitivity = -174 + 10 * log10(bandwidth) + noise_floor + (sfn.get(spreading_factor, 0))

    if bandwidth == 203125 or bandwidth == 406250 or bandwidth > 500000:
        sensitivity = -165.6 + 10 * log10(bandwidth) + noise_floor + (sfn.get(spreading_factor, 0))

    link_budget = (transmit_power - sensitivity) + antenna_gain

    if data_rate < 1000:
        data_rate_str = f"{data_rate:.0f} bps"
    else:
        data_rate_str = f"{(data_rate / 1000):.2f} kbps"

    return {
        "data_rate": data_rate_str,
        "link_budget": f"{link_budget:.1f} dB",
        "sensitivity": f"{sensitivity:.1f} dBm",
        "raw_data_rate": data_rate,
        "raw_link_budget": link_budget,
        "raw_sensitivity": sensitivity
    }

class RNodeCalculator(urwid.WidgetWrap):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        self.update_alarm = None

        self.data_rate_widget = urwid.Text("Data Rate: Calculating...")
        self.link_budget_widget = urwid.Text("Link Budget: Calculating...")
        self.sensitivity_widget = urwid.Text("Sensitivity: Calculating...")

        self.noise_floor_edit = urwid.Edit("", "0")
        self.antenna_gain_edit = urwid.Edit("", "0")

        layout = urwid.Pile([
            urwid.Divider("-"),

            urwid.Columns([
                (28, urwid.Text(("key", "Enter Noise Floor (dB): "), align="right")),
                self.noise_floor_edit
            ]),

            urwid.Columns([
                (28, urwid.Text(("key", "Enter Antenna Gain (dBi): "), align="right")),
                self.antenna_gain_edit
            ]),

            urwid.Divider(),

            urwid.Text(("connected_status", "On-Air Calculations:"), align="left"),
            self.data_rate_widget,
            self.link_budget_widget,
            self.sensitivity_widget,
            urwid.Divider(),

            urwid.Text([
                "These calculations will update as you change RNode parameters"
            ])
        ])

        super().__init__(layout)

        self.connect_all_field_signals()

        self.update_calculation()

    def connect_all_field_signals(self):
        urwid.connect_signal(self.noise_floor_edit, 'change', self._queue_update)
        urwid.connect_signal(self.antenna_gain_edit, 'change', self._queue_update)
        rnode_fields = ['bandwidth', 'spreadingfactor', 'codingrate', 'txpower']

        for field_name in rnode_fields:
            if field_name in self.parent_view.fields:

                field_widget = self.parent_view.fields[field_name]['widget']

                if hasattr(field_widget, 'edit_text'):
                    urwid.connect_signal(field_widget, 'change', self._queue_update)
                elif hasattr(field_widget, '_emit') and 'change' in getattr(field_widget, 'signals', []):
                    urwid.connect_signal(field_widget, 'change', self._queue_update)

    def _queue_update(self, widget, new_text):
        if self.update_alarm is not None:
            try:
                self.parent_view.parent.app.ui.loop.remove_alarm(self.update_alarm)
            except:
                pass

        self.update_alarm = self.parent_view.parent.app.ui.loop.set_alarm_in(
            0.3, self._delayed_update)

    def _delayed_update(self, loop, user_data):
        self.update_alarm = None
        self.update_calculation()

    def update_calculation(self):
        try:

            try:
                bandwidth_widget = self.parent_view.fields.get('bandwidth', {}).get('widget')
                bandwidth = int(bandwidth_widget.get_value()) if bandwidth_widget else 125000
            except (ValueError, AttributeError):
                bandwidth = 125000

            try:
                sf_widget = self.parent_view.fields.get('spreadingfactor', {}).get('widget')
                spreading_factor = int(sf_widget.get_value()) if sf_widget else 7
            except (ValueError, AttributeError):
                spreading_factor = 7

            try:
                cr_widget = self.parent_view.fields.get('codingrate', {}).get('widget')
                coding_rate = int(cr_widget.get_value()) if cr_widget else 5
                if isinstance(coding_rate, str) and ":" in coding_rate:
                    coding_rate = int(coding_rate.split(":")[1])
            except (ValueError, AttributeError):
                coding_rate = 5

            try:
                txpower_widget = self.parent_view.fields.get('txpower', {}).get('widget')
                if hasattr(txpower_widget, 'edit_text'):
                    txpower_text = txpower_widget.edit_text.strip()
                    txpower = int(txpower_text) if txpower_text else 17
                else:
                    txpower = int(txpower_widget.get_value()) if txpower_widget else 17
            except (ValueError, AttributeError):
                txpower = 17

            try:
                noise_floor_text = self.noise_floor_edit.edit_text.strip()
                noise_floor = int(noise_floor_text) if noise_floor_text else 0
            except (ValueError, AttributeError):
                noise_floor = 0

            try:
                antenna_gain_text = self.antenna_gain_edit.edit_text.strip()
                antenna_gain = int(antenna_gain_text) if antenna_gain_text else 0
            except (ValueError, AttributeError):
                antenna_gain = 0

            result = calculate_rnode_parameters(
                bandwidth=bandwidth,
                spreading_factor=spreading_factor,
                coding_rate=coding_rate,
                noise_floor=noise_floor,
                antenna_gain=antenna_gain,
                transmit_power=txpower
            )

            self.data_rate_widget.set_text(f"Data Rate: {result['data_rate']}")
            self.link_budget_widget.set_text(f"Link Budget: {result['link_budget']}")
            self.sensitivity_widget.set_text(f"Sensitivity: {result['sensitivity']}")

        except (ValueError, KeyError, TypeError) as e:
            self.data_rate_widget.set_text(f"Data Rate: Waiting for parameters...")
            self.link_budget_widget.set_text(f"Link Budget: Waiting for valid parameters...")
            self.sensitivity_widget.set_text(f"Sensitivity: Waiting for parameters...")

### INTERFACE FIELDS ###
COMMON_INTERFACE_OPTIONS = [
    {
        "config_key": "network_name",
        "type": "edit",
        "label": "Virtual Network Name: ",
        "placeholder": "Optional virtual network name",
        "default": "",
        "validation": [],
        "transform": lambda x: x.strip()
    },
    {
        "config_key": "passphrase",
        "type": "edit",
        "label": "IFAC Passphrase: ",
        "placeholder": "IFAC authentication passphrase",
        "default": "",
        "validation": [],
        "transform": lambda x: x.strip()
    },
    {
        "config_key": "ifac_size",
        "type": "edit",
        "label": "IFAC Size: ",
        "placeholder": "8 - 512",
        "default": "",
        "validation": ['number'],
        "transform": lambda x: x.strip()
    },
    {
        "config_key": "bitrate",
        "type": "edit",
        "label": "Inferred Bitrate: ",
        "placeholder": "Automatically determined",
        "default": "",
        "validation": ['number'],
        "transform": lambda x: x.strip()
    },
]

INTERFACE_FIELDS = {
    "BackboneInterface": [
        {
            "config_key": "listen_on",
            "type": "edit",
            "label": "Listen On: ",
            "default": "",
            "placeholder": "e.g., 0.0.0.0",
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "port",
            "type": "edit",
            "label": "Port: ",
            "default": "",
            "placeholder": "e.g., 4242",
            "validation": ["number"],
            "transform": lambda x: int(x.strip()) if x.strip() else None
        },
        {
            "config_key": "device",
            "type": "edit",
            "label": "Device: ",
            "default": "",
            "placeholder": "e.g., eth0",
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "remote",
            "type": "edit",
            "label": "Remote: ",
            "default": "",
            "placeholder": "e.g., a remote TCPServerInterface location",
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "target_host",
            "type": "edit",
            "label": "Target Host: ",
            "default": "",
            "placeholder": "e.g., 201:5d78:af73:5caf:a4de:a79f:3278:71e5",
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "port",
            "type": "edit",
            "label": "Target Port: ",
            "default": "",
            "placeholder": "e.g., 4242",
            "validation": ["number"],
            "transform": lambda x: int(x.strip()) if x.strip() else None
        },
        {
            "config_key": "prefer_ipv6",
            "type": "checkbox",
            "label": "",
            "default": False,
            "validation": [],
            "transform": lambda x: bool(x)
        },
    ],
    "AutoInterface": [
        {

        },
        {
            "additional_options": [
                {
                    "config_key": "devices",
                    "type": "multilist",
                    "label": "Devices: ",
                    "validation": [],
                    "transform": lambda x: ",".join(x)
                },
                {
                    "config_key": "ignored_devices",
                    "type": "multilist",
                    "label": "Ignored Devices: ",
                    "validation": [],
                    "transform": lambda x: ",".join(x)
                },
                {
                            "config_key": "group_id",
                            "type": "edit",
                            "label": "Group ID: ",
                            "default": "",
                            "placeholder": "e.g., my_custom_network",
                            "validation": [],
                            "transform": lambda x: x.strip()
                },
                {
                    "config_key": "discovery_scope",
                    "type": "dropdown",
                    "label": "Discovery Scope: ",
                    "options": ["None", "link", "admin", "site", "organisation", "global"],
                    "default": "None",
                    "validation": [],
                    "transform": lambda x: "" if x == "None" else x.strip()
                }
            ]
        },
    ],
    "I2PInterface": [
        {
            "config_key": "peers",
            "type": "multilist",
            "label": "Peers: ",
            "placeholder": "",
            "validation": ["required"],
            "transform": lambda x: ",".join(x)
        }
    ],
    "TCPServerInterface": [
        {
            "config_key": "listen_ip",
            "type": "edit",
            "label": "Listen IP: ",
            "default": "",
            "placeholder": "e.g., 0.0.0.0",
            "validation": ["required"],
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "listen_port",
            "type": "edit",
            "label": "Listen Port: ",
            "default": "",
            "placeholder": "e.g., 4242",
            "validation": ["number"],
            "transform": lambda x: int(x.strip()) if x.strip() else None
        },
        {
            "additional_options": [
                {
                    "config_key": "prefer_ipv6",
                    "type": "checkbox",
                    "label": "Prefer IPv6?",
                    "default": False,
                    "validation": [],
                    "transform": lambda x: bool(x)
                },
                {
                    "config_key": "i2p_tunneled",
                    "type": "checkbox",
                    "label": "I2P Tunneled?",
                    "default": False,
                    "validation": [],
                    "transform": lambda x: bool(x)
                },
                {
                    "config_key": "device",
                    "type": "edit",
                    "label": "Device: ",
                    "placeholder": "A specific network device to listen on - e.g. eth0",
                    "default": "",
                    "validation": [],
                    "transform": lambda x: x.strip() if x.strip() else None
                },
                {
                    "config_key": "port",
                    "type": "edit",
                    "label": "Port: ",
                    "default": "",
                    "placeholder": "e.g., 4242",
                    "validation": ["number"],
                    "transform": lambda x: int(x.strip()) if x.strip() else None
                },
            ]
        }
    ],
    "TCPClientInterface": [
        {
            "config_key": "target_host",
            "type": "edit",
            "label": "Target Host: ",
            "default": "",
            "placeholder": "e.g., 127.0.0.1",
            "validation": ["required"],
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "target_port",
            "type": "edit",
            "label": "Target Port: ",
            "default": "",
            "placeholder": "e.g., 8080",
            "validation": ["required", "number"],
            "transform": lambda x: int(x.strip()) if x.strip() else None
        },
        {
            "additional_options": [
                {
                    "config_key": "i2p_tunneled",
                    "type": "checkbox",
                    "label": "I2P Tunneled?",
                    "default": False,
                    "validation": [],
                    "transform": lambda x: bool(x)
                },
                {
                    "config_key": "kiss_framing",
                    "type": "checkbox",
                    "label": "KISS Framing?",
                    "default": False,
                    "validation": [],
                    "transform": lambda x: bool(x)
                }
            ]
        }
    ],
    "UDPInterface": [
        {
            "config_key": "listen_ip",
            "type": "edit",
            "label": "Listen IP: ",
            "default": "",
            "placeholder": "e.g., 0.0.0.0",
            "validation": ["required"],
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "listen_port",
            "type": "edit",
            "label": "Listen Port: ",
            "default": "",
            "placeholder": "e.g., 4242",
            "validation": ["number"],
            "transform": lambda x: int(x.strip()) if x.strip() else None
        },
        {
            "config_key": "forward_ip",
            "type": "edit",
            "label": "Forward IP: ",
            "default": "",
            "placeholder": "e.g., 255.255.255.255",
            "validation": ["required"],
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "forward_port",
            "type": "edit",
            "label": "Forward Port: ",
            "default": "",
            "placeholder": "e.g., 4242",
            "validation": ["required", "number"],
            "transform": lambda x: int(x.strip()) if x.strip() else None
        },
        {
            "additional_options": [
                {
                    "config_key": "device",
                    "type": "edit",
                    "label": "Device: ",
                    "placeholder": "A specific network device to listen on - e.g. eth0",
                    "default": "",
                    "validation": [],
                    "transform": lambda x: x.strip()
                },
                {
                    "config_key": "port",
                    "type": "edit",
                    "label": "Port: ",
                    "default": "",
                    "placeholder": "e.g., 4242",
                    "validation": ["number"],
                    "transform": lambda x: int(x.strip()) if x.strip() else None
                },
            ]
        }
    ],
    "RNodeInterface": [
        get_port_field(),
        {
            "config_key": "frequency",
            "type": "edit",
            "label": "Frequency (MHz): ",
            "default": "",
            "placeholder": "868.5",
            "validation": ["required", "float"],
            "transform": lambda x: int(float(x.strip()) * 1000000) if x.strip() else 868500000
        },
        {
            "config_key": "txpower",
            "type": "edit",
            "label": "Transmit Power (dBm): ",
            "default": "",
            "placeholder": "17",
            "validation": ["required", "number"],
            "transform": lambda x: int(x.strip()) if x.strip() else 17
        },
        {
            "config_key": "bandwidth",
            "type": "dropdown",
            "label": "Bandwidth (Hz): ",
            "options": ["7800", "10400", "15600", "20800", "31250", "41700", "62500", "125000", "250000",
                        "500000", "1625000"],
            "default": "7800",
            "validation": ["required"],
            "transform": lambda x: int(x)
        },
        {
            "config_key": "spreadingfactor",
            "type": "dropdown",
            "label": "Spreading Factor: ",
            "options": ["7", "8", "9", "10", "11", "12"],
            "default": "7",
            "validation": ["required"],
            "transform": lambda x: int(x)
        },
        {
            "config_key": "codingrate",
            "type": "dropdown",
            "label": "Coding Rate: ",
            "options": ["4:5", "4:6", "4:7", "4:8"],
            "default": "4:5",
            "validation": ["required"],
            "transform": lambda x: int(x.split(":")[1])
        },
        {
            "additional_options": [
                {
                    "config_key": "id_callsign",
                    "type": "edit",
                    "label": "Callsign: ",
                    "default": "",
                    "placeholder": "e.g. MYCALL-0",
                    "validation": [""],
                    "transform": lambda x: x.strip()
                },
                {
                    "config_key": "id_interval",
                    "type": "edit",
                    "label": "ID Interval (Seconds): ",
                    "placeholder": "e.g. 600",
                    "default": "",
                    "validation": ['number'],
                    "transform": lambda x: "" if x == "" else int(x)
                },
                {
                    "config_key": "airtime_limit_long",
                    "type": "edit",
                    "label": "Airtime Limit Long (Seconds):  ",
                    "placeholder": "e.g. 1.5",
                    "default": "",
                    "validation": ['number'],
                    "transform": lambda x: "" if x == "" else int(x)
                },
                {
                    "config_key": "airtime_limit_short",
                    "type": "edit",
                    "label": "Airtime Limit Short (Seconds):  ",
                    "placeholder": "e.g. 33",
                    "default": "",
                    "validation": ['number'],
                    "transform": lambda x: "" if x == "" else int(x)
                },
            ]
        }
    ],
    "RNodeMultiInterface": [
        get_port_field(),
        {
            "config_key": "subinterfaces",
            "type": "multitable",
            "fields": {
                "frequency": {
                    "label": "Freq (Hz)",
                    "type": "edit",
                    "validation": ["required", "float"],
                    "transform": lambda x: int(x) if x else None
                },
                "bandwidth": {
                    "label": "BW (Hz)",
                    "type": "edit",
                    "options": ["7800", "10400", "15600", "20800", "31250", "41700", "62500", "125000", "250000", "500000", "1625000"],
                    "transform": lambda x: int(x) if x else None
                },
                "txpower": {
                    "label": "TX (dBm)",
                    "type": "edit",
                    "validation": ["required", "number"],
                    "transform": lambda x: int(x) if x else None
                },
                "vport": {
                    "label": "V.Port",
                    "type": "edit",
                    "validation": ["required", "number"],
                    "transform": lambda x: int(x) if x else None
                },
                "spreadingfactor": {
                    "label": "SF",
                    "type": "edit",
                    "transform": lambda x: int(x) if x else None
                },
                "codingrate": {
                    "label": "CR",
                    "type": "edit",
                    "transform": lambda x: int(x) if x else None
                }
            },
            "validation": ["required"],
            "transform": lambda x: x
        },
        {
            "additional_options": [
                {
                    "config_key": "id_callsign",
                    "type": "edit",
                    "label": "Callsign: ",
                    "default": "",
                    "placeholder": "e.g. MYCALL-0",
                    "validation": [""],
                    "transform": lambda x: x.strip()
                },
                {
                    "config_key": "id_interval",
                    "type": "edit",
                    "label": "ID Interval (Seconds): ",
                    "placeholder": "e.g. 600",
                    "default": "",
                    "validation": ['number'],
                    "transform": lambda x: "" if x == "" else int(x)
                }
            ]
        }
    ],
    "SerialInterface": [
        get_port_field(),
        {
            "config_key": "speed",
            "type": "edit",
            "label": "Speed (bps): ",
            "default": "",
            "placeholder": "e.g. 115200",
            "validation": ["required", "number"],
            "transform": lambda x: int(x.strip())
        },
        {
            "config_key": "databits",
            "type": "edit",
            "label": "Databits: ",
            "default": "",
            "placeholder": "e.g. 8",
            "validation": ["required", "number"],
            "transform": lambda x: int(x.strip())
        },
        {
            "config_key": "parity",
            "type": "edit",
            "label": "Parity: ",
            "default": "",
            "placeholder": "",
            "validation": ["number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "config_key": "stopbits",
            "type": "edit",
            "label": "Stopbits: ",
            "default": "",
            "placeholder": "e.g. 1",
            "validation": ["number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
    ],
    "PipeInterface": [
        {
            "config_key": "command",
            "type": "edit",
            "label": "Command: ",
            "default": "",
            "placeholder": "e.g. netcat -l 5757",
            "validation": ["required"],
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "respawn_delay",
            "type": "edit",
            "label": "Respawn Delay (seconds):  ",
            "default": "",
            "placeholder": "e.g. 5",
            "validation": ["number"],
            "transform": lambda x: x.strip()
        },
    ],
    "KISSInterface": [
        get_port_field(),
        {
            "config_key": "speed",
            "type": "edit",
            "label": "Speed (bps): ",
            "default": "",
            "placeholder": "e.g. 115200",
            "validation": ["required", "number"],
            "transform": lambda x: int(x.strip())
        },
        {
            "config_key": "databits",
            "type": "edit",
            "label": "Databits: ",
            "default": "",
            "placeholder": "e.g. 8",
            "validation": ["required", "number"],
            "transform": lambda x: int(x.strip())
        },
        {
            "config_key": "parity",
            "type": "edit",
            "label": "Parity: ",
            "default": "",
            "placeholder": "",
            "validation": ["number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "config_key": "stopbits",
            "type": "edit",
            "label": "Stopbits: ",
            "default": "",
            "placeholder": "e.g. 1",
            "validation": ["number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "config_key": "preamble",
            "type": "edit",
            "label": "Preamble (miliseconds): ",
            "default": "",
            "placeholder": "e.g. 150",
            "validation": ["required", "number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "config_key": "txtail",
            "type": "edit",
            "label": "TX Tail (miliseconds): ",
            "default": "",
            "placeholder": "e.g. 10",
            "validation": ["required", "number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "config_key": "slottime",
            "type": "edit",
            "label": "slottime (miliseconds): ",
            "default": "",
            "placeholder": "e.g. 20",
            "validation": ["required", "number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "config_key": "persistence",
            "type": "edit",
            "label": "Persistence (miliseconds): ",
            "default": "",
            "placeholder": "e.g. 200",
            "validation": ["required", "number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "additional_options": [
                {
                    "config_key": "id_callsign",
                    "type": "edit",
                    "label": "ID Callsign: ",
                    "default": "",
                    "placeholder": "e.g. MYCALL-0",
                    "validation": [""],
                    "transform": lambda x: x.strip()
                },
                {
                    "config_key": "id_interval",
                    "type": "edit",
                    "label": "ID Interval (Seconds): ",
                    "placeholder": "e.g. 600",
                    "default": "",
                    "validation": ['number'],
                    "transform": lambda x: "" if x == "" else int(x)
                },
                {
                    "config_key": "flow_control",
                    "type": "checkbox",
                    "label": "Flow Control ",
                    "validation": [],
                    "transform": lambda x: "" if x == "" else bool(x)
                },
            ]
        }
    ],
    "AX25KISSInterface": [
        get_port_field(),
        {
            "config_key": "callsign",
            "type": "edit",
            "label": "Callsign: ",
            "default": "",
            "placeholder": "e.g. NO1CLL",
            "validation": ["required"],
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "ssid",
            "type": "edit",
            "label": "SSID: ",
            "default": "",
            "placeholder": "e.g. 0",
            "validation": ["required"],
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "speed",
            "type": "edit",
            "label": "Speed (bps): ",
            "default": "",
            "placeholder": "e.g. 115200",
            "validation": ["required", "number"],
            "transform": lambda x: int(x.strip())
        },
        {
            "config_key": "databits",
            "type": "edit",
            "label": "Databits: ",
            "default": "",
            "placeholder": "e.g. 8",
            "validation": ["required", "number"],
            "transform": lambda x: int(x.strip())
        },
        {
            "config_key": "parity",
            "type": "edit",
            "label": "Parity: ",
            "default": "",
            "placeholder": "",
            "validation": ["number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "config_key": "stopbits",
            "type": "edit",
            "label": "Stopbits: ",
            "default": "",
            "placeholder": "e.g. 1",
            "validation": ["number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "config_key": "preamble",
            "type": "edit",
            "label": "Preamble (miliseconds): ",
            "default": "",
            "placeholder": "e.g. 150",
            "validation": ["required", "number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "config_key": "txtail",
            "type": "edit",
            "label": "TX Tail (miliseconds): ",
            "default": "",
            "placeholder": "e.g. 10",
            "validation": ["required", "number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "config_key": "slottime",
            "type": "edit",
            "label": "Slottime (miliseconds): ",
            "default": "",
            "placeholder": "e.g. 20",
            "validation": ["required", "number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "config_key": "persistence",
            "type": "edit",
            "label": "Persistence (miliseconds): ",
            "default": "",
            "placeholder": "e.g. 200",
            "validation": ["required", "number"],
            "transform": lambda x: "" if x == "" else int(x.strip())
        },
        {
            "additional_options": [
                {
                    "config_key": "flow_control",
                    "type": "checkbox",
                    "label": "Flow Control ",
                    "validation": [],
                    "transform": lambda x: "" if x == "" else bool(x)
                },
            ]
        }
    ],
    "CustomInterface": [
        {
            "config_key": "type",
            "type": "edit",
            "label": "Interface Type: ",
            "default": "",
            "placeholder": "Name of custom interface class",
            "validation": ["required"],
            "transform": lambda x: x.strip()
        },
        {
            "config_key": "custom_parameters",
            "type": "keyvaluepairs",
            "label": "Parameters: ",
            "validation": [],
            "transform": lambda x: x
        },
    ],
    "default": [
        {

        },
    ]
}

### INTERFACE WIDGETS ####
class SelectableInterfaceItem(urwid.WidgetWrap):
    def __init__(self, parent, name, is_connected, is_enabled, iface_type, tx, rx, icon="?", iface_options=None):
        self.parent = parent
        self._selectable = True
        self.icon = icon
        self.name = name
        self.is_connected = is_connected
        self.is_enabled = is_enabled
        self.iface_options = iface_options


        if is_enabled:
            enabled_txt = ("connected_status", "Enabled")
        else:
            enabled_txt = ("disconnected_status", "Disabled")

        if is_connected:
            connected_txt = ("connected_status", "Connected")
        else:
            connected_txt = ("disconnected_status", "Disconnected")

        self.selection_txt = urwid.Text(" ")
        self.title_widget = urwid.Text(("interface_title", f"{icon}  {name}"))

        title_content = urwid.Columns([
            (4, self.selection_txt),
            self.title_widget,
        ])

        self.tx_widget = urwid.Text(("value", format_bytes(tx)))
        self.rx_widget = urwid.Text(("value", format_bytes(rx)))

        self.status_widget = urwid.Text(enabled_txt)
        self.connection_widget = urwid.Text(connected_txt)

        rows = [
            urwid.Columns([
                (10, urwid.Text(("key", "Status: "))),
                (10, self.status_widget),
                (3, urwid.Text(" | ")),
                self.connection_widget,
            ]),

            urwid.Columns([
                (10, urwid.Text(("key", "Type:"))),
                urwid.Text(("value", iface_type)),
            ]),

            urwid.Divider("-"),

            urwid.Columns([
                (10, urwid.Text(("key", "TX:"))),
                (15, self.tx_widget),
                (10, urwid.Text(("key", "RX:"))),
                self.rx_widget,
            ]),
        ]

        pile_contents = [title_content] + rows

        pile = urwid.Pile(pile_contents)

        padded_body = urwid.Padding(pile, left=2, right=2)

        box = urwid.LineBox(
            padded_body,
            title=None,
            #todo
            tlcorner="╭", tline="─",
            trcorner="╮", lline="│",
            rline="│", blcorner="╰",
            bline="─", brcorner="╯"
        )

        super().__init__(box)

    def update_status_display(self):
        if self.is_enabled:
            self.status_widget.set_text(("connected_status", "Enabled"))
        else:
            self.status_widget.set_text(("disconnected_status", "Disabled"))

    def selectable(self):
        return True

    def render(self, size, focus=False):
        self.selection_txt.set_text(self.parent.g['selected'] if focus else self.parent.g['unselected'])

        if focus:
            self.title_widget.set_text(
                ("interface_title_selected", f"{self.icon}  {self.name}"))
        else:
            self.title_widget.set_text(("interface_title", f"{self.icon}  {self.name}"))

        return super().render(size, focus=focus)

    def keypress(self, size, key):
        if key == "up":
            listbox = self.parent.box_adapter._original_widget
            walker = listbox.body

            interface_items = [i for i, item in enumerate(walker)
                               if isinstance(item, SelectableInterfaceItem)]

            if interface_items and walker[listbox.focus_position] is self and \
                    listbox.focus_position == interface_items[0]:
                self.parent.app.ui.main_display.frame.focus_position = "header"
                return None
        elif key == "enter":
            self.parent.switch_to_show_interface(self.name)
            return None
        return key

    def update_stats(self, tx, rx):
        self.tx_widget.set_text(("value", format_bytes(tx)))
        self.rx_widget.set_text(("value", format_bytes(rx)))

class InterfaceOptionItem(urwid.WidgetWrap):
    def __init__(self, parent_display, label, value):
        self.parent_display = parent_display
        self.label = label
        self.value = value
        self._selectable = True

        text_widget = urwid.Text(label, align="left")
        super().__init__(urwid.AttrMap(text_widget, "list_normal", focus_map="list_focus"))

    def selectable(self):
        return True

    def keypress(self, size, key):
        if key == "enter":
            self.parent_display.dismiss_dialog()
            self.parent_display.switch_to_add_interface(self.value)
            return None
        return super().keypress(size, key)

class InterfaceBandwidthChart:

    def __init__(self, history_length=60, glyphset="unicode"):
        self.history_length = history_length
        self.glyphset = glyphset
        self.rx_rates = [0] * history_length
        self.tx_rates = [0] * history_length

        self.prev_rx = None
        self.prev_tx = None
        self.prev_time = None

        self.max_rx_rate = 1
        self.max_tx_rate = 1

        self.first_update = True
        self.initialization_complete = False
        self.stabilization_updates = 2
        self.update_count = 0

        self.peak_rx_for_display = 0
        self.peak_tx_for_display = 0

    def update(self, rx_bytes, tx_bytes):
        current_time = time.time()

        if self.prev_rx is None or self.first_update:
            self.prev_rx = rx_bytes
            self.prev_tx = tx_bytes
            self.prev_time = current_time
            self.first_update = False
            return

        time_delta = max(0.1, current_time - self.prev_time)

        rx_delta = max(0, rx_bytes - self.prev_rx) / time_delta
        tx_delta = max(0, tx_bytes - self.prev_tx) / time_delta

        self.prev_rx = rx_bytes
        self.prev_tx = tx_bytes
        self.prev_time = current_time

        self.update_count += 1

        self.rx_rates.pop(0)
        self.tx_rates.pop(0)
        self.rx_rates.append(rx_delta*8)
        self.tx_rates.append(tx_delta*8)

        if self.update_count >= self.stabilization_updates:
            self.initialization_complete = True

            self.peak_rx_for_display = max(self.peak_rx_for_display, rx_delta)
            self.peak_tx_for_display = max(self.peak_tx_for_display, tx_delta)


            current_rx_max = max(self.rx_rates)
            current_tx_max = max(self.tx_rates)

            self.max_rx_rate = max(1, current_rx_max)
            self.max_tx_rate = max(1, current_tx_max)

    def get_charts(self, height=8):
        chart = AsciiChart(glyphset=self.glyphset)

        rx_data = self.rx_rates.copy()
        tx_data = self.tx_rates.copy()

        peak_rx = self.peak_rx_for_display if self.initialization_complete else 0
        peak_tx = self.peak_tx_for_display if self.initialization_complete else 0

        peak_rx_str = RNS.prettyspeed(peak_rx*8)
        peak_tx_str = RNS.prettyspeed(peak_tx*8)

        rx_chart = chart.plot(
            [rx_data],
            {
                'height': height,
                'format': RNS.prettyspeed,
                'min': 0,
                'max': self.max_rx_rate * 1.1,
            }
        )

        tx_chart = chart.plot(
            [tx_data],
            {
                'height': height,
                'format': RNS.prettyspeed,
                'min': 0,
                'max': self.max_tx_rate * 1.1,
            }
        )

        return rx_chart, tx_chart, peak_rx_str, peak_tx_str


class ResponsiveChartContainer(urwid.WidgetWrap):

    def __init__(self, rx_box, tx_box, min_cols_for_horizontal=100):
        self.rx_box = rx_box
        self.tx_box = tx_box
        self.min_cols_for_horizontal = min_cols_for_horizontal

        self.horizontal_layout = urwid.Columns([
            (urwid.WEIGHT, 1, self.rx_box),
            (urwid.WEIGHT, 1, self.tx_box)
        ])

        self.vertical_layout = urwid.Pile([
            self.rx_box,
            self.tx_box
        ])

        self.layout = urwid.WidgetPlaceholder(self.horizontal_layout)

        super().__init__(self.layout)

    def render(self, size, focus=False):
        maxcol = size[0] if len(size) > 0 else 0

        if maxcol >= self.min_cols_for_horizontal and self.layout.original_widget is not self.horizontal_layout:
            self.layout.original_widget = self.horizontal_layout
        elif maxcol < self.min_cols_for_horizontal and self.layout.original_widget is not self.vertical_layout:
            self.layout.original_widget = self.vertical_layout

        return super().render(size, focus)

### URWID FILLER ###
class InterfaceFiller(urwid.WidgetWrap):
    def __init__(self, widget, app):
        self.app = app
        self.filler = urwid.Filler(widget, urwid.TOP)
        super().__init__(self.filler)

    def keypress(self, size, key):
        if key == "ctrl a":
            # add interface
            self.app.ui.main_display.sub_displays.interface_display.add_interface()
            return
        elif key == "ctrl x":
            # remove Interface
            self.app.ui.main_display.sub_displays.interface_display.remove_selected_interface()
            return
        elif key == "ctrl e":
            # edit interface
            self.app.ui.main_display.sub_displays.interface_display.edit_selected_interface()
            return None
        elif key == "ctrl w":
            # open config file editor
            self.app.ui.main_display.sub_displays.interface_display.open_config_editor()
            return None

        return super().keypress(size, key)

### VIEWS ###
class AddInterfaceView(urwid.WidgetWrap):
    def __init__(self, parent, iface_type):
        self.parent = parent
        self.iface_type = iface_type
        self.fields = {}
        self.port_pile = None
        self.additional_fields = {}
        self.additional_pile_contents = []
        self.common_fields = {}

        self.parent.shortcuts_display.set_add_interface_shortcuts()

        name_field = FormEdit(
            config_key="name",
            placeholder="Enter interface name",
            validation_types=["required"]
        )
        self.fields['name'] = {
            'label': "Name: ",
            'widget': name_field
        }

        config = INTERFACE_FIELDS.get(iface_type, INTERFACE_FIELDS["default"])
        iface_fields = [field for field in config if "config_key" in field]

        for field in iface_fields:
            self._initialize_field(field)

        self._initialize_additional_fields(config)

        self._initialize_common_fields()

        pile_items = self._build_form_layout(iface_fields)

        form_pile = urwid.Pile(pile_items)
        form_filler = urwid.Filler(form_pile, valign="top")
        form_box = urwid.LineBox(
            form_filler,
            title="Add Interface",
            tlcorner="╭", tline="─",
            trcorner="╮", lline="│",
            rline="│", blcorner="╰",
            bline="─", brcorner="╯"
        )

        background = urwid.SolidFill(" ")
        self.overlay = urwid.Overlay(
            top_w=form_box,
            bottom_w=background,
            align='center',
            width=('relative', 85),
            valign='middle',
            height=('relative', 85),
        )
        super().__init__(self.overlay)

    def _initialize_field(self, field):
        if field["type"] == "dropdown":
            widget = FormDropdown(
                config_key=field["config_key"],
                label=field.get("label", ""),
                options=field["options"],
                default=field.get("default"),
                validation_types=field.get("validation", []),
                transform=field.get("transform")
            )
        elif field["type"] == "checkbox":
            widget = FormCheckbox(
                config_key=field["config_key"],
                label=field.get("label", ""),
                state=field.get("default", False),
                validation_types=field.get("validation", []),
                transform=field.get("transform")
            )
        elif field["type"] == "multilist":
            widget = FormMultiList(
                config_key=field["config_key"],
                placeholder=field.get("placeholder", ""),
                validation_types=field.get("validation", []),
                transform=field.get("transform")
            )
        elif field["type"] == "multitable":
            widget = FormMultiTable(
                config_key=field["config_key"],
                fields=field.get("fields", {}),
                validation_types=field.get("validation", []),
                transform=field.get("transform")
            )
        elif field["type"] == "keyvaluepairs":
            widget = FormKeyValuePairs(
                config_key=field["config_key"],
                validation_types=field.get("validation", []),
                transform=field.get("transform")
            )
        else:
            widget = FormEdit(
                config_key=field["config_key"],
                caption="",
                edit_text=field.get("default", ""),
                placeholder=field.get("placeholder", ""),
                validation_types=field.get("validation", []),
                transform=field.get("transform")
            )

        label = field.get("label", "")
        if not label:
            label = " ".join(word.capitalize() for word in field["config_key"].split('_')) + ": "

        self.fields[field["config_key"]] = {
            'label': label,
            'widget': widget
        }

    def _initialize_additional_fields(self, config):
        for field in config:
            if isinstance(field, dict) and "additional_options" in field:
                for option in field["additional_options"]:
                    if option["type"] == "checkbox":
                        widget = FormCheckbox(
                            config_key=option["config_key"],
                            label=option.get("label", ""),
                            state=option.get("default", False),
                            validation_types=option.get("validation", []),
                            transform=option.get("transform")
                        )
                    elif option["type"] == "dropdown":
                        widget = FormDropdown(
                            config_key=option["config_key"],
                            label=option.get("label", ""),
                            options=option["options"],
                            default=option.get("default"),
                            validation_types=option.get("validation", []),
                            transform=option.get("transform")
                        )
                    elif option["type"] == "multilist":
                        widget = FormMultiList(
                            config_key=option["config_key"],
                            placeholder=option.get("placeholder", ""),
                            validation_types=option.get("validation", []),
                            transform=option.get("transform")
                        )
                    else:
                        widget = FormEdit(
                            config_key=option["config_key"],
                            caption="",
                            edit_text=str(option.get("default", "")),
                            placeholder=option.get("placeholder", ""),
                            validation_types=option.get("validation", []),
                            transform=option.get("transform")
                        )

                    label = option.get("label", "")
                    if not label:
                        label = " ".join(word.capitalize() for word in option["config_key"].split('_')) + ": "

                    self.additional_fields[option["config_key"]] = {
                        'label': label,
                        'widget': widget,
                        'type': option["type"]
                    }

    def _initialize_common_fields(self):
        if self.parent.app.rns.transport_enabled():
            # Transport mode options
            COMMON_INTERFACE_OPTIONS.extend([
                {
                    "config_key": "outgoing",
                    "type": "checkbox",
                    "label": "Allow outgoing traffic",
                    "default": True,
                    "validation": [],
                    "transform": lambda x: bool(x)
                },
                {
                    "config_key": "mode",
                    "type": "dropdown",
                    "label": "Interface Mode: ",
                    "options": ["full", "gateway", "access_point", "roaming", "boundary"],
                    "default": "full",
                    "validation": [],
                    "transform": lambda x: x
                },
                {
                    "config_key": "announce_cap",
                    "type": "edit",
                    "label": "Announce Cap: ",
                    "placeholder": "Default: 2.0",
                    "default": "",
                    "validation": ["float"],
                    "transform": lambda x: float(x) if x.strip() else 2.0
                }
            ])

        for option in COMMON_INTERFACE_OPTIONS:
            if option["type"] == "checkbox":
                widget = FormCheckbox(
                    config_key=option["config_key"],
                    label=option["label"],
                    state=option.get("default", False),
                    validation_types=option.get("validation", []),
                    transform=option.get("transform")
                )
            elif option["type"] == "dropdown":
                widget = FormDropdown(
                    config_key=option["config_key"],
                    label=option["label"],
                    options=option["options"],
                    default=option.get("default"),
                    validation_types=option.get("validation", []),
                    transform=option.get("transform")
                )
            else:
                widget = FormEdit(
                    config_key=option["config_key"],
                    caption="",
                    edit_text=str(option.get("default", "")),
                    placeholder=option.get("placeholder", ""),
                    validation_types=option.get("validation", []),
                    transform=option.get("transform")
                )

            self.common_fields[option["config_key"]] = {
                'label': option["label"],
                'widget': widget,
                'type': option["type"]
            }

    def _on_rnode_field_change(self, widget, new_value):
        if hasattr(self, 'rnode_calculator') and self.calculator_visible:
            self.rnode_calculator.update_calculation()

    def _build_form_layout(self, iface_fields):
        pile_items = []
        pile_items.append(urwid.Text(
            ("form_title", f"Add new {_get_interface_icon(self.parent.glyphset, self.iface_type)} {self.iface_type}"),
            align="center"))
        pile_items.append(urwid.Divider("─"))

        for key in ["name"] + [f["config_key"] for f in iface_fields]:
            field = self.fields[key]
            widget = field["widget"]

            # Special case for multitable and keyvaluepairs - they already have their own layout
            if isinstance(widget, (FormMultiTable, FormKeyValuePairs)):
                pile_items.append(urwid.Text(("key", field["label"]), align="left"))
                pile_items.append(widget)
                pile_items.append(urwid.Padding(widget.error_widget, left=2))
                continue

            field_pile = urwid.Pile([
                urwid.Columns([
                    (26, urwid.Text(("key", field["label"]), align="right")),
                    widget,
                ]),
                urwid.Padding(widget.error_widget, left=24)
            ])

            if self.iface_type in ["RNodeInterface", "RNodeMultiInterface", "SerialInterface", "AX25KISSInterface",
                                   "KISSInterface"] and key == "port":
                refresh_btn = urwid.Button("Refresh Ports", on_press=self.refresh_ports)
                refresh_btn = urwid.AttrMap(refresh_btn, "button_normal", focus_map="button_focus")
                refresh_row = urwid.Padding(refresh_btn, left=26, width=20)
                field_pile.contents.append((refresh_row, field_pile.options()))
                self.port_pile = field_pile

            pile_items.append(field_pile)

        self.more_options_visible = False
        self.more_options_button = urwid.Button("Show more options", on_press=self.toggle_more_options)
        self.more_options_button = urwid.AttrMap(self.more_options_button, "button_normal", focus_map="button_focus")
        self.more_options_widget = urwid.Pile([])

        self.ifac_options_visible = False
        self.ifac_options_button = urwid.Button("Show IFAC options", on_press=self.toggle_ifac_options)
        self.ifac_options_button = urwid.AttrMap(self.ifac_options_button, "button_normal", focus_map="button_focus")
        self.ifac_options_widget = urwid.Pile([])

        if self.iface_type in ["RNodeInterface"]:
            self.calculator_button = urwid.Button("Show On-Air Calculations", on_press=self.toggle_calculator)
            self.calculator_button = urwid.AttrMap(self.calculator_button, "button_normal", focus_map="button_focus")

        save_btn = urwid.Button("Save", on_press=self.on_save)
        back_btn = urwid.Button("Cancel", on_press=self.on_back)
        button_row = urwid.Columns([
            (urwid.WEIGHT, 0.45, save_btn),
            (urwid.WEIGHT, 0.1, urwid.Text("")),
            (urwid.WEIGHT, 0.45, back_btn),
        ])

        pile_items.extend([
            urwid.Divider(),
            self.more_options_button,
            self.more_options_widget,
        ])
        if self.iface_type in ["RNodeInterface"]:
            self.rnode_calculator = RNodeCalculator(self)
            self.calculator_visible = False
            self.calculator_widget = urwid.Pile([])
            pile_items.extend([
                self.calculator_button,
                self.calculator_widget,
            ])
        pile_items.extend([
            urwid.Divider("─"),
            button_row,
        ])

        return pile_items

    def toggle_more_options(self, button):
        if self.more_options_visible:
            self.more_options_widget.contents = []
            button.base_widget.set_label("Show more options")
            self.more_options_visible = False
        else:
            pile_contents = []

            if self.additional_fields:
                for key, field in self.additional_fields.items():
                    widget = field['widget']

                    if field['type'] == "checkbox":
                        centered_widget = urwid.Columns([
                            ('weight', 1, urwid.Text("")),
                            ('pack', widget),
                            ('weight', 1, urwid.Text(""))
                        ])
                        field_pile = urwid.Pile([
                            centered_widget,
                            urwid.Padding(widget.error_widget, left=24)
                        ])
                    else:
                        field_pile = urwid.Pile([
                            urwid.Columns([
                                (26, urwid.Text(("key", field["label"]), align="right")),
                                widget
                            ]),
                            urwid.Padding(widget.error_widget, left=24)
                        ])

                    pile_contents.append(field_pile)

                if self.additional_fields and self.common_fields:
                    pile_contents.append(urwid.Divider("─"))

            if self.common_fields:
                for key, field in self.common_fields.items():
                    widget = field['widget']

                    if field['type'] == "checkbox":
                        centered_widget = urwid.Columns([
                            ('weight', 1, urwid.Text("")),
                            ('pack', widget),
                            ('weight', 1, urwid.Text(""))
                        ])
                        field_pile = urwid.Pile([
                            centered_widget,
                            urwid.Padding(widget.error_widget, left=24)
                        ])
                    else:
                        field_pile = urwid.Pile([
                            urwid.Columns([
                                (26, urwid.Text(("key", field["label"]), align="right")),
                                widget
                            ]),
                            urwid.Padding(widget.error_widget, left=24)
                        ])

                    pile_contents.append(field_pile)

            if pile_contents:
                self.more_options_widget.contents = [(w, self.more_options_widget.options()) for w in pile_contents]
            else:
                self.more_options_widget.contents = [(
                    urwid.Text("No additional options available", align="center"),
                    self.more_options_widget.options()
                )]

            button.base_widget.set_label("Hide more options")
            self.more_options_visible = True

    def toggle_ifac_options(self, button):
        if self.ifac_options_visible:
            self.ifac_options_widget.contents = []
            button.base_widget.set_label("Show IFAC options")
            self.ifac_options_visible = False
        else:
            dummy = urwid.Text("IFAC (Interface Access Codes)", align="left")
            self.ifac_options_widget.contents = [(dummy, self.more_options_widget.options())]
            button.base_widget.set_label("Hide IFAC options")
            self.ifac_options_visible = True

    def toggle_calculator(self, button):
        if self.calculator_visible:
            self.calculator_widget.contents = []
            button.base_widget.set_label("Show On-Air Calculations")
            self.calculator_visible = False
        else:
            calculator_contents = [self.rnode_calculator]

            self.calculator_widget.contents = [(w, self.calculator_widget.options()) for w in calculator_contents]

            self.rnode_calculator.update_calculation()

            button.base_widget.set_label("Hide On-Air Calculations")
            self.calculator_visible = True

    def refresh_ports(self, button):
        if self.port_pile is not None:
            # Get fresh port config
            port_field = get_port_field()

            if port_field["type"] == "dropdown":
                widget = FormDropdown(
                    config_key=port_field["config_key"],
                    label=port_field["label"],
                    options=port_field["options"],
                    default=port_field.get("default"),
                    validation_types=port_field.get("validation", []),
                    transform=port_field.get("transform")
                )
            else:
                widget = FormEdit(
                    config_key=port_field["config_key"],
                    caption="",
                    edit_text=port_field.get("default", ""),
                    placeholder=port_field.get("placeholder", ""),
                    validation_types=port_field.get("validation", []),
                    transform=port_field.get("transform")
                )

            self.fields["port"] = {
                'label': port_field["label"],
                'widget': widget
            }

            columns = urwid.Columns([
                (26, urwid.Text(("key", port_field["label"]), align="right")),
                widget
            ])
            self.port_pile.contents[0] = (columns, self.port_pile.options())

            self.port_pile.contents[1] = (urwid.Padding(widget.error_widget, left=24), self.port_pile.options())

    def validate_all(self):
        all_valid = True

        # validate main fields
        for field in self.fields.values():
            if not field["widget"].validate():
                all_valid = False

        # validate additional iface fields
        for field in self.additional_fields.values():
            if not field["widget"].validate():
                all_valid = False

        # validate common fields
        for field in self.common_fields.values():
            if not field["widget"].validate():
                all_valid = False

        return all_valid

    def on_save(self, button):
        all_valid = self.validate_all()

        name = self.fields['name']["widget"].get_value() or "Untitled interface"

        existing_interfaces = self.parent.app.rns.config['interfaces']
        if name in existing_interfaces:
            self.fields['name']["widget"].error = f"Interface name '{name}' already exists"
            self.fields['name']["widget"].error_widget.set_text(("error", self.fields['name']["widget"].error))
            all_valid = False

        if not all_valid:
            return

        if self.iface_type == "CustomInterface":
            custom_type = self.fields.get('type', {}).get('widget').get_value()
            interface_config = {
                "type": custom_type,
                "interface_enabled": True
            }
        else:
            interface_config = {
                "type": self.iface_type,
                "interface_enabled": True
            }

        for field_key, field in self.fields.items():
            if field_key not in ["name", "custom_parameters", "type"]:
                widget = field["widget"]
                value = widget.get_value()

                if field_key == "subinterfaces" and self.iface_type == "RNodeMultiInterface" and isinstance(value,
                                                                                                            dict):
                    for subname, subconfig in value.items():
                        interface_config[f"{subname}"] = subconfig
                elif value is not None and value != "":
                    interface_config[widget.config_key] = value

        if self.iface_type == "CustomInterface" and "custom_parameters" in self.fields:
            custom_params = self.fields["custom_parameters"]["widget"].get_value()
            if isinstance(custom_params, dict):
                for param_key, param_value in custom_params.items():
                    interface_config[param_key] = param_value

        for field_key, field in self.additional_fields.items():
            widget = field["widget"]
            value = widget.get_value()
            if value is not None and value != "":
                interface_config[widget.config_key] = value

        for field_key, field in self.common_fields.items():
            widget = field["widget"]
            value = widget.get_value()
            if value is not None and value != "":
                interface_config[widget.config_key] = value

        try:
            interfaces = self.parent.app.rns.config['interfaces']
            interfaces[name] = interface_config
            self.parent.app.rns.config.write()

            display_type = custom_type if self.iface_type == "CustomInterface" else self.iface_type

            new_item = SelectableInterfaceItem(
                parent=self.parent,
                name=name,
                is_connected=False,  # will always be false until restart
                is_enabled=True,
                iface_type=display_type,
                tx=0,
                rx=0,
                icon=_get_interface_icon(self.parent.glyphset, display_type),
                iface_options=interface_config
            )

            self.parent.interface_items.append(new_item)
            self.parent._rebuild_list()

            self.show_message(f"Interface {name} added. Restart NomadNet to start using this interface")

        except Exception as e:
            print(f"Error saving interface: {str(e)}")
            self.show_message(f"Error: {str(e)}", title="Error")

    def on_back(self, button):
        self.parent.switch_to_list()

    def show_message(self, message, title="Notice"):
        def dismiss_dialog(button):
            self.parent.switch_to_list()

        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text(message, align="center"),
                urwid.Divider(),
                urwid.Button("OK", on_press=dismiss_dialog)
            ]),
            title=title
        )

        overlay = urwid.Overlay(
            dialog,
            self.parent.interfaces_display,
            align='center',
            width=100,
            valign='middle',
            height=8,
            min_width=1,
            min_height=1
        )

        self.parent.widget = overlay
        self.parent.app.ui.main_display.update_active_sub_display()


class EditInterfaceView(AddInterfaceView):
    def __init__(self, parent, iface_name):
        self.parent = parent
        self.iface_name = iface_name

        self.interface_config = parent.app.rns.config['interfaces'][iface_name]
        config_type = self.interface_config.get("type", "Unknown")

        # check if this is a custom interface type
        known_types = list(INTERFACE_FIELDS.keys())
        if config_type not in known_types:
            self.original_type = config_type
            self.iface_type = "CustomInterface"
        else:
            self.original_type = None
            self.iface_type = config_type

        super().__init__(parent, self.iface_type)

        self.overlay.top_w.title_widget.set_text(f"Edit Interface: {iface_name}")

        self._populate_form_fields()

    def _populate_form_fields(self):
        self.fields['name']['widget'].edit_text = self.iface_name

        if self.original_type and self.iface_type == "CustomInterface":
            if "type" in self.fields:
                self.fields["type"]["widget"].edit_text = self.original_type

            if "custom_parameters" in self.fields:
                custom_params = {}
                standard_keys = ["type", "interface_enabled", "enabled", "description",
                                 "network_name", "bitrate", "passphrase", "ifac_size",
                                 "mode", "outgoing", "announce_cap"]

                for key, value in self.interface_config.items():
                    if key not in standard_keys:
                        custom_params[key] = value

                self.fields["custom_parameters"]["widget"].set_value(custom_params)

        for key, field in self.fields.items():
            if key not in ['name', 'type', 'custom_parameters']:
                widget = field['widget']

                if key == "subinterfaces" and isinstance(widget, FormMultiTable):
                    self._populate_subinterfaces(widget)
                    continue

                if key in self.interface_config:
                    value = self.interface_config[key]

                    if key == 'frequency':
                        value = float(value) / 1000000
                        value = f"{value:.6f}".rstrip('0').rstrip('.') if '.' in f"{value:.6f}" else f"{value}"

                    self._set_field_value(widget, value)

        for key, field in self.additional_fields.items():
            if key in self.interface_config:
                self._set_field_value(field['widget'], self.interface_config[key])

        for key, field in self.common_fields.items():
            if key in self.interface_config:
                self._set_field_value(field['widget'], self.interface_config[key])

    def _set_field_value(self, widget, value):
        if hasattr(widget, 'edit_text'):
            widget.edit_text = str(value)
        elif hasattr(widget, 'set_state'):
            checkbox_state = value if isinstance(value, bool) else value.strip().lower() not in (
                'false', 'off', 'no', '0')
            widget.set_state(checkbox_state)
        elif isinstance(widget, FormDropdown):
            str_value = str(value)
            if str_value in widget.options:
                widget.selected = str_value
                widget.main_button.base_widget.set_text(str_value)
            else:
                # Try to match after transform
                for opt in widget.options:
                    try:
                        if widget.transform(opt) == value:
                            widget.selected = opt
                            widget.main_button.base_widget.set_text(opt)
                            break
                    except:
                        pass
        elif isinstance(widget, FormMultiList):
            self._populate_multilist(widget, value)

    def _populate_multilist(self, widget, value):
        items = []
        if isinstance(value, str):
            items = [item.strip() for item in value.split(',') if item.strip()]
        elif isinstance(value, list):
            items = value

        while len(widget.entries) > 1:
            widget.remove_entry(None, widget.entries[-1])

        if items:
            first_entry = widget.entries[0]
            first_edit = first_entry.contents[0][0]
            if len(items) > 0:
                first_edit.edit_text = items[0]

            for i in range(1, len(items)):
                widget.add_entry(None)
                entry = widget.entries[i]
                edit_widget = entry.contents[0][0]
                edit_widget.edit_text = items[i]

    def _populate_subinterfaces(self, widget):
        subinterfaces = {}

        for key, value in self.interface_config.items():
            if isinstance(value, dict):
                if key.startswith('[[[') and key.endswith(']]]'):
                    clean_key = key[3:-3]  # removes [[[...]]]
                    subinterfaces[clean_key] = value
                elif key not in ["type", "interface_enabled", "enabled", "port",
                                 "id_callsign", "id_interval"]:
                    subinterfaces[key] = value

        if subinterfaces:
            widget.set_value(subinterfaces)

    def on_save(self, button):
        if not self.validate_all():
            return

        new_name = self.fields['name']["widget"].get_value() or self.iface_name

        if new_name != self.iface_name and new_name in self.parent.app.rns.config['interfaces']:
            self.fields['name']["widget"].error = f"Interface name '{new_name}' already exists"
            self.fields['name']["widget"].error_widget.set_text(("error", self.fields['name']["widget"].error))
            return

        if self.iface_type == "CustomInterface":
            interface_type = self.fields.get('type', {}).get('widget').get_value()
        else:
            interface_type = self.iface_type

        updated_config = {
            "type": interface_type,
            "interface_enabled": True
        }

        for field_key, field in self.fields.items():
            if field_key not in ["name", "custom_parameters", "type", "subinterfaces"]:
                widget = field["widget"]
                value = widget.get_value()
                if value is not None and value != "":
                    updated_config[widget.config_key] = value

        if self.iface_type == "CustomInterface" and "custom_parameters" in self.fields:
            custom_params = self.fields["custom_parameters"]["widget"].get_value()
            if isinstance(custom_params, dict):
                for param_key, param_value in custom_params.items():
                    updated_config[param_key] = param_value

        elif self.iface_type == "RNodeMultiInterface" and "subinterfaces" in self.fields:
            subinterfaces = self.fields["subinterfaces"]["widget"].get_value()
            for subname, subconfig in subinterfaces.items():
                updated_config[subname] = subconfig

        for field_key, field in self.additional_fields.items():
            widget = field["widget"]
            value = widget.get_value()
            if value is not None and value != "":
                updated_config[widget.config_key] = value

        for field_key, field in self.common_fields.items():
            widget = field["widget"]
            value = widget.get_value()
            if value is not None and value != "":
                updated_config[widget.config_key] = value

        try:
            interfaces = self.parent.app.rns.config['interfaces']

            if new_name != self.iface_name:
                del interfaces[self.iface_name]
                interfaces[new_name] = updated_config

                for i, item in enumerate(self.parent.interface_items):
                    if item.name == self.iface_name:
                        self.parent.interface_items[i].name = new_name
                        break
            else:
                interfaces[self.iface_name] = updated_config

            self.parent.app.rns.config.write()

            display_type = interface_type

            for item in self.parent.interface_items:
                if item.name == new_name:
                    item.iface_type = display_type
                    break

            self.parent._rebuild_list()
            self.show_message(f"Interface {new_name} updated. Restart NomadNet for these changes to take effect")

        except Exception as e:
            print(f"Error saving interface: {str(e)}")
            self.show_message(f"Error updating interface: {str(e)}", title="Error")


class ShowInterface(urwid.WidgetWrap):
    def __init__(self, parent, iface_name):
        self.parent = parent
        self.iface_name = iface_name
        self.started = False
        self.g = self.parent.app.ui.glyphs

        # get config
        self.interface_config = self.parent.app.rns.config['interfaces'][iface_name]
        iface_type = self.interface_config.get("type", "Unknown")

        self.parent.shortcuts_display.set_show_interface_shortcuts()

        self.config_rows = []

        screen_cols, _ = _get_cols_rows()
        margin = 22
        if screen_cols >= 145:
            self.history_length = screen_cols//2-margin
        else:
            self.history_length = screen_cols-(margin+2)

        # get interface stats
        interface_stats = self.parent.app.rns.get_interface_stats()
        stats_lookup = {iface['short_name']: iface for iface in interface_stats['interfaces']}
        self.stats = stats_lookup.get(iface_name, {})

        self.tx = self.stats.get("txb", 0)
        self.rx = self.stats.get("rxb", 0)
        self.is_connected = self.stats.get("status", False)
        self.is_enabled = (str(self.interface_config.get("enabled")).lower() != 'false' and
                           str(self.interface_config.get("interface_enabled")).lower() != 'false')

        header_content = [
            urwid.Text(("interface_title", f"Interface: {iface_name}"), align="center"),
            urwid.Divider("=")
        ]
        header = urwid.Pile(header_content)

        self.edit_button = urwid.Button("Edit", on_press=self.on_edit)
        self.back_button = urwid.Button("Back", on_press=self.on_back)

        self.toggle_button = urwid.Button(
            "Disable" if self.is_enabled else "Enable",
            on_press=self.on_toggle_enabled
        )

        button_row = urwid.Columns([
            (urwid.WEIGHT, 0.3, self.back_button),
            (urwid.WEIGHT, 0.05, urwid.Text("")),
            (urwid.WEIGHT, 0.3, self.toggle_button),
            (urwid.WEIGHT, 0.05, urwid.Text("")),
            (urwid.WEIGHT, 0.3, self.edit_button),
        ])

        footer_content = [
            urwid.Divider("="),
            button_row
        ]
        footer = urwid.Pile(footer_content)

        # status widgets
        self.status_text = urwid.Text(("connected_status" if self.is_enabled else "disconnected_status",
                                       "Enabled" if self.is_enabled else "Disabled"))

        self.status_indicator = urwid.Text(("connected_status" if self.is_enabled else "disconnected_status",
                                            self.parent.g['selected'] if self.is_enabled else self.parent.g[
                                                'unselected']))

        self.connection_text = urwid.Text(("connected_status" if self.is_connected else "disconnected_status",
                                           "Connected" if self.is_connected else "Disconnected"))

        self.info_rows = [
            urwid.Columns([
                (10, urwid.Text(("key", "Type:"))),
                urwid.Text(("value", f"{_get_interface_icon(self.parent.glyphset, iface_type)} {iface_type}")),
            ]),
            urwid.Columns([
                (10, urwid.Text(("key", "Status:"))),
                (4, self.status_indicator),
                (8, self.status_text),
                (3, urwid.Text(" | ")),
                self.connection_text,
            ]),
            urwid.Divider("-")
        ]

        self.tx_text = urwid.Text(("value", format_bytes(self.tx)))
        self.rx_text = urwid.Text(("value", format_bytes(self.rx)))

        self.stat_row = urwid.Columns([
            (10, urwid.Text(("key", "TX:"))),
            (15, self.tx_text),
            (10, urwid.Text(("key", "RX:"))),
            self.rx_text,
        ])

        self.info_rows.append(self.stat_row)
        self.info_rows.append(urwid.Divider("-"))

        self.bandwidth_chart = InterfaceBandwidthChart(history_length=self.history_length, glyphset=self.parent.glyphset)
        self.bandwidth_chart.update(self.rx, self.tx)

        self.rx_chart_text = urwid.Text("Loading RX data...", align='left')
        self.tx_chart_text = urwid.Text("Loading TX data...", align='left')
        self.rx_peak_text = urwid.Text("Peak: 0 B/s", align='right')
        self.tx_peak_text = urwid.Text("Peak: 0 B/s", align='right')

        self.rx_box = urwid.LineBox(
            urwid.Pile([
                urwid.AttrMap(self.rx_chart_text, "rx"),
                self.rx_peak_text
            ]),
            title="RX Traffic (60s)"
        )

        self.tx_box = urwid.LineBox(
            urwid.Pile([
                urwid.AttrMap(self.tx_chart_text, "tx"),
                self.tx_peak_text
            ]),
            title="TX Traffic (60s)"
        )

        self.horizontal_charts = urwid.Columns([
            (urwid.WEIGHT, 1, self.rx_box),
            (urwid.WEIGHT, 1, self.tx_box)
        ])

        self.vertical_charts = urwid.Pile([
            self.rx_box,
            self.tx_box
        ])

        self.disconnected_message = urwid.Filler(
            urwid.Text(("disconnected_status",
                        "Charts not available - Interface is not connected"),
                       align="center"),
            valign="top"
        )
        self.disconnected_box = urwid.LineBox(self.disconnected_message, title="Bandwidth Charts")

        self.charts_widget = self.vertical_charts
        self.is_horizontal = False

        screen_cols, _ = _get_cols_rows()
        # RNS.log(screen_cols)
        if screen_cols >= 145:
            self.charts_widget = self.horizontal_charts
            self.is_horizontal = True

        if not self.is_connected:
            self.charts_widget = self.disconnected_box

        connection_params = []
        radio_params = []
        network_params = []
        ifac_params = []
        other_params = []

        # Sort parameters into groups
        for key, value in self.interface_config.items():
            # skip empty
            if value is None or value == "":
                continue

            # Skip these keys as their shown elsewhere
            if key in ["type", "interface_enabled", "enabled", 'selected_interface_mode', 'name']:
                continue

            # Connection parameters
            elif key in ["port", "listen_ip", "listen_port", "target_host", "target_port", "device"]:
                connection_params.append((key, value))

            # Radio parameters
            elif key in ["frequency", "bandwidth", "spreadingfactor", "codingrate", "txpower"]:
                radio_params.append((key, value))

            # Network parameters
            elif key in ["network_name", "bitrate", "peers", "group_id", "multicast_address_type",
                         "discovery_scope", "announce_cap", "mode"]:
                network_params.append((key, value))

            # IFAC parameters
            elif key in ["passphrase", "ifac_size", "ifac_netname", "ifac_netkey"]:
                ifac_params.append((key, value))

            else:
                other_params.append((key, value))

        def create_param_row(key, value):
            if isinstance(value, bool):
                value_str = "Yes" if value else "No"
            elif key == "frequency":
                int_value = int(value)
                value_str = f"{int_value / 1000000:.3f} MHz"
            elif key == "bandwidth":
                int_value = int(value)
                value_str = f"{int_value / 1000:.1f} kHz"
            elif key == "passphrase":
                value_str = len(value)*"*"
            else:
                value_str = str(value)
            # format display keys: "listen_port" => Listen Port
            display_key = key.replace('_', ' ').title()

            return urwid.Columns([
                (18, urwid.Text(("key", f"{display_key}:"))),
                urwid.Text(("value", value_str)),
            ])

        if connection_params:
            connection_params.sort(key=lambda x: x[0])
            self.config_rows.append(urwid.Text(("interface_title", "Connection Parameters"), align="left"))
            for key, value in connection_params:
                self.config_rows.append(create_param_row(key, value))
            self.config_rows.append(urwid.Divider("-"))

        if radio_params:
            radio_params.sort(key=lambda x: x[0])
            self.config_rows.append(urwid.Text(("interface_title", "Radio Parameters"), align="left"))
            for key, value in radio_params:
                self.config_rows.append(create_param_row(key, value))
            self.config_rows.append(urwid.Divider("-"))

        if network_params:
            network_params.sort(key=lambda x: x[0])
            self.config_rows.append(urwid.Text(("interface_title", "Network Parameters"), align="left"))
            for key, value in network_params:
                self.config_rows.append(create_param_row(key, value))
            self.config_rows.append(urwid.Divider("-"))

        if ifac_params:
            ifac_params.sort(key=lambda x: x[0])
            self.config_rows.append(urwid.Text(("interface_title", "IFAC Parameters"), align="left"))
            for key, value in ifac_params:
                self.config_rows.append(create_param_row(key, value))
            self.config_rows.append(urwid.Divider("-"))

        if other_params:
            other_params.sort(key=lambda x: x[0])
            self.config_rows.append(urwid.Text(("interface_title", "Additional Parameters"), align="left"))
            for key, value in other_params:
                self.config_rows.append(create_param_row(key, value))
            self.config_rows.append(urwid.Divider("-"))

        if not self.config_rows:
            self.config_rows.append(urwid.Text("No additional parameters", align="center"))

        body_content = []
        body_content.extend(self.info_rows)
        body_content.append(
            self.charts_widget)
        body_content.append(urwid.Divider("-"))
        body_content.extend(self.config_rows)

        body_pile = urwid.Pile(body_content)
        body_padding = urwid.Padding(body_pile, left=2, right=2)

        body = urwid.ListBox(urwid.SimpleListWalker([body_padding]))

        self.frame = urwid.Frame(
            body=body,
            header=header,
            footer=footer
        )

        self.content_box = urwid.LineBox(self.frame)

        super().__init__(self.content_box)

    def update_status_display(self):
        if self.is_enabled:
            self.status_indicator.set_text(("connected_status", self.parent.g['selected']))
            self.status_text.set_text(("connected_status", "Enabled"))
        else:
            self.status_indicator.set_text(("disconnected_status", self.parent.g['unselected']))
            self.status_text.set_text(("disconnected_status", "Disabled"))

    def update_connection_display(self, is_connected):
        old_connection_state = self.is_connected
        self.is_connected = is_connected

        self.connection_text.set_text(("connected_status" if self.is_connected else "disconnected_status",
                                       "Connected" if self.is_connected else "Disconnected"))

        if old_connection_state != self.is_connected:
            body_pile = self.frame.body.body[0].original_widget

            chart_index = None
            for i, (widget, options) in enumerate(body_pile.contents):
                if (widget == self.horizontal_charts or
                        widget == self.vertical_charts or
                        widget == self.disconnected_box):
                    chart_index = i
                    break

            if chart_index is not None:
                if self.is_connected:
                    new_widget = self.horizontal_charts if self.is_horizontal else self.vertical_charts
                    if not self.started:
                        self.start()
                else:
                    new_widget = self.disconnected_box
                    self.started = False

                body_pile.contents[chart_index] = (new_widget, body_pile.options())

    def on_toggle_enabled(self, button):
        action = "disable" if self.is_enabled else "enable"

        def on_confirm_yes(confirm_button):
            self.parent.app.ui.main_display.frame.body = self.parent.app.ui.main_display.sub_displays.active().widget

            self.is_enabled = not self.is_enabled

            self.toggle_button.set_label("Disable" if self.is_enabled else "Enable")

            if "interface_enabled" in self.interface_config:
                self.interface_config["interface_enabled"] = self.is_enabled
            else:
                self.interface_config["enabled"] = self.is_enabled

            try:
                interfaces = self.parent.app.rns.config['interfaces']

                interfaces[self.iface_name] = self.interface_config

                self.parent.app.rns.config.write()

                self.update_status_display()

                for item in self.parent.interface_items:
                    if item.name == self.iface_name:
                        item.is_enabled = self.is_enabled
                        item.update_status_display()

                if hasattr(self.parent.app.ui, 'loop') and self.parent.app.ui.loop is not None:
                    self.parent.app.ui.loop.draw_screen()

                self.show_restart_required_message()

            except Exception as e:
                self.show_error_message(f"Error updating interface: {str(e)}")

        def on_confirm_no(confirm_button):
            self.parent.app.ui.main_display.frame.body = self.parent.app.ui.main_display.sub_displays.active().widget

        confirm_text = urwid.Text((
            "interface_title",
            f"Are you sure you want to {action} the {self.iface_name} interface?"
        ), align="center")

        yes_button = urwid.Button("Yes", on_press=on_confirm_yes)
        no_button = urwid.Button("No", on_press=on_confirm_no)

        buttons_row = urwid.Columns([
            (urwid.WEIGHT, 0.45, yes_button),
            (urwid.WEIGHT, 0.1, urwid.Text("")),
            (urwid.WEIGHT, 0.45, no_button),
        ])

        pile = urwid.Pile([
            confirm_text,
            urwid.Divider(),
            buttons_row
        ])

        dialog = DialogLineBox(pile, title="Confirm")

        overlay = urwid.Overlay(
            dialog,
            self.parent.app.ui.main_display.frame.body,
            align='center',
            width=50,
            valign='middle',
            height=7
        )

        self.parent.app.ui.main_display.frame.body = overlay

    def show_restart_required_message(self):

        def dismiss_dialog(button):
            self.parent.app.ui.main_display.frame.body = self.parent.app.ui.main_display.sub_displays.active().widget

        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text(
                    f"Interface {self.iface_name} has been " +
                    ("enabled" if self.is_enabled else "disabled") +
                    ".\nRestart required for changes to take effect.",
                    align="center"
                ),
                urwid.Divider(),
                urwid.Button("OK", on_press=dismiss_dialog)
            ]),
            title="Notice"
        )

        overlay = urwid.Overlay(
            dialog,
            self.parent.app.ui.main_display.frame.body,
            align='center',
            width=50,
            valign='middle',
            height=8
        )

        self.parent.app.ui.main_display.frame.body = overlay

    def show_error_message(self, message):

        def dismiss_dialog(button):
            self.parent.app.ui.main_display.frame.body = self.parent.app.ui.main_display.sub_displays.active().widget

        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text(message, align="center"),
                urwid.Divider(),
                urwid.Button("OK", on_press=dismiss_dialog)
            ]),
            title="Error"
        )

        overlay = urwid.Overlay(
            dialog,
            self.parent.app.ui.main_display.frame.body,
            align='center',
            width=50,
            valign='middle',
            height=8
        )

        self.parent.app.ui.main_display.frame.body = overlay

    def keypress(self, size, key):
        if key == 'tab':
            if self.frame.focus_position == 'body':
                self.frame.focus_position = 'footer'
                footer_pile = self.frame.footer
                if isinstance(footer_pile, urwid.Pile):
                    footer_pile.focus_position = 1  # button row
                    button_row = footer_pile.contents[1][0]
                    if isinstance(button_row, urwid.Columns):
                        button_row.focus_position = 0
                return None
            elif self.frame.focus_position == 'footer':
                footer_pile = self.frame.footer
                if isinstance(footer_pile, urwid.Pile):
                    button_row = footer_pile.contents[1][0]
                    if isinstance(button_row, urwid.Columns):
                        # If on first button (Back), move to Toggle button
                        if button_row.focus_position == 0:
                            button_row.focus_position = 2  # skip spacer
                            return None
                        # If on toggle button, move to Edit button
                        elif button_row.focus_position == 2:
                            button_row.focus_position = 4
                            return None
                        # if on edit button wrap back to toggle button
                        elif button_row.focus_position == 4:
                            button_row.focus_position = 0
                            return None
        elif key == 'shift tab':
            if self.frame.focus_position == 'footer':
                self.frame.focus_position = 'body'
                return None
            elif self.frame.focus_position == 'footer':
                footer_pile = self.frame.footer
                if isinstance(footer_pile, urwid.Pile):
                    button_row = footer_pile.contents[1][0]
                    if isinstance(button_row, urwid.Columns):
                        if button_row.focus_position == 4:  # edit button
                            button_row.focus_position = 2  # toggle button
                            return None
                        elif button_row.focus_position == 2:
                            button_row.focus_position = 0  # back button
                            return None
                        elif button_row.focus_position == 0:  # back button
                            self.frame.focus_position = 'body'
                            return None
        elif key == 'down':
            if self.frame.focus_position == 'body':
                result = super().keypress(size, key)
                # if the key wasn't consumed, we're at the bottom
                if result == 'down':
                    self.frame.focus_position = 'footer'
                    footer_pile = self.frame.footer
                    if isinstance(footer_pile, urwid.Pile):
                        footer_pile.focus_position = 1  # button row
                        button_row = footer_pile.contents[1][0]
                        if isinstance(button_row, urwid.Columns):
                            button_row.focus_position = 0  # focus on back button
                    return None
                return result
        elif key == 'up':
            if self.frame.focus_position == 'footer':
                self.frame.focus_position = 'body'
                listbox = self.frame.body
                if hasattr(listbox, 'body') and len(listbox.body) > 0:
                    listbox.focus_position = len(listbox.body) - 1
                return None
            elif self.frame.focus_position == 'body':
                result = super().keypress(size, key)
                # if the key wasn't consumed, we're at the top
                if result == 'up':
                    pass
                return result
        elif key == "h" and self.is_connected:  # horizontal layout
            if not self.is_horizontal:
                self.switch_to_horizontal()
                return None
        elif key == "v" and self.is_connected:  # vertical layout
            if self.is_horizontal:
                self.switch_to_vertical()
                return None

        return super().keypress(size, key)

    def switch_to_horizontal(self):
        if not self.is_connected:
            return

        self.is_horizontal = True

        body_pile = self.frame.body.body[0].original_widget
        for i, (widget, options) in enumerate(body_pile.contents):
            if widget == self.vertical_charts:
                body_pile.contents[i] = (self.horizontal_charts, options)
                self.charts_widget = self.horizontal_charts
                break

    def switch_to_vertical(self):
        if not self.is_connected:
            return

        self.is_horizontal = False
        body_pile = self.frame.body.body[0].original_widget
        for i, (widget, options) in enumerate(body_pile.contents):
            if widget == self.horizontal_charts:
                body_pile.contents[i] = (self.vertical_charts, options)
                self.charts_widget = self.vertical_charts
                break

    def start(self):
        if not self.started and self.is_connected:
            self.started = True
            self.parent.app.ui.loop.set_alarm_in(1, self.update_bandwidth_charts)

    def update_bandwidth_charts(self, loop, user_data):
        if not self.started:
            return

        try:
            interface_stats = self.parent.app.rns.get_interface_stats()
            stats_lookup = {iface['short_name']: iface for iface in interface_stats['interfaces']}
            stats = stats_lookup.get(self.iface_name, {})

            tx = stats.get("txb", self.tx)
            rx = stats.get("rxb", self.rx)

            new_connection_status = stats.get("status", False)
            if new_connection_status != self.is_connected:
                self.update_connection_display(new_connection_status)

                if not self.is_connected:
                    return

            self.tx_text.set_text(("value", format_bytes(tx)))
            self.rx_text.set_text(("value", format_bytes(rx)))

            self.bandwidth_chart.update(rx, tx)

            rx_chart, tx_chart, peak_rx, peak_tx = self.bandwidth_chart.get_charts(height=8)

            self.rx_chart_text.set_text(rx_chart)
            self.tx_chart_text.set_text(tx_chart)
            self.rx_peak_text.set_text(f"Peak: {peak_rx}")
            self.tx_peak_text.set_text(f"Peak: {peak_tx}")

            self.tx = tx
            self.rx = rx
        except Exception as e:
            if not hasattr(self.parent,
                           'disconnect_overlay') or self.parent.widget is not self.parent.disconnect_overlay:
                dialog_text = urwid.Pile([
                    urwid.Text(("disconnected_status", "(!) RNS Instance Disconnected"), align="center"),
                    urwid.Text("Waiting to Reconnect...", align="center")
                ])
                dialog_content = urwid.Filler(dialog_text)
                dialog_box = urwid.LineBox(dialog_content)

                self.parent.disconnect_overlay = urwid.Overlay(
                    dialog_box,
                    self,
                    align='center',
                    width=35,
                    valign='middle',
                    height=4
                )

                self.parent.widget = self.parent.disconnect_overlay
                self.parent.app.ui.main_display.update_active_sub_display()
                self.started = False
        finally:
            if self.started:
                loop.set_alarm_in(1, self.update_bandwidth_charts)

    def on_back(self, button):
        self.started = False
        self.parent.switch_to_list()

    def on_edit(self, button):
        self.started = False
        self.parent.switch_to_edit_interface(self.iface_name)

### MAIN DISPLAY ###
class InterfaceDisplay:
    def __init__(self, app):
        self.app = app
        self.started = False
        self.interface_items = []
        self.glyphset = self.app.config["textui"]["glyphs"]
        self.g = self.app.ui.glyphs

        self.terminal_cols, self.terminal_rows = _get_cols_rows()
        self.iface_row_offset = 4
        self.list_rows = self.terminal_rows - self.iface_row_offset

        interfaces = app.rns.config['interfaces']
        processed_interfaces = {}

        for interface_name, interface in interfaces.items():
            interface_data = interface.copy()

            # handle sub-interfaces for RNodeMultiInterface
            if interface_data.get("type") == "RNodeMultiInterface":
                sub_interfaces = []
                for sub_name, sub_config in interface_data.items():
                    if sub_name not in {"type", "port", "interface_enabled", "selected_interface_mode",
                                        "configured_bitrate"}:
                        if isinstance(sub_config, dict):
                            sub_config["name"] = sub_name
                            sub_interfaces.append(sub_config)

                # add sub-interfaces to the main interface data
                interface_data["sub_interfaces"] = sub_interfaces

                for sub in sub_interfaces:
                    del interface_data[sub["name"]]

            processed_interfaces[interface_name] = interface_data

        interface_stats = app.rns.get_interface_stats()
        stats_lookup = {interface['short_name']: interface for interface in interface_stats['interfaces']}
        # print(stats_lookup)
        for interface_name, interface_data in processed_interfaces.items():
            # configobj false values
            is_enabled = str(interface_data.get("enabled")).lower() not in ('false', 'off', 'no', '0') and str(interface_data.get("interface_enabled")).lower() not in ('false', 'off', 'no', '0')

            iface_type = interface_data.get("type", "Unknown")
            icon = _get_interface_icon(self.glyphset, iface_type)

            stats_for_interface = stats_lookup.get(interface_name)

            if stats_for_interface:
                tx = stats_for_interface.get("txb", 0)
                rx = stats_for_interface.get("rxb", 0)
                is_connected = stats_for_interface["status"]
            else:
                tx = 0
                rx = 0
                is_connected = False

            item = SelectableInterfaceItem(
                parent=self,
                name=interface_data.get("name", interface_name),
                is_connected=is_connected,
                is_enabled=is_enabled,
                iface_type=iface_type,
                tx=tx,
                rx=rx,
                icon=icon
            )

            self.interface_items.append(item)

        interface_header = urwid.Text(("interface_title", "Interfaces"), align="center")
        if len(self.interface_items) == 0:
            interface_header = urwid.Text(
                ("interface_title", "No interfaces found. Press Ctrl + A to add a new interface "), align="center")


        list_contents = [
            interface_header,
            urwid.Divider(),
        ] + self.interface_items

        self.list_walker = urwid.SimpleFocusListWalker(list_contents)
        self.list_box = urwid.ListBox(self.list_walker)

        self.box_adapter = urwid.BoxAdapter(self.list_box, self.list_rows)


        pile = urwid.Pile([self.box_adapter])
        self.interfaces_display = InterfaceFiller(pile, self.app)
        self.shortcuts_display = InterfaceDisplayShortcuts(self.app)
        self.widget = self.interfaces_display

    def start(self):
        # started from Main.py
        self.started = True
        self.app.ui.loop.set_alarm_in(1, self.poll_stats)
        self.app.ui.loop.set_alarm_in(5, self.check_terminal_size)

    def switch_to_edit_interface(self, iface_name):
        self.edit_interface_view = EditInterfaceView(self, iface_name)
        self.widget = self.edit_interface_view
        self.app.ui.main_display.update_active_sub_display()

    def edit_selected_interface(self):
        focus_widget, focus_position = self.box_adapter._original_widget.body.get_focus()

        if not isinstance(focus_widget, SelectableInterfaceItem):
            return

        selected_item = focus_widget
        interface_name = selected_item.name

        self.switch_to_edit_interface(interface_name)

    def check_terminal_size(self, loop, user_data):
        new_cols, new_rows = _get_cols_rows()

        if new_rows != self.terminal_rows or new_cols != self.terminal_cols:
            self.terminal_cols, self.terminal_rows = new_cols, new_rows
            self.list_rows = self.terminal_rows - self.iface_row_offset

            self.box_adapter.height = self.list_rows

            loop.draw_screen()

        if self.started:
            loop.set_alarm_in(5, self.check_terminal_size)

    def poll_stats(self, loop, user_data):
        try:
            if hasattr(self, 'disconnect_overlay') and self.widget is self.disconnect_overlay:
                self.widget = self.interfaces_display
                self.app.ui.main_display.update_active_sub_display()

            interface_stats = self.app.rns.get_interface_stats()
            stats_lookup = {iface['short_name']: iface for iface in interface_stats['interfaces']}
            for item in self.interface_items:
                # use interface name as the key
                stats_for_interface = stats_lookup.get(item.name)
                if stats_for_interface:
                    tx = stats_for_interface.get("txb", 0)
                    rx = stats_for_interface.get("rxb", 0)
                    item.update_stats(tx, rx)
        except Exception as e:
            if not hasattr(self, 'disconnect_overlay') or self.widget is not self.disconnect_overlay:
                dialog_text = urwid.Pile([
                    urwid.Text(("disconnected_status", "(!) RNS Instance Disconnected"), align="center"),
                    urwid.Text(("Waiting to Reconnect..."), align="center")
                    ])
                dialog_content = urwid.Filler(dialog_text)
                dialog_box = urwid.LineBox(dialog_content)

                self.disconnect_overlay = urwid.Overlay(
                    dialog_box,
                    self.interfaces_display,
                    align='center',
                    width=35,
                    valign='middle',
                    height=4
                )

                if self.widget is self.interfaces_display:
                    self.widget = self.disconnect_overlay
                    self.app.ui.main_display.update_active_sub_display()
        finally:
            if self.started:
                loop.set_alarm_in(1, self.poll_stats)

    def shortcuts(self):
        return self.shortcuts_display

    def switch_to_show_interface(self, iface_name):
        show_interface = ShowInterface(self, iface_name)
        self.widget = show_interface
        self.app.ui.main_display.update_active_sub_display()

        show_interface.start()

    def switch_to_list(self):
        self.shortcuts_display.reset_shortcuts()
        self.widget = self.interfaces_display
        self._rebuild_list()
        self.app.ui.main_display.update_active_sub_display()

    def add_interface(self):
        dialog_widgets = []

        def add_heading(txt):
            dialog_widgets.append(urwid.Text(("interface_title", txt), align="left"))

        def add_option(label, value):
            item = InterfaceOptionItem(self, label, value)
            dialog_widgets.append(item)

        # Get the icons based on plain, unicode, nerdfont glyphset
        network_icon = _get_interface_icon(self.glyphset, "AutoInterface")
        rnode_icon = _get_interface_icon(self.glyphset, "RNodeInterface")
        serial_icon = _get_interface_icon(self.glyphset, "SerialInterface")
        other_icon = _get_interface_icon(self.glyphset, "PipeInterface")

        add_heading(f"{network_icon}  IP Networks")
        add_option("Auto Interface", "AutoInterface")
        add_option("TCP Client Interface", "TCPClientInterface")
        add_option("TCP Server Interface", "TCPServerInterface")
        add_option("UDP Interface", "UDPInterface")
        add_option("I2P Interface", "I2PInterface")
        if PLATFORM_IS_LINUX:
            add_option("Backbone Interface", "BackboneInterface")

        if PYSERIAL_AVAILABLE:
            add_heading(f"{rnode_icon}  RNodes")
            add_option("RNode Interface", "RNodeInterface")
            add_option("RNode Multi Interface", "RNodeMultiInterface")

            add_heading(f"{serial_icon}  Hardware")
            add_option("Serial Interface", "SerialInterface")
            add_option("KISS Interface", "KISSInterface")
            add_option("AX.25 KISS Interface", "AX25KISSInterface")

        add_heading(f"{other_icon}  Other")
        add_option("Pipe Interface", "PipeInterface")
        add_option("Custom Interface", "CustomInterface")


        listbox = urwid.ListBox(urwid.SimpleFocusListWalker(dialog_widgets))
        dialog = DialogLineBox(listbox, parent=self, title="Select Interface Type")

        overlay = urwid.Overlay(
            dialog,
            self.interfaces_display,
            align='center',
            width=('relative', 50),
            valign='middle',
            height=('relative', 50),
            min_width=20,
            min_height=15,
            left=2,
            right=2
        )
        self.widget = overlay
        self.app.ui.main_display.update_active_sub_display()

    def switch_to_add_interface(self, iface_type):
        self.add_interface_view = AddInterfaceView(self, iface_type)
        self.widget = self.add_interface_view
        self.app.ui.main_display.update_active_sub_display()

    def remove_selected_interface(self):
        focus_widget, focus_position = self.box_adapter._original_widget.body.get_focus()
        if not isinstance(focus_widget, SelectableInterfaceItem):
            return

        selected_item = focus_widget
        interface_name = selected_item.name

        def on_confirm_yes(button):
            try:
                if interface_name in self.app.rns.config['interfaces']:
                    del self.app.rns.config['interfaces'][interface_name]
                    self.app.rns.config.write()

                if selected_item in self.interface_items:
                    self.interface_items.remove(selected_item)

                self._rebuild_list()
                self.dismiss_dialog()

            except Exception as e:
               print(e)

        def on_confirm_no(button):
            self.dismiss_dialog()

        confirm_text = urwid.Text(("interface_title", f"Remove interface {interface_name}?"), align="center")
        yes_button = urwid.Button("Yes", on_press=on_confirm_yes)
        no_button = urwid.Button("No", on_press=on_confirm_no)

        buttons_row = urwid.Columns([
            (urwid.WEIGHT, 0.45, yes_button),
            (urwid.WEIGHT, 0.1, urwid.Text("")),
            (urwid.WEIGHT, 0.45, no_button),
        ])

        pile = urwid.Pile([
            confirm_text,
            buttons_row
        ])

        dialog = DialogLineBox(pile, parent=self, title="?")

        overlay = urwid.Overlay(
            dialog,
            self.interfaces_display,
            align='center',
            width=('relative', 35),
            valign='middle',
            height=(5),
            min_width=5,
            left=2,
            right=2
        )
        dialog.original_widget.focus_position = 1  # columns row
        buttons_row = dialog.original_widget.contents[1][0]
        buttons_row.focus_position = 2  # second button "No"

        self.widget = overlay
        self.app.ui.main_display.update_active_sub_display()

    def dismiss_dialog(self):
        self.widget = self.interfaces_display
        self.app.ui.main_display.update_active_sub_display()

    def _rebuild_list(self):
        interface_header = urwid.Text(("interface_title", f"Interfaces ({len(self.interface_items)})"), align="center")
        if len(self.interface_items) == 0:
            interface_header = urwid.Text(("interface_title", "No interfaces found. Press Ctrl + A to add a new interface "), align="center")

        new_list = [
                       interface_header,
                       urwid.Divider(),
                   ] + self.interface_items
        # RNS.log(f"items: {self.interface_items}")

        walker = urwid.SimpleFocusListWalker(new_list)
        self.box_adapter._original_widget.body = walker
        self.box_adapter._original_widget.focus_position = len(new_list) - 1

    def open_config_editor(self):
        import platform

        editor_cmd = self.app.config["textui"]["editor"]

        if platform.system() == "Darwin" and editor_cmd == "editor":
            editor_cmd = "nano"

        editor_term = urwid.Terminal(
            (editor_cmd, self.app.rns.configpath),
            encoding='utf-8',
            main_loop=self.app.ui.loop,
        )

        def quit_term(*args, **kwargs):
            self.widget = self.interfaces_display
            self.app.ui.main_display.update_active_sub_display()
            self.app.ui.main_display.request_redraw()

        urwid.connect_signal(editor_term, 'closed', quit_term)

        editor_box = urwid.LineBox(editor_term, title="Editing RNS Config")
        self.widget = editor_box
        self.app.ui.main_display.update_active_sub_display()
        self.app.ui.main_display.frame.focus_position = "body"
        editor_term.change_focus(True)

### SHORTCUTS ###
class InterfaceDisplayShortcuts:
    def __init__(self, app):
        self.app = app
        self.default_shortcuts = "[C-a] Add Interface [C-e] Edit Interface [C-x] Remove Interface [Enter] Show Interface [C-w] Open Text Editor"
        self.current_shortcuts = self.default_shortcuts
        self.widget = urwid.AttrMap(
            urwid.Text(self.current_shortcuts),
            "shortcutbar"
        )

    def update_shortcuts(self, new_shortcuts):
        self.current_shortcuts = new_shortcuts
        self.widget.original_widget.set_text(new_shortcuts)

    def reset_shortcuts(self):
        self.update_shortcuts(self.default_shortcuts)

    def set_show_interface_shortcuts(self):
        show_shortcuts = "[Up/Down] Navigate [Tab] Switch Focus [h] Horizontal Charts [v] Vertical Charts "
        self.update_shortcuts(show_shortcuts)

    def set_add_interface_shortcuts(self):
        add_shortcuts = "[Up/Down] Navigate Fields [Enter] Select Option"
        self.update_shortcuts(add_shortcuts)

    def set_edit_interface_shortcuts(self):
        edit_shortcuts = "[Up/Down] Navigate Fields [Enter] Select Option"
        self.update_shortcuts(edit_shortcuts)