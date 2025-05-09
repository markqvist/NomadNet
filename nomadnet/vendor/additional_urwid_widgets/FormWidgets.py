import urwid

class DialogLineBox(urwid.LineBox):
    def __init__(self, body, parent=None, title="?"):
        super().__init__(body, title=title)
        self.parent = parent

    def keypress(self, size, key):
        if key == "esc":
            if self.parent and hasattr(self.parent, "dismiss_dialog"):
                self.parent.dismiss_dialog()
            return None
        return super().keypress(size, key)

class Placeholder(urwid.Edit):
    def __init__(self, caption="", edit_text="", placeholder="", **kwargs):
        super().__init__(caption, edit_text, **kwargs)
        self.placeholder = placeholder

    def render(self, size, focus=False):
        if not self.edit_text and not focus:
            placeholder_widget = urwid.Text(("placeholder", self.placeholder))
            return placeholder_widget.render(size, focus)
        else:
            return super().render(size, focus)

class Dropdown(urwid.WidgetWrap):
    signals = ['change'] # emit for urwid.connect_signal fn

    def __init__(self, label, options, default=None):
        self.label = label
        self.options = options
        self.selected = default if default is not None else options[0]

        self.main_text = f"{self.selected}"
        self.main_button = urwid.SelectableIcon(self.main_text, 0)
        self.main_button = urwid.AttrMap(self.main_button, "button_normal", "button_focus")

        self.option_widgets = []
        for opt in options:
            icon = urwid.SelectableIcon(opt, 0)
            icon = urwid.AttrMap(icon, "list_normal", "list_focus")
            self.option_widgets.append(icon)

        self.options_walker = urwid.SimpleFocusListWalker(self.option_widgets)
        self.options_listbox = urwid.ListBox(self.options_walker)
        self.dropdown_box = None  # will be created on open_dropdown

        self.pile = urwid.Pile([self.main_button])
        self.dropdown_visible = False

        super().__init__(self.pile)

    def open_dropdown(self):
        if not self.dropdown_visible:
            height = len(self.options)
            self.dropdown_box = urwid.BoxAdapter(self.options_listbox, height)
            self.pile.contents.append((self.dropdown_box, self.pile.options()))
            self.dropdown_visible = True
            self.pile.focus_position = 1
            self.options_walker.set_focus(0)

    def close_dropdown(self):
        if self.dropdown_visible:
            self.pile.contents.pop()  # remove the dropdown_box
            self.dropdown_visible = False
            self.pile.focus_position = 0
            self.dropdown_box = None

    def keypress(self, size, key):
        if not self.dropdown_visible:
            if key == "enter":
                self.open_dropdown()
                return None
            return self.main_button.keypress(size, key)
        else:
            if key == "enter":
                focus_result = self.options_walker.get_focus()
                if focus_result is not None:
                    focus_widget = focus_result[0]
                    new_val = focus_widget.base_widget.text
                    old_val = self.selected
                    self.selected = new_val
                    self.main_button.base_widget.set_text(f"{self.selected}")

                    if old_val != new_val:
                        self._emit('change', new_val)

                self.close_dropdown()
                return None
            return self.dropdown_box.keypress(size, key)

    def get_value(self):
        return self.selected

class ValidationError(urwid.Text):
    def __init__(self, message=""):
        super().__init__(("error", message))

class FormField:
    def __init__(self, config_key, transform=None):
        self.config_key = config_key
        self.transform = transform or (lambda x: x)

class FormEdit(Placeholder, FormField):
    def __init__(self, config_key, caption="", edit_text="", placeholder="", validation_types=None, transform=None, **kwargs):
        Placeholder.__init__(self, caption, edit_text, placeholder, **kwargs)
        FormField.__init__(self, config_key, transform)
        self.validation_types = validation_types or []
        self.error_widget = urwid.Text("")
        self.error = None

    def get_value(self):
        return self.transform(self.edit_text.strip())

    def validate(self):
        value = self.edit_text.strip()
        self.error = None

        for validation in self.validation_types:
            if validation == "required":
                if not value:
                    self.error = "This field is required"
                    break
            elif validation == "number":
                if value and not value.replace('-', '').replace('.', '').isdigit():
                    self.error = "This field must be a number"
                    break
            elif validation == "float":
                try:
                    if value:
                        float(value)
                except ValueError:
                    self.error = "This field must be decimal number"
                    break

        self.error_widget.set_text(("error", self.error or ""))
        return self.error is None

