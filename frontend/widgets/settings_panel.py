from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.GestureConfig import GestureConfig


class SettingsPanel(QWidget):
    """Generated settings editor for all gesture config keys."""

    settings_saved = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._field_controls = {}
        self._create_ui()

    def _create_ui(self):
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(8)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)

        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(10)

        for group_name, keys in GestureConfig.get_grouped_keys().items():
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
        self._scroll_area.setWidget(container)
        root_layout.addWidget(self._scroll_area)

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

    def _build_control(self, key, metadata):
        control_type = metadata.get("type")
        nullable = bool(metadata.get("nullable", False))

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
