import RNS
import nomadnet
import urwid
import platform

from RNS.vendor.configobj import ConfigObj
from nomadnet.vendor.additional_urwid_widgets.FormWidgets import *

CONFIG_SECTION_GLYPHS = {
    ("logging",     "(L)",     "≡",      ""),
    ("client",      "(C)",     "✉",      ""),
    ("utilities",   "(Y)",     "⚒",      ""),
    ("textui",      "(U)",     "▤",      ""),
    ("rrc",         "(R)",     "❖",      ""),
    ("node",        "(N)",     "Ⓝ",      "\U000f0002"),
    ("printing",    "(P)",     "⎙",      ""),
    ("reticulum",   "(Rt)",    "⇄",      ""),
    ("editor",      "(E)",     "✎",      ""),
}

def _get_section_icon(glyphset, name):
    glyphset_index = 1
    if glyphset == "plain":
        glyphset_index = 0
    elif glyphset == "nerdfont":
        glyphset_index = 2

    for glyph_tuple in CONFIG_SECTION_GLYPHS:
        if glyph_tuple[0] == name:
            return glyph_tuple[glyphset_index + 1]

    return "(#)" if glyphset == "plain" else "⚙" if glyphset == "unicode" else ""

def _get_cols_rows():
    return nomadnet.NomadNetworkApp.get_shared_instance().ui.screen.get_cols_rows()

def section_title_attr(section_key):
    return "config_title_" + section_key

class ConfigCheckbox(FormCheckbox):
    def __init__(self, config_key, on_text="Enabled", off_text="Disabled", state=False, validation_types=None, transform=None, **kwargs):
        self.on_text = on_text
        self.off_text = off_text
        super().__init__(config_key, label="", state=state, validation_types=validation_types, transform=transform, **kwargs)
        self._refresh_label(self.get_state())
        urwid.connect_signal(self, "change", self._on_change)

    def _on_change(self, widget, new_state):
        self._refresh_label(new_state)

    def _refresh_label(self, state):
        if state:
            self.set_label(("connected_status", "  " + self.on_text))
        else:
            self.set_label(("inactive_text", "  " + self.off_text))