class FormCheckbox(urwid.CheckBox, FormField):
    def __init__(self, config_key, label="", state=False, validation_types=None, transform=None, **kwargs):
        urwid.CheckBox.__init__(self, label, state, **kwargs)
        FormField.__init__(self, config_key, transform)
        self.validation_types = validation_types or []
        self.error_widget = urwid.Text("")
        self.error = None

    def get_value(self):
        return self.transform(self.get_state())

    def validate(self):

        value = self.get_state()
        self.error = None

        for validation in self.validation_types:
            if validation == "required":
                if not value:
                    self.error = "This field is  required"
                    break

        self.error_widget.set_text(("error", self.error or ""))
        return self.error is None

class FormDropdown(Dropdown, FormField):
    signals = ['change']

    def __init__(self, config_key, label, options, default=None, validation_types=None, transform=None):
        self.options = [str(opt) for opt in options]

        if default is not None:
            default_str = str(default)
            if default_str in self.options:
                default = default_str
            elif transform:
                try:
                    default_transformed = transform(default_str)
                    for opt in self.options:
                        if transform(opt) == default_transformed:
                            default = opt
                            break
                except:
                    default = self.options[0]
            else:
                default = self.options[0]
        else:
            default = self.options[0]

        Dropdown.__init__(self, label, self.options, default)
        FormField.__init__(self, config_key, transform)

        self.validation_types = validation_types or []
        self.error_widget = urwid.Text("")
        self.error = None

        if hasattr(self, 'main_button'):
            self.main_button.base_widget.set_text(str(default))

    def get_value(self):
        return self.transform(self.selected)

    def validate(self):
        value = self.get_value()
        self.error = None

        for validation in self.validation_types:
            if validation == "required":
                if not value:
                    self.error = "This field is required"
                    break

        self.error_widget.set_text(("error", self.error or ""))
        return self.error is None

    def open_dropdown(self):
        if not self.dropdown_visible:
            super().open_dropdown()
            try:
                current_index = self.options.index(self.selected)
                self.options_walker.set_focus(current_index)
            except ValueError:
                pass

class FormMultiList(urwid.Pile, FormField):
    def __init__(self, config_key, placeholder="", validation_types=None, transform=None, **kwargs):
        self.entries = []
        self.error_widget = urwid.Text("")
        self.error = None
        self.placeholder = placeholder
        self.validation_types = validation_types or []

        first_entry = self.create_entry_row()
        self.entries.append(first_entry)

        self.add_button = urwid.Button("+ Add Another", on_press=self.add_entry)
        add_button_padded = urwid.Padding(self.add_button, left=2, right=2)

        pile_widgets = [first_entry, add_button_padded]
        urwid.Pile.__init__(self, pile_widgets)
        FormField.__init__(self, config_key, transform)

    def create_entry_row(self):
        edit = urwid.Edit("", "")
        entry_row = urwid.Columns([
            ('weight', 1, edit),
            (3, urwid.Button("×", on_press=lambda button: self.remove_entry(button, entry_row))),
        ])
        return entry_row

    def remove_entry(self, button, entry_row):
        if len(self.entries) > 1:
            self.entries.remove(entry_row)
            self.contents = [(w, self.options()) for w in self.get_pile_widgets()]

    def add_entry(self, button):
        new_entry = self.create_entry_row()
        self.entries.append(new_entry)

        self.contents = [(w, self.options()) for w in self.get_pile_widgets()]

    def get_pile_widgets(self):
        return self.entries + [urwid.Padding(self.add_button, left=2, right=2)]

    def get_value(self):
        values = []
        for entry in self.entries:
            edit_widget = entry.contents[0][0]
            value = edit_widget.edit_text.strip()
            if value:
                values.append(value)
        return self.transform(values)

    def validate(self):
        values = self.get_value()
        self.error = None

        for validation in self.validation_types:
            if validation == "required" and not values:
                self.error = "At least one entry is required"
                break

        self.error_widget.set_text(("error", self.error or ""))
        return self.error is None


