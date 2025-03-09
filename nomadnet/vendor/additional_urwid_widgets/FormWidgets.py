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