CONFIG_SECTIONS = [
    {
        "key": "logging",
        "name": "Logging",
        "glyph": "logging",
        "description": "Log verbosity and where log output is written",
        "fields": [
            {
                "config_key": "loglevel",
                "label": "Log level: ",
                "type": "dropdown",
                "options": ["0", "1", "2", "3", "4", "5", "6", "7"],
                "default": "4",
                "help": "0 = critical, 4 = info, 7 = extreme verbosity",
            },
            {
                "config_key": "destination",
                "label": "Destination: ",
                "type": "dropdown",
                "options": ["file", "stdout"],
                "default": "file",
                "help": "Write log to a file or to standard output",
            },
            {
                "config_key": "logfile",
                "label": "Log file: ",
                "type": "edit",
                "placeholder": "Defaults to the config directory",
                "help": "Path to the log file (when destination is file)",
            },
        ],
    },
    {
        "key": "client",
        "name": "LXMF client",
        "glyph": "client",
        "description": "Client behaviour, announces, syncing and messages",
        "fields": [
            {
                "config_key": "downloads_path",
                "label": "Downloads path: ",
                "type": "edit",
                "default": "~/Downloads",
                "placeholder": "~/Downloads",
                "help": "Where downloaded files are saved",
            },
            {
                "config_key": "attachment_save_path",
                "label": "Attachment path: ",
                "type": "edit",
                "placeholder": "Defaults to the downloads path",
                "help": "Where message attachments are saved",
            },
            {
                "config_key": "notify_on_new_message",
                "label": "Notify on message: ",
                "type": "checkbox",
                "default": True,
                "help": "Show a notification when a new message arrives",
            },
            {
                "config_key": "announce_at_start",
                "label": "Announce at start: ",
                "type": "checkbox",
                "default": True,
                "help": "Announce the local peer when starting",
            },
            {
                "config_key": "announce_interval",
                "label": "Announce interval: ",
                "type": "edit",
                "default": "360",
                "validation": ["number"],
                "help": "Minutes between peer announces (minimum 30)",
            },
            {
                "config_key": "try_propagation_on_send_fail",
                "label": "Propagate on fail: ",
                "type": "checkbox",
                "default": True,
                "help": "Use a propagation node if direct delivery fails",
            },
            {
                "config_key": "periodic_lxmf_sync",
                "label": "Periodic sync: ",
                "type": "checkbox",
                "default": True,
                "help": "Automatically sync messages from a propagation node",
            },
            {
                "config_key": "lxmf_sync_interval",
                "label": "Sync interval: ",
                "type": "edit",
                "default": "360",
                "validation": ["number"],
                "help": "Minutes between automatic syncs",
            },
            {
                "config_key": "lxmf_sync_limit",
                "label": "Sync limit: ",
                "type": "edit",
                "default": "8",
                "validation": ["number"],
                "help": "Max messages fetched per sync (0 = no limit)",
            },
            {
                "config_key": "required_stamp_cost",
                "label": "Required stamp cost: ",
                "type": "edit",
                "default": "None",
                "placeholder": "None",
                "validation": ["stamp_cost"],
                "help": "Required inbound stamp cost 1-255, or None to disable",
            },
            {
                "config_key": "accept_invalid_stamps",
                "label": "Accept invalid stamps: ",
                "type": "checkbox",
                "default": False,
                "help": "Accept messages carrying an invalid stamp",
            },
            {
                "config_key": "max_accepted_size",
                "label": "Max message size: ",
                "type": "edit",
                "default": "500",
                "validation": ["float"],
                "help": "Maximum accepted incoming message size, in KB",
            },
            {
                "config_key": "compact_announce_stream",
                "label": "Compact announces: ",
                "type": "checkbox",
                "default": True,
                "help": "Show only one announce per destination",
            },
            {
                "config_key": "compose_in_markdown",
                "label": "Compose in markdown: ",
                "type": "checkbox",
                "default": True,
                "help": "Author messages using markdown",
            },
        ],
    },
    {
        "key": "textui",
        "name": "Text UI",
        "glyph": "textui",
        "description": "Appearance and behaviour of the text interface",
        "note": "Switch between the light and dark theme, glyphs and other appearance options here.",
        "fields": [
            {
                "config_key": "intro_time",
                "label": "Show intro: ",
                "type": "checkbox",
                "default": True,
                "on_value": "1.0",
                "off_value": "0",
                "help": "Show the intro screen at startup",
            },
            {
                "config_key": "intro_text",
                "label": "Intro text: ",
                "type": "edit",
                "default": "Nomad Network",
                "placeholder": "Nomad Network",
                "help": "Text shown on the intro screen",
            },
            {
                "config_key": "theme",
                "label": "Theme: ",
                "type": "dropdown",
                "options": ["dark", "light"],
                "default": "dark",
                "help": "Colour theme",
            },
            {
                "config_key": "colormode",
                "label": "Color mode: ",
                "type": "dropdown",
                "options": ["monochrome", "16", "88", "256", "24bit"],
                "default": "24bit",
                "help": "Colour capability of your terminal",
            },
            {
                "config_key": "glyphs",
                "label": "Glyphs: ",
                "type": "dropdown",
                "options": ["plain", "unicode", "nerdfont"],
                "default": "nerdfont",
                "help": "Glyph set used for icons",
            },
            {
                "config_key": "mouse_enabled",
                "label": "Mouse enabled: ",
                "type": "checkbox",
                "default": True,
                "help": "Allow mouse interaction",
            },
            {
                "config_key": "editor",
                "label": "Editor: ",
                "type": "edit",
                "default": "nano",
                "placeholder": "nano",
                "help": "Command used to edit text",
            },
            {
                "config_key": "hide_guide",
                "label": "Hide guide: ",
                "type": "checkbox",
                "default": False,
                "help": "Hide the Guide entry in the menu",
            },
            {
                "config_key": "sanitize_names",
                "label": "Sanitize names: ",
                "type": "checkbox",
                "default": True,
                "help": "Strip control characters from announced names",
            },
            {
                "config_key": "clipboard_copy",
                "label": "Clipboard copy: ",
                "type": "checkbox",
                "default": False,
                "help": "Enable copying to the system clipboard",
            },
            {
                "config_key": "animation_interval",
                "label": "Animation interval: ",
                "type": "edit",
                "default": "1",
                "validation": ["number"],
                "help": "Interval between UI animation frames",
            },
        ],
    },
    {
        "key": "utilities",
        "name": "Utilities",
        "glyph": "utilities",
        "description": "Optional utility views and tools",
        "note": "Adds a Utilities menu where you can view path/announce tables and probe destinations.",
        "fields": [
            {
                "config_key": "enable_utilities",
                "label": "Enable utilities: ",
                "type": "checkbox",
                "default": False,
                "help": "Show the Utilities section (path tables, probe) in the menu",
            },
        ],
    },
    {
        "key": "rrc",
        "name": "RRC Client Settings",
        "glyph": "rrc",
        "description": "Rendering and history for the rooms client",
        "fields": [
            {
                "config_key": "history_per_room_cap",
                "label": "History cap: ",
                "type": "edit",
                "default": "500",
                "validation": ["number"],
                "help": "Messages kept in memory per room",
            },
            {
                "config_key": "filter_loaded_history",
                "label": "Filter history: ",
                "type": "checkbox",
                "default": True,
                "help": "Filter system messages out of loaded history",
            },
            {
                "config_key": "ephemeral_notices",
                "label": "Ephemeral notices: ",
                "type": "edit",
                "default": "10",
                "validation": ["float"],
                "help": "Minutes to keep notices (0 keeps them)",
            },
            {
                "config_key": "color_mention_timestamps",
                "label": "Color mention time: ",
                "type": "checkbox",
                "default": True,
                "help": "Colour the timestamp when you are mentioned",
            },
            {
                "config_key": "render_markdown",
                "label": "Render markdown: ",
                "type": "checkbox",
                "default": True,
                "help": "Render markdown formatting in messages",
            },
            {
                "config_key": "render_micron",
                "label": "Render micron: ",
                "type": "checkbox",
                "default": True,
                "help": "Render micron markup in messages",
            },
            {
                "config_key": "nick_colors",
                "label": "Nick colors: ",
                "type": "checkbox",
                "default": True,
                "help": "Colour user nicknames",
            },
            {
                "config_key": "justify_msgs",
                "label": "Justify messages: ",
                "type": "checkbox",
                "default": True,
                "help": "Justify message text",
            },
            {
                "config_key": "space_msgs",
                "label": "Space messages: ",
                "type": "checkbox",
                "default": False,
                "help": "Add extra spacing between messages",
            },
            {
                "config_key": "show_gutters",
                "label": "Show gutters: ",
                "type": "checkbox",
                "default": True,
                "help": "Show gutters alongside messages",
            },
            {
                "config_key": "mention_color",
                "label": "Mention color: ",
                "type": "edit",
                "placeholder": "6-digit hex, e.g. ff8800",
                "help": "Hex colour used for mentions of your nick",
            },
            {
                "config_key": "nick_colors_theme",
                "label": "Nick color theme: ",
                "type": "list",
                "default": [],
                "placeholder": "6-digit hex colour",
                "help": "Custom palette of hex colours used for nicknames",
            },
            {
                "config_key": "enable_esoterics",
                "label": "Enable esoterics: ",
                "type": "checkbox",
                "default": False,
                "help": "Enable esoteric features",
            },
        ],
    },
    {
        "key": "node",
        "name": "Node",
        "glyph": "node",
        "description": "Node hosting, propagation and announces",
        "note": "Enable this to host a node on the network, serving pages and files to others.",
        "fields": [
            {
                "config_key": "enable_node",
                "label": "Enable node: ",
                "type": "checkbox",
                "default": False,
                "help": "Host a node on the network",
            },
            {
                "config_key": "node_name",
                "label": "Node name: ",
                "type": "edit",
                "default": "None",
                "placeholder": "None",
                "help": "Display name for the node, or None",
            },
            {
                "config_key": "announce_at_start",
                "label": "Announce at start: ",
                "type": "checkbox",
                "default": True,
                "help": "Announce the node when starting",
            },
            {
                "config_key": "announce_interval",
                "label": "Announce interval: ",
                "type": "edit",
                "default": "360",
                "validation": ["number"],
                "help": "Minutes between node announces (minimum 1)",
            },
            {
                "config_key": "disable_propagation",
                "label": "Disable propagation: ",
                "type": "checkbox",
                "default": True,
                "help": "Disable the propagation node functionality",
            },
            {
                "config_key": "propagation_cost",
                "label": "Propagation cost: ",
                "type": "edit",
                "default": "16",
                "validation": ["number"],
                "help": "Stamp cost for propagation (minimum 13)",
            },
            {
                "config_key": "max_transfer_size",
                "label": "Max transfer size: ",
                "type": "edit",
                "default": "256",
                "validation": ["float"],
                "help": "Maximum single message size on propagation, in KB",
            },
            {
                "config_key": "max_sync_size",
                "label": "Max sync size: ",
                "type": "edit",
                "default": "10240",
                "validation": ["float"],
                "help": "Maximum sync batch size, in KB",
            },
            {
                "config_key": "pages_path",
                "label": "Pages path: ",
                "type": "edit",
                "placeholder": "Default node pages directory",
                "help": "Directory of pages served by the node",
            },
            {
                "config_key": "page_refresh_interval",
                "label": "Page refresh: ",
                "type": "edit",
                "default": "0",
                "validation": ["number"],
                "help": "Minutes between page rescans (0 = never)",
            },
            {
                "config_key": "files_path",
                "label": "Files path: ",
                "type": "edit",
                "placeholder": "Default node files directory",
                "help": "Directory of files served by the node",
            },
            {
                "config_key": "file_refresh_interval",
                "label": "File refresh: ",
                "type": "edit",
                "default": "0",
                "validation": ["number"],
                "help": "Minutes between file rescans (0 = never)",
            },
            {
                "config_key": "prioritise_destinations",
                "label": "Priority dests: ",
                "type": "list",
                "default": [],
                "placeholder": "Destination hash",
                "help": "Destination hashes given storage priority",
            },
            {
                "config_key": "static_peers",
                "label": "Static peers: ",
                "type": "list",
                "default": [],
                "placeholder": "Destination hash",
                "help": "Propagation peers always kept connected",
            },
            {
                "config_key": "max_peers",
                "label": "Max peers: ",
                "type": "edit",
                "placeholder": "No limit",
                "validation": ["number"],
                "help": "Maximum number of propagation peers",
            },
            {
                "config_key": "message_storage_limit",
                "label": "Storage limit: ",
                "type": "edit",
                "default": "2000",
                "validation": ["float"],
                "help": "Maximum propagation storage, in MB",
            },
        ],
    },
    {
        "key": "printing",
        "name": "Printing",
        "glyph": "printing",
        "description": "Printing of received messages",
        "note": "The rendered message file is appended to this command, so it runs as e.g. 'lp <file>'.",
        "fields": [
            {
                "config_key": "print_messages",
                "label": "Print messages: ",
                "type": "checkbox",
                "default": False,
                "help": "Print received messages",
            },
            {
                "config_key": "print_command",
                "label": "Print command: ",
                "type": "edit",
                "default": "lp",
                "placeholder": "lp",
                "help": ("Command to print with; the message file is appended as the last argument. Examples: "
                         "lp  |  "
                         "lp -d NAME (named printer, list with lpstat -p)  |  "
                         "lp -d NAME -o cpi=16 -o lpi=8 (small thermal-roll printers)  |  "
                         "lp -d NAME -o media=Custom.58x210mm (58mm thermal roll)"),
            },
            {
                "config_key": "print_from",
                "label": "Print from: ",
                "type": "list",
                "default": [],
                "placeholder": "everywhere, trusted, or hash",
                "help": "Which senders may trigger automatic printing",
            },
            {
                "config_key": "message_template",
                "label": "Message template: ",
                "type": "edit",
                "placeholder": "Path to template file",
                "help": "Template file used when printing messages",
            },
        ],
    },
    {
        "key": "reticulum",
        "name": "Reticulum (global)",
        "glyph": "reticulum",
        "configfile": "reticulum",
        "description": "Global Reticulum settings (shared instance, transport)",
        "fields": [
            {
                "config_key": "enable_transport",
                "label": "Enable transport: ",
                "type": "checkbox",
                "default": False,
                "help": "Route traffic for other peers (transport node)",
            },
            {
                "config_key": "share_instance",
                "label": "Share instance: ",
                "type": "checkbox",
                "default": True,
                "help": "Run a shared instance other local programs connect to",
            },
            {
                "config_key": "instance_name",
                "label": "Instance name: ",
                "type": "edit",
                "default": "default",
                "placeholder": "default",
                "help": "Name used to isolate multiple shared instances",
            },
            {
                "config_key": "shared_instance_type",
                "label": "Instance type: ",
                "type": "edit",
                "placeholder": "unix or tcp (blank for auto)",
                "help": "Transport used for shared instance communication",
            },
            {
                "config_key": "shared_instance_port",
                "label": "Instance port: ",
                "type": "edit",
                "placeholder": "37428",
                "validation": ["number"],
                "help": "TCP port for the shared instance",
            },
            {
                "config_key": "instance_control_port",
                "label": "Control port: ",
                "type": "edit",
                "placeholder": "37429",
                "validation": ["number"],
                "help": "TCP control port for the shared instance",
            },
            {
                "config_key": "discover_interfaces",
                "label": "Discover interfaces: ",
                "type": "checkbox",
                "default": False,
                "help": "Discover interfaces advertised by transport instances",
            },
            {
                "config_key": "enable_remote_management",
                "label": "Remote management: ",
                "type": "checkbox",
                "default": False,
                "help": "Allow remote management of this instance",
            },
            {
                "config_key": "remote_management_allowed",
                "label": "Remote allowed: ",
                "type": "list",
                "default": [],
                "placeholder": "Identity hash",
                "help": "Identity hashes allowed to manage this instance",
            },
            {
                "config_key": "respond_to_probes",
                "label": "Respond to probes: ",
                "type": "checkbox",
                "default": False,
                "help": "Answer reachability probes from other nodes",
            },
            {
                "config_key": "use_implicit_proof",
                "label": "Implicit proof: ",
                "type": "checkbox",
                "default": True,
                "help": "Use implicit proofs for packet delivery",
            },
            {
                "config_key": "panic_on_interface_error",
                "label": "Panic on iface error: ",
                "type": "checkbox",
                "default": False,
                "help": "Exit if an interface has an unrecoverable error",
            },
        ],
    },
]

