from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.GestureConfig import GestureConfig
from backend.camera_devices import build_camera_options
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.macros.macro_store import MacroStore
from frontend.widgets.settings.gesture_settings_page import GestureSettingsPage
from frontend.widgets.settings.macro_settings_page import MacroSettingsPage
from frontend.widgets.settings.settings_theme import (
    SettingsCard,
    apply_settings_theme,
    set_button_icon,
    set_button_role,
    set_label_role,
    set_label_tone,
)


class SettingsPanel(QWidget):
    """Generated settings editor for all gesture config keys."""

    settings_saved = Signal(dict)
    gesture_overrides_changed = Signal()
    CAMERA_OPTION_ROLE = Qt.UserRole + 1

    def __init__(self, ui_mode="dev", parent=None):
        super().__init__(parent)
        self.ui_mode = ui_mode
        self._field_controls = {}
        self._create_ui()

    def _create_ui(self):
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(16)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(16)

        nav_card = SettingsCard(surface="panel")
        self._submenu_list = QListWidget()
        self._submenu_list.setObjectName("settingsNavList")
        self._submenu_list.setMinimumWidth(180)
        self._submenu_list.setMaximumWidth(240)
        nav_title = QLabel("Settings Sections")
        set_label_role(nav_title, "section-title")
        set_label_tone(nav_title, "muted")
        nav_card.body_layout.addWidget(nav_title)
        nav_card.body_layout.addWidget(self._submenu_list, 1)
        content_row.addWidget(nav_card, 0)

        stack_card = SettingsCard(surface="panel")
        self._page_stack = QStackedWidget()
        stack_card.body_layout.addWidget(self._page_stack, 1)
        content_row.addWidget(stack_card, 1)

        self._gesture_settings_page = GestureSettingsPage()
        self._gesture_settings_page.overrides_changed.connect(self.gesture_overrides_changed)
        self._macro_settings_page = MacroSettingsPage()

        page_definitions = GestureConfig.get_page_definitions(ui_mode=self.ui_mode)
        ordered_page_names = list(page_definitions.keys())
        if "Keyboard" in ordered_page_names:
            ordered_page_names.insert(ordered_page_names.index("Keyboard") + 1, "Gestures")
            ordered_page_names.insert(ordered_page_names.index("Gestures") + 1, "Macros")
        else:
            ordered_page_names.insert(0, "Gestures")
            ordered_page_names.insert(1, "Macros")

        for page_name in ordered_page_names:
            self._submenu_list.addItem(page_name)
            if page_name == "Gestures":
                self._page_stack.addWidget(self._gesture_settings_page)
                continue
            if page_name == "Macros":
                self._page_stack.addWidget(self._macro_settings_page)
                continue
            groups = page_definitions[page_name]
            self._page_stack.addWidget(self._build_page_widget(page_name, groups))

        self._submenu_list.currentRowChanged.connect(self._page_stack.setCurrentIndex)
        if self._submenu_list.count() > 0:
            self._submenu_list.setCurrentRow(0)

        root_layout.addLayout(content_row)

        footer_card = SettingsCard(surface="panel")
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        footer_card.body_layout.addLayout(button_row)

        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self._on_save_clicked)
        set_button_role(self.save_button, "primary")
        set_button_icon(self.save_button, "save")
        button_row.addWidget(self.save_button)

        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self._on_reset_clicked)
        set_button_role(self.reset_button, "secondary")
        set_button_icon(self.reset_button, "reset")
        button_row.addWidget(self.reset_button)

        button_row.addStretch()
        root_layout.addWidget(footer_card)
        self.setLayout(root_layout)
        apply_settings_theme(self)

    def _build_page_widget(self, page_name, groups):
        """Build a scrollable settings page with grouped controls."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(2, 2, 2, 2)
        container_layout.setSpacing(14)

        header_card = SettingsCard(surface="subtle-card")
        title_label = QLabel(page_name)
        set_label_role(title_label, "page-title")
        description_label = QLabel(f"Adjust {page_name.lower()} configuration for the current profile.")
        set_label_tone(description_label, "muted")
        description_label.setWordWrap(True)
        header_card.body_layout.addWidget(title_label)
        header_card.body_layout.addWidget(description_label)
        container_layout.addWidget(header_card)

        for group_name, keys in groups.items():
            group_box = QGroupBox(group_name)
            group_layout = QFormLayout()
            group_layout.setContentsMargins(12, 12, 12, 12)
            group_layout.setSpacing(10)
            group_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            group_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
            group_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            group_layout.setHorizontalSpacing(18)

            label_width = self._label_column_width(keys)

            for key in keys:
                metadata = GestureConfig.get_field_metadata(key)
                control = self._build_control(key, metadata)
                self._field_controls[key] = control
                label = QLabel(metadata["label"])
                label.setProperty("settingsFormLabel", True)
                label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                label.setFixedWidth(label_width)
                group_layout.addRow(label, control["widget"])

            group_box.setLayout(group_layout)
            container_layout.addWidget(group_box)

        container_layout.addStretch()
        container.setLayout(container_layout)
        scroll_area.setWidget(container)
        return scroll_area

    def _label_column_width(self, keys):
        metrics = QFontMetrics(self.font())
        max_width = 0
        for key in keys:
            label = str(GestureConfig.get_field_metadata(key).get("label", ""))
            max_width = max(max_width, metrics.horizontalAdvance(label))
        return max(170, max_width + 14)

    def _build_control(self, key, metadata):
        control_type = metadata.get("type")
        nullable = bool(metadata.get("nullable", False))

        if control_type == "choice":
            combo = QComboBox()
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            control = {
                "widget": combo,
                "type": "choice",
                "combo": combo,
                "metadata": metadata,
                "key": key,
                "options": [],
            }
            self._populate_choice_options(control)
            return control

        if control_type == "bool":
            checkbox = QCheckBox()
            checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            return {
                "widget": checkbox,
                "type": "bool",
                "checkbox": checkbox,
            }

        if control_type == "int":
            if nullable:
                spinbox = self._create_int_spinbox(metadata)
                return self._wrap_nullable_numeric(spinbox, key, "int")
            spinbox = self._create_int_spinbox(metadata)
            return {
                "widget": spinbox,
                "type": "int",
                "spinbox": spinbox,
            }

        if control_type == "float":
            if nullable:
                spinbox = self._create_float_spinbox(metadata)
                return self._wrap_nullable_numeric(spinbox, key, "float")
            spinbox = self._create_float_spinbox(metadata)
            return {
                "widget": spinbox,
                "type": "float",
                "spinbox": spinbox,
            }

        raise ValueError(f"Unsupported control type '{control_type}' for key '{key}'")

    def _create_int_spinbox(self, metadata):
        spinbox = QSpinBox()
        spinbox.setRange(int(metadata.get("min", -1_000_000)), int(metadata.get("max", 1_000_000)))
        spinbox.setSingleStep(int(metadata.get("step", 1)))
        spinbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return spinbox

    def _create_float_spinbox(self, metadata):
        spinbox = QDoubleSpinBox()
        spinbox.setRange(float(metadata.get("min", -1_000_000.0)), float(metadata.get("max", 1_000_000.0)))
        spinbox.setSingleStep(float(metadata.get("step", 0.1)))
        spinbox.setDecimals(int(metadata.get("decimals", 3)))
        spinbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return spinbox

    def _wrap_nullable_numeric(self, spinbox, key, value_type):
        wrapper = QWidget()
        wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        enabled_checkbox = QCheckBox("Use value")
        enabled_checkbox.setChecked(False)
        spinbox.setEnabled(False)
        enabled_checkbox.toggled.connect(spinbox.setEnabled)

        layout.addWidget(enabled_checkbox)
        layout.addWidget(spinbox, 1)
        wrapper.setLayout(layout)

        return {
            "widget": wrapper,
            "type": value_type,
            "nullable": True,
            "enabled_checkbox": enabled_checkbox,
            "spinbox": spinbox,
            "key": key,
        }

    def _populate_choice_options(self, control, saved_values=None):
        """Populate a combo box from a metadata-driven options provider."""
        combo = control["combo"]
        metadata = control["metadata"]

        combo.blockSignals(True)
        combo.clear()

        provider_name = metadata.get("options_provider")
        options = []
        if provider_name == "camera_options":
            options = build_camera_options()
        else:
            options = list(metadata.get("options", []) or [])
        control["options"] = options

        for option in options:
            option_label = str(option.get("label", option.get("value", "")))
            option_value = option.get("index") if provider_name == "camera_options" else option.get("value")
            combo.addItem(option_label, option_value)
            item_index = combo.count() - 1
            combo.setItemData(item_index, option, self.CAMERA_OPTION_ROLE)

        selected_index = self._resolve_choice_index(control, saved_values)
        if selected_index >= 0:
            combo.setCurrentIndex(selected_index)
        elif combo.count() > 0:
            combo.setCurrentIndex(0)

        combo.blockSignals(False)

    def _resolve_choice_index(self, control, saved_values=None):
        """Resolve the best current choice item for saved config values."""
        combo = control["combo"]
        if combo.count() == 0:
            return -1

        if not saved_values:
            return 0

        provider_name = control["metadata"].get("options_provider")
        if provider_name != "camera_options":
            key = control["key"]
            saved_value = saved_values.get(key)
            for item_index in range(combo.count()):
                option_value = combo.itemData(item_index)
                if option_value == saved_value:
                    return item_index
            return 0

        key = control["key"]
        saved_index = int(saved_values.get(key, 0) or 0)
        saved_backend = int(saved_values.get("camera_backend", 0) or 0)
        saved_path = str(saved_values.get("camera_device_path", "") or "").strip().casefold()
        saved_name = str(saved_values.get("camera_device_name", "") or "").strip().casefold()

        if saved_path:
            for item_index in range(combo.count()):
                option = combo.itemData(item_index, self.CAMERA_OPTION_ROLE) or {}
                option_path = str(option.get("path", "") or "").strip().casefold()
                if option_path and option_path == saved_path:
                    return item_index

        if saved_name:
            matching_names = []
            for item_index in range(combo.count()):
                option = combo.itemData(item_index, self.CAMERA_OPTION_ROLE) or {}
                option_name = str(option.get("name", "") or "").strip().casefold()
                if option_name == saved_name:
                    matching_names.append(item_index)
            if len(matching_names) == 1:
                return matching_names[0]

        for item_index in range(combo.count()):
            option = combo.itemData(item_index, self.CAMERA_OPTION_ROLE) or {}
            if int(option.get("backend", 0) or 0) == saved_backend and int(option.get("index", 0) or 0) == saved_index:
                return item_index

        for item_index in range(combo.count()):
            option = combo.itemData(item_index, self.CAMERA_OPTION_ROLE) or {}
            if int(option.get("index", 0) or 0) == saved_index:
                return item_index

        return 0

    def load_values(self, values):
        """Load UI controls from a dictionary of config values."""
        for key, control in self._field_controls.items():
            if key not in values:
                continue

            value = values[key]
            control_type = control["type"]

            if control_type == "bool":
                control["checkbox"].setChecked(bool(value))
                continue

            if control_type == "choice":
                self._populate_choice_options(control, values)
                continue

            is_nullable = bool(control.get("nullable", False))
            if is_nullable:
                is_enabled = value is not None
                control["enabled_checkbox"].setChecked(is_enabled)
                if is_enabled:
                    control["spinbox"].setValue(value)
                continue

            control["spinbox"].setValue(value)

    def get_values(self):
        """Read all UI values into a dictionary."""
        values = {}
        for key, control in self._field_controls.items():
            control_type = control["type"]

            if control_type == "bool":
                values[key] = bool(control["checkbox"].isChecked())
                continue

            if control_type == "choice":
                combo_value = control["combo"].currentData()
                provider_name = control["metadata"].get("options_provider")
                if provider_name == "camera_options":
                    values[key] = int(combo_value) if combo_value is not None else 0
                else:
                    values[key] = combo_value

                selected_option = control["combo"].currentData(self.CAMERA_OPTION_ROLE) or {}
                if provider_name == "camera_options" and key == "camera_index":
                    values["camera_backend"] = int(selected_option.get("backend", 0) or 0)
                    values["camera_device_path"] = str(selected_option.get("path", "") or "")
                    values["camera_device_name"] = str(selected_option.get("name", "") or "")
                continue

            is_nullable = bool(control.get("nullable", False))
            if is_nullable and not control["enabled_checkbox"].isChecked():
                values[key] = None
                continue

            if control_type == "int":
                values[key] = int(control["spinbox"].value())
            else:
                values[key] = float(control["spinbox"].value())

        return values

    def load_from_config(self, config: GestureConfig):
        """Populate UI from GestureConfig."""
        self.load_values(config.config)
        self._gesture_settings_page.set_config(config)
        self._gesture_settings_page.set_override_store(GestureOverrideStore.from_config(config))
        self._macro_settings_page.set_config(config)
        self._macro_settings_page.set_macro_store(MacroStore.from_config(config))

    def _on_save_clicked(self):
        self.settings_saved.emit(self.get_values())

    def _on_reset_clicked(self):
        self.load_values(GestureConfig.DEFAULT_CONFIG.copy())