class FormMultiTable(urwid.Pile, FormField):
    def __init__(self, config_key, fields, validation_types=None, transform=None, **kwargs):
        self.entries = []
        self.fields = fields
        self.error_widget = urwid.Text("")
        self.error = None
        self.validation_types = validation_types or []

        header_columns = [('weight', 3, urwid.Text(("list_focus", "Name")))]
        for field_key, field_config in self.fields.items():
            header_columns.append(('weight', 2, urwid.Text(("list_focus", field_config.get("label", field_key)))))
        header_columns.append((4, urwid.Text(("list_focus", ""))))

        self.header_row = urwid.Columns(header_columns)

        first_entry = self.create_entry_row()
        self.entries.append(first_entry)

        self.add_button = urwid.Button("+ Add ", on_press=self.add_entry)
        add_button_padded = urwid.Padding(self.add_button, left=2, right=2)

        pile_widgets = [
            self.header_row,
            urwid.Divider("-"),
            first_entry,
            add_button_padded
        ]

        urwid.Pile.__init__(self, pile_widgets)
        FormField.__init__(self, config_key, transform)

    def create_entry_row(self, name="", values=None):
        if values is None:
            values = {}

        name_edit = urwid.Edit("", name)

        columns = [('weight', 3, name_edit)]

        field_widgets = {}
        for field_key, field_config in self.fields.items():
            field_value = values.get(field_key, "")

            if field_config.get("type") == "checkbox":
                widget = urwid.CheckBox("", state=bool(field_value))
            elif field_config.get("type") == "dropdown":
                # TODO: dropdown in MultiTable
                widget = urwid.Edit("", str(field_value))
            else:
                widget = urwid.Edit("", str(field_value))

            field_widgets[field_key] = widget
            columns.append(('weight', 2, widget))

        remove_button = urwid.Button("×", on_press=lambda button: self.remove_entry(button, entry_row))
        columns.append((4, remove_button))

        entry_row = urwid.Columns(columns)
        entry_row.name_edit = name_edit
        entry_row.field_widgets = field_widgets

        return entry_row

    def remove_entry(self, button, entry_row):
        if len(self.entries) > 1:
            self.entries.remove(entry_row)
            self.contents = [(w, self.options()) for w in self.get_pile_widgets()]

    def add_entry(self, button):
        new_entry = self.create_entry_row()
        self.entries.append(new_entry)

        self.contents = [(w, self.options()) for w in self.get_pile_widgets()]

    def get_pile_widgets(self):
        return [
            self.header_row,
            urwid.Divider("-")
        ] + self.entries + [
            urwid.Padding(self.add_button, left=2, right=2)
        ]

    def get_value(self):
        values = {}
        for entry in self.entries:
            name = entry.name_edit.edit_text.strip()
            if name:
                subinterface = {}
                subinterface["interface_enabled"] = True

                for field_key, widget in entry.field_widgets.items():
                    field_config = self.fields.get(field_key, {})

                    if hasattr(widget, "get_state"):
                        value = widget.get_state()
                    elif hasattr(widget, "edit_text"):
                        value = widget.edit_text.strip()

                        transform = field_config.get("transform")
                        if transform and value:
                            try:
                                value = transform(value)
                            except (ValueError, TypeError):
                                value = ""

                    if value:
                        subinterface[field_key] = value

                values[name] = subinterface

        return self.transform(values) if self.transform else values

    def set_value(self, value):
        self.entries = []

        if not value:
            self.entries.append(self.create_entry_row())
        else:
            for name, config in value.items():
                self.entries.append(self.create_entry_row(name=name, values=config))

        self.contents = [(w, self.options()) for w in self.get_pile_widgets()]

    def validate(self):
        values = self.get_value()
        self.error = None

        for validation in self.validation_types:
            if validation == "required" and not values:
                self.error = "At least one subinterface is required"
                break

        self.error_widget.set_text(("error", self.error or ""))
        return self.error is None