_SECTION_ORDER = {"node": 0, "client": 1, "logging": 2, "textui": 3, "utilities": 4, "rrc": 5, "printing": 6, "reticulum": 7}
CONFIG_SECTIONS.sort(key=lambda s: _SECTION_ORDER.get(s["key"], 99))

class ConfigDisplayShortcuts():
    def __init__(self, app):
        self.app = app
        self.default_shortcuts = "[Enter] Edit Section [C-w] Text Editor [Up/Down] Navigate"
        self.widget = urwid.AttrMap(urwid.Text(self.default_shortcuts), "shortcutbar")

    def update_shortcuts(self, new_shortcuts):
        self.widget.original_widget.set_text(new_shortcuts)

    def reset_shortcuts(self):
        self.update_shortcuts(self.default_shortcuts)

    def set_section_shortcuts(self):
        self.update_shortcuts("[Up/Down] Navigate Fields [Enter] Select Option [C-s] Save [C-r] Reset [Esc] Cancel")

class ConfigFiller(urwid.WidgetWrap):
    def __init__(self, widget, app):
        self.app = app
        super().__init__(widget)

    def keypress(self, size, key):
        if key == "ctrl w":
            self.app.ui.main_display.sub_displays.config_display.open_text_editor()
            return None
        return super(ConfigFiller, self).keypress(size, key)

