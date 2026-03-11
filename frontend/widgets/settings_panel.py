from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.GestureConfig import GestureConfig
from backend.camera_devices import build_camera_options


class SettingsPanel(QWidget):
    """Generated settings editor for all gesture config keys."""

    settings_saved = Signal(dict)
    CAMERA_OPTION_ROLE = Qt.UserRole + 1

    def __init__(self, ui_mode="dev", parent=None):
        super().__init__(parent)
        self.ui_mode = ui_mode
        self._field_controls = {}
        self._create_ui()

    def _create_ui(self):
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(8)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(10)

        self._submenu_list = QListWidget()
        self._submenu_list.setMinimumWidth(180)
        self._submenu_list.setMaximumWidth(220)
        content_row.addWidget(self._submenu_list)

        self._page_stack = QStackedWidget()
        content_row.addWidget(self._page_stack, 1)

        page_definitions = GestureConfig.get_page_definitions(ui_mode=self.ui_mode)
        for page_name, groups in page_definitions.items():
            self._submenu_list.addItem(page_name)
            self._page_stack.addWidget(self._build_page_widget(groups))

        self._submenu_list.currentRowChanged.connect(self._page_stack.setCurrentIndex)
        if self._submenu_list.count() > 0:
            self._submenu_list.setCurrentRow(0)

        root_layout.addLayout(content_row)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_button)

        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self._on_reset_clicked)
        button_row.addWidget(self.reset_button)

        button_row.addStretch()
        root_layout.addLayout(button_row)
        self.setLayout(root_layout)

    def _build_page_widget(self, groups):
        """Build a scrollable settings page with grouped controls."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(10)

        for group_name, keys in groups.items():
            group_box = QGroupBox(group_name)
            group_layout = QFormLayout()
            group_layout.setContentsMargins(8, 8, 8, 8)
            group_layout.setSpacing(6)

            for key in keys:
                metadata = GestureConfig.get_field_metadata(key)
                control = self._build_control(key, metadata)
                self._field_controls[key] = control
                group_layout.addRow(metadata["label"], control["widget"])

            group_box.setLayout(group_layout)
            container_layout.addWidget(group_box)

        container_layout.addStretch()
        container.setLayout(container_layout)
        scroll_area.setWidget(container)
        return scroll_area

    def _build_control(self, key, metadata):
        control_type = metadata.get("type")
        nullable = bool(metadata.get("nullable", False))

        if control_type == "choice":
            combo = QComboBox()
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
        return spinbox

    def _create_float_spinbox(self, metadata):
        spinbox = QDoubleSpinBox()
        spinbox.setRange(float(metadata.get("min", -1_000_000.0)), float(metadata.get("max", 1_000_000.0)))
        spinbox.setSingleStep(float(metadata.get("step", 0.1)))
        spinbox.setDecimals(int(metadata.get("decimals", 3)))
        return spinbox

    def _wrap_nullable_numeric(self, spinbox, key, value_type):
        wrapper = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        enabled_checkbox = QCheckBox("Use value")
        enabled_checkbox.setChecked(False)
        spinbox.setEnabled(False)
        enabled_checkbox.toggled.connect(spinbox.setEnabled)

        layout.addWidget(enabled_checkbox)
        layout.addWidget(spinbox)
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
        control["options"] = options

        for option in options:
            combo.addItem(option["label"], option["index"])
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
                values[key] = int(combo_value) if combo_value is not None else 0

                selected_option = control["combo"].currentData(self.CAMERA_OPTION_ROLE) or {}
                if key == "camera_index":
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

    def _on_save_clicked(self):
        self.settings_saved.emit(self.get_values())

    def _on_reset_clicked(self):
        self.load_values(GestureConfig.DEFAULT_CONFIG.copy())