class FormKeyValuePairs(urwid.Pile, FormField):
    def __init__(self, config_key, validation_types=None, transform=None, **kwargs):
        self.entries = []
        self.error_widget = urwid.Text("")
        self.error = None
        self.validation_types = validation_types or []

        header_columns = [
            ('weight', 1, urwid.AttrMap(urwid.Text("Parameter Key"), "multitable_header")),
            ('weight', 1, urwid.AttrMap(urwid.Text("Parameter Value"), "multitable_header")),
            (4, urwid.AttrMap(urwid.Text("Action"), "multitable_header"))
        ]

        self.header_row = urwid.AttrMap(urwid.Columns(header_columns), "multitable_header")

        first_entry = self.create_entry_row()
        self.entries.append(first_entry)

        self.add_button = urwid.Button("+ Add Parameter", on_press=self.add_entry)
        add_button_padded = urwid.Padding(self.add_button, left=2, right=2)

        pile_widgets = [
            self.header_row,
            urwid.Divider("-"),
            first_entry,
            add_button_padded
        ]

        urwid.Pile.__init__(self, pile_widgets)
        FormField.__init__(self, config_key, transform)

    def create_entry_row(self, key="", value=""):
        key_edit = urwid.Edit("", key)
        value_edit = urwid.Edit("", value)

        remove_button = urwid.Button("×", on_press=lambda button: self.remove_entry(button, entry_row))

        entry_row = urwid.Columns([
            ('weight', 1, key_edit),
            ('weight', 1, value_edit),
            (4, remove_button)
        ])

        entry_row.key_edit = key_edit
        entry_row.value_edit = value_edit

        return entry_row

    def remove_entry(self, button, entry_row):
        if len(self.entries) > 1:
            self.entries.remove(entry_row)
            self.contents = [(w, self.options()) for w in self.get_pile_widgets()]

    def add_entry(self, button):
        new_entry = self.create_entry_row()
        self.entries.append(new_entry)

        self.contents = [(w, self.options()) for w in self.get_pile_widgets()]

    def get_pile_widgets(self):
        return [
            self.header_row,
            urwid.Divider("-")
        ] + self.entries + [
            urwid.Padding(self.add_button, left=2, right=2)
        ]

    def get_value(self):
        values = {}
        for entry in self.entries:
            key = entry.key_edit.edit_text.strip()
            value = entry.value_edit.edit_text.strip()

            if key:
                if value.isdigit():
                    values[key] = int(value)
                elif value.replace('.', '', 1).isdigit() and value.count('.') <= 1:
                    values[key] = float(value)
                elif value.lower() == 'true':
                    values[key] = True
                elif value.lower() == 'false':
                    values[key] = False
                else:
                    values[key] = value

        return self.transform(values) if self.transform else values

    def set_value(self, value):
        self.entries = []

        if not value or not isinstance(value, dict):
            self.entries.append(self.create_entry_row())
        else:
            for key, val in value.items():
                self.entries.append(self.create_entry_row(key=key, value=str(val)))

        self.contents = [(w, self.options()) for w in self.get_pile_widgets()]

    def validate(self):
        values = self.get_value()
        self.error = None

        keys = [entry.key_edit.edit_text.strip() for entry in self.entries
                if entry.key_edit.edit_text.strip()]
        if len(keys) != len(set(keys)):
            self.error = "Duplicate keys are not allowed"
            self.error_widget.set_text(("error", self.error))
            return False

        for validation in self.validation_types:
            if validation == "required" and not values:
                self.error = "Atleast one parameter is required"
                break

        self.error_widget.set_text(("error", self.error or ""))
        return self.error is None