class SelectableConfigSection(urwid.WidgetWrap):
    def __init__(self, parent, section_key, name, description, icon, note=None):
        self.parent = parent
        self.section_key = section_key
        self.name = name
        self.icon = icon
        self._selectable = True

        self.title_attr = section_title_attr(section_key)
        self.title_attr_selected = self.title_attr + "_selected"

        self.selection_txt = urwid.Text(" ")
        self.title_widget = urwid.Text((self.title_attr, f"{icon}  {name}"))

        title_content = urwid.Columns([
            (4, self.selection_txt),
            self.title_widget,
        ])

        description_row = urwid.Columns([
            (4, urwid.Text(" ")),
            urwid.Text(("value", description)),
        ])

        pile_rows = [title_content, description_row]
        if note:
            pile_rows.append(urwid.Columns([
                (4, urwid.Text(" ")),
                urwid.Text(("inactive_text", note)),
            ]))

        pile = urwid.Pile(pile_rows)
        padded_body = urwid.Padding(pile, left=2, right=2)

        box = urwid.LineBox(
            padded_body,
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

        if focus:
            self.title_widget.set_text((self.title_attr_selected, f"{self.icon}  {self.name}"))
        else:
            self.title_widget.set_text((self.title_attr, f"{self.icon}  {self.name}"))

        return super().render(size, focus=focus)

    def keypress(self, size, key):
        if key == "up":
            listbox = self.parent.list_box
            if listbox.focus_position == 0:
                self.parent.app.ui.main_display.frame.focus_position = "header"
                return None
        elif key == "enter":
            self.parent.switch_to_section(self.section_key)
            return None
        return key

class ConfigActionItem(urwid.WidgetWrap):
    def __init__(self, parent, label, on_select):
        self.parent = parent
        self.on_select = on_select
        self._selectable = True

        text_widget = urwid.Text(label, align="left")
        super().__init__(urwid.AttrMap(text_widget, "list_normal", focus_map="list_focus"))

    def selectable(self):
        return True

    def keypress(self, size, key):
        if key == "enter":
            self.on_select()
            return None
        return super().keypress(size, key)

    def mouse_event(self, size, event, button, x, y, focus):
        if button == 1 and urwid.util.is_mouse_press(event):
            self.on_select()
            return True
        return False

class ConfigSectionView(urwid.WidgetWrap):
    LABEL_WIDTH = 24

    def __init__(self, parent, section):
        self.parent = parent
        self.section = section
        self.section_key = section["key"]
        self.fields = {}

        self.parent.shortcuts_display.set_section_shortcuts()

        self.config_path = self._resolve_config_path(section)
        self.file_config = ConfigObj(self.config_path)
        section_config = self.file_config.get(self.section_key, {})

        cols, rows = _get_cols_rows()
        self.content_width = min(80, max(40, cols - 6))

        icon = _get_section_icon(self.parent.glyphset, section["glyph"])

        field_items = []
        for field in section["fields"]:
            widget = self._build_field_widget(field)
            current = section_config.get(field["config_key"], field.get("default"))
            self._populate_field(widget, field, current)
            self.fields[field["config_key"]] = {"field": field, "widget": widget}
            field_items.append(self._build_field_row(field, widget))

        self.list_walker = urwid.SimpleFocusListWalker(field_items)
        self.form_listbox = urwid.ListBox(self.list_walker)

        header = urwid.Pile([
            urwid.Text((section_title_attr(self.section_key) + "_selected", f"{icon}  {section['name']}"), align=urwid.CENTER),
            urwid.Divider("─"),
        ])

        save_btn = urwid.AttrMap(urwid.Button("Save", on_press=self.on_save), "button_normal", focus_map="button_focus")
        reset_btn = urwid.AttrMap(urwid.Button("Reset", on_press=self.on_reset), "button_normal", focus_map="button_focus")
        back_btn = urwid.AttrMap(urwid.Button("Cancel", on_press=self.on_back), "button_normal", focus_map="button_focus")
        button_row = urwid.Columns([
            (urwid.WEIGHT, 0.3, save_btn),
            (urwid.WEIGHT, 0.05, urwid.Text("")),
            (urwid.WEIGHT, 0.3, reset_btn),
            (urwid.WEIGHT, 0.05, urwid.Text("")),
            (urwid.WEIGHT, 0.3, back_btn),
        ])
        self._footer = urwid.Pile([
            urwid.Divider("─"),
            urwid.Padding(button_row, align=urwid.CENTER, width=self.content_width),
        ])
        try:
            self._footer.focus_position = 1
        except Exception:
            pass

        self._frame = urwid.Frame(self.form_listbox, header=header, footer=self._footer)
        super().__init__(self._frame)

    def _resolve_config_path(self, section):
        if section.get("configfile") == "reticulum":
            try:
                return self.parent.app.rns.config.filename
            except Exception:
                return RNS.Reticulum.configpath
        return self.parent.app.configpath

    def _build_field_row(self, field, widget):
        row = urwid.Columns([
            (self.LABEL_WIDTH, urwid.Text(("key", field["label"]), align=urwid.RIGHT)),
            widget,
        ])
        contents = [row]
        help_text = self._field_help(field)
        if help_text:
            contents.append(urwid.Padding(urwid.Text(("inactive_text", help_text)), left=self.LABEL_WIDTH + 2))
        contents.append(urwid.Padding(widget.error_widget, left=self.LABEL_WIDTH + 2))
        contents.append(urwid.Divider())
        field_pile = urwid.Pile(contents)
        return urwid.Padding(field_pile, align=urwid.CENTER, width=self.content_width)

    def _field_help(self, field):
        parts = []
        if field.get("help"):
            parts.append(field["help"])
        default = field.get("default", None)
        if field["type"] == "checkbox":
            default_text = "yes" if default else "no"
        elif field["type"] == "list":
            if not default:
                default_text = "none"
            elif isinstance(default, (list, tuple)):
                default_text = ", ".join(str(item) for item in default)
            else:
                default_text = str(default)
        else:
            default_text = str(default) if default not in (None, "") else "none"
        parts.append(f"(default: {default_text})")
        return " ".join(parts)

    def _build_field_widget(self, field):
        if field["type"] == "dropdown":
            return FormDropdown(
                config_key=field["config_key"],
                label=field.get("label", ""),
                options=field["options"],
                default=str(field.get("default", field["options"][0])),
                validation_types=field.get("validation", []),
            )
        elif field["type"] == "checkbox":
            return ConfigCheckbox(
                config_key=field["config_key"],
                on_text=field.get("on_text", "Enabled"),
                off_text=field.get("off_text", "Disabled"),
                state=bool(field.get("default", False)),
                validation_types=field.get("validation", []),
            )
        elif field["type"] == "list":
            return FormMultiList(
                config_key=field["config_key"],
                placeholder=field.get("placeholder", ""),
                validation_types=field.get("validation", []),
            )
        else:
            return FormEdit(
                config_key=field["config_key"],
                caption="",
                edit_text=str(field.get("default", "")),
                placeholder=field.get("placeholder", ""),
                validation_types=field.get("validation", []),
            )

    def _populate_field(self, widget, field, value):
        if value is None:
            return

        if field["type"] == "checkbox":
            if isinstance(value, bool):
                state = value
            else:
                s = str(value).strip().lower()
                if s in ("", "false", "off", "no"):
                    state = False
                else:
                    try:
                        state = float(s) != 0
                    except ValueError:
                        state = True
            widget.set_state(state)
        elif field["type"] == "dropdown":
            str_value = str(value)
            if str_value in widget.options:
                widget.selected = str_value
                widget.main_button.base_widget.set_text(str_value)
        elif field["type"] == "list":
            if value:
                widget.set_value(value if isinstance(value, list) else [value])
        else:
            if isinstance(value, (list, tuple)):
                widget.edit_text = ", ".join(str(item) for item in value)
            else:
                widget.edit_text = str(value)

    def validate_all(self):
        all_valid = True
        for entry in self.fields.values():
            if not entry["widget"].validate():
                all_valid = False
        return all_valid

    def on_save(self, button):
        if not self.validate_all():
            self.show_message("Some fields have invalid values.\nCorrect the marked fields and try again.", title="Not saved", back_to_list=False)
            return

        try:
            self.file_config.reload()
        except Exception:
            pass

        if self.section_key not in self.file_config:
            self.file_config[self.section_key] = {}

        section_config = self.file_config[self.section_key]

        for config_key, entry in self.fields.items():
            field = entry["field"]
            widget = entry["widget"]

            if field["type"] == "checkbox":
                on_value = field.get("on_value", "yes")
                off_value = field.get("off_value", "no")
                section_config[config_key] = on_value if widget.get_state() else off_value
            elif field["type"] == "list":
                value = widget.get_value()
                if value:
                    section_config[config_key] = value
                elif config_key in section_config:
                    del section_config[config_key]
            else:
                value = widget.get_value()
                if value != "":
                    section_config[config_key] = value
                elif config_key in section_config:
                    del section_config[config_key]

        try:
            self.file_config.write()
            if self.section.get("configfile") == "reticulum":
                try:
                    self.parent.app.rns.config.reload()
                except Exception:
                    pass
            self.parent.mark_restart_pending()
            self.show_message(f"{self.section['name']} configuration saved.\nRestart Nomad Network for changes to take effect.")
        except Exception as e:
            self.show_message(f"Error saving configuration: {str(e)}", title="Error", back_to_list=False)

    def on_reset(self, button=None):
        self._confirm(
            f"Reset all {self.section['name']} settings to their defaults?\nYou will still need to Save to apply.",
            self._do_reset,
        )

    def _do_reset(self):
        for entry in self.fields.values():
            self._reset_field(entry["widget"], entry["field"])

    def _reset_field(self, widget, field):
        default = field.get("default")
        if field["type"] == "checkbox":
            widget.set_state(bool(default))
        elif field["type"] == "dropdown":
            default_str = str(default if default is not None else widget.options[0])
            if default_str in widget.options:
                widget.selected = default_str
                widget.main_button.base_widget.set_text(default_str)
        elif field["type"] == "list":
            widget.set_value(default if isinstance(default, list) else [])
        else:
            widget.edit_text = "" if default is None else str(default)
        widget.error_widget.set_text("")

    def on_back(self, button):
        self.parent.switch_to_list()

    def dismiss_dialog(self):
        self._dismiss_overlay()

    def _confirm(self, message, on_yes):
        def yes(button):
            self._dismiss_overlay()
            on_yes()

        def no(button):
            self._dismiss_overlay()

        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text(message, align=urwid.CENTER),
                urwid.Divider(),
                urwid.Columns([
                    (urwid.WEIGHT, 0.45, urwid.Button("Yes", on_press=yes)),
                    (urwid.WEIGHT, 0.1, urwid.Text("")),
                    (urwid.WEIGHT, 0.45, urwid.Button("No", on_press=no)),
                ]),
            ]),
            parent=self,
            title="Confirm",
        )
        self._show_overlay(dialog, height=9, width=64)

    def _show_overlay(self, dialog, height=8, width=60):
        overlay = urwid.Overlay(
            dialog,
            self,
            align=urwid.CENTER,
            width=width,
            valign=urwid.MIDDLE,
            height=height,
            min_width=1,
            min_height=1,
        )
        self.parent.widget = overlay
        self.parent.app.ui.main_display.update_active_sub_display()

    def _dismiss_overlay(self):
        self.parent.widget = self
        self.parent.app.ui.main_display.update_active_sub_display()

    def show_message(self, message, title="Notice", back_to_list=True):
        def dismiss_dialog(button=None):
            if back_to_list:
                self.parent.switch_to_list()
            else:
                self._dismiss_overlay()

        dialog = DialogLineBox(
            urwid.Pile([
                urwid.Text(message, align=urwid.CENTER),
                urwid.Divider(),
                urwid.Button("OK", on_press=dismiss_dialog)
            ]),
            parent=self,
            title=title
        )

        self._show_overlay(dialog, height=10, width=60)

    def keypress(self, size, key):
        if key == "ctrl s":
            self.on_save(None)
            return None
        if key == "ctrl r":
            self.on_reset(None)
            return None
        if key == "esc":
            self.parent.switch_to_list()
            return None

        result = super().keypress(size, key)
        if result is None:
            return None

        if result in ("down", "tab") and self._frame.focus_position != "footer":
            self._frame.focus_position = "footer"
            try:
                self._footer.focus_position = 1
            except Exception:
                pass
            return None
        if result == "up":
            if self._frame.focus_position == "footer":
                self._frame.focus_position = "body"
            else:
                self.parent.app.ui.main_display.frame.focus_position = "header"
            return None

        return result

class ConfigDisplay():
    def __init__(self, app):
        self.app = app
        self.glyphset = self.app.config["textui"]["glyphs"]
        self.g = self.app.ui.glyphs
        self.restart_pending = False
        self.editor_term = None

        self.shortcuts_display = ConfigDisplayShortcuts(self.app)

        self._build_list_view()
        self.widget = self.list_view

    def _build_list_view(self):
        self.section_items = []
        for section in CONFIG_SECTIONS:
            icon = _get_section_icon(self.glyphset, section["glyph"])
            self.section_items.append(
                SelectableConfigSection(self, section["key"], section["name"], section["description"], icon, note=section.get("note"))
            )

        editor_icon = _get_section_icon(self.glyphset, "editor")
        self.editor_item = ConfigActionItem(self, f"{editor_icon}  Open config file in text editor", self.open_text_editor)

        list_contents = list(self.section_items) + [urwid.Divider(), self.editor_item]
        self.list_walker = urwid.SimpleFocusListWalker(list_contents)
        self.list_box = urwid.ListBox(self.list_walker)

        self.header_text = urwid.Text("")
        self.list_divider = urwid.Divider("─")
        self.list_pile = urwid.Pile([('weight', 1, self.list_box)])
        self._update_header()

        self.list_view = ConfigFiller(self.list_pile, self.app)

    def _update_header(self):
        contents = []
        if self.restart_pending:
            self.header_text.set_text(("warning_text", "Changes saved. Restart NomadNet for them to take effect"))
            contents.append((self.header_text, self.list_pile.options('pack')))
            contents.append((self.list_divider, self.list_pile.options('pack')))
        contents.append((self.list_box, self.list_pile.options('weight', 1)))
        self.list_pile.contents = contents

    def mark_restart_pending(self):
        self.restart_pending = True
        self._update_header()

    def switch_to_section(self, section_key):
        section = next(s for s in CONFIG_SECTIONS if s["key"] == section_key)
        self.section_view = ConfigSectionView(self, section)
        self.widget = self.section_view
        self.app.ui.main_display.update_active_sub_display()

    def switch_to_list(self):
        self.shortcuts_display.reset_shortcuts()
        self.editor_term = None
        self._update_header()
        self.widget = self.list_view
        self.app.ui.main_display.update_active_sub_display()

    def open_text_editor(self):
        self.editor_term = EditorTerminal(self.app, self)
        self.widget = urwid.LineBox(self.editor_term)
        self.app.ui.main_display.update_active_sub_display()
        self.app.ui.main_display.frame.focus_position = "body"
        self.editor_term.term.change_focus(True)

    def shortcuts(self):
        return self.shortcuts_display

class EditorTerminal(urwid.WidgetWrap):
    def __init__(self, app, parent):
        self.app = app
        self.parent = parent
        editor_cmd = self.app.config["textui"]["editor"]

        # The "editor" alias is unavailable on Darwin,
        # so we replace it with nano.
        if platform.system() == "Darwin" and editor_cmd == "editor":
            editor_cmd = "nano"

        self.term = urwid.Terminal(
            (editor_cmd, self.app.configpath),
            encoding='utf-8',
            main_loop=self.app.ui.loop,
        )

        def quit_term(*args, **kwargs):
            self.parent.switch_to_list()
            self.app.ui.main_display.request_redraw()

        urwid.connect_signal(self.term, 'closed', quit_term)

        super().__init__(self.term)


    def keypress(self, size, key):
        return super(EditorTerminal, self).keypress(size, key)
