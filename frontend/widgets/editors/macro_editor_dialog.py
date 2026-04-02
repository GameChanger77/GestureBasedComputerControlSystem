from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal, QSize
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.gesture_remap.pose_templates import HandPoseTemplate, PoseMatcherConfig, build_pose_template
from backend.gesture_remap.rule_overrides import (
    GestureRuleOverride,
    POINT_OVERRIDE_KIND,
    RULE_OVERRIDE_KIND,
)
from backend.macros.macro_models import (
    MacroActionStep,
    MacroPointTrigger,
    MacroRecord,
    MacroRuleTrigger,
)
from backend.macros.macro_step_catalog import KEY_OPTIONS, STEP_DEFINITIONS
from frontend.widgets.editors.dialog_windowing import (
    apply_bounded_dialog_geometry,
    configure_bounded_dialog_window,
    ensure_bounded_dialog_screen_tracking,
)
from frontend.widgets.editors.gesture_pose_editor_dialog import GesturePoseEditorWidget
from frontend.widgets.editors.gesture_rule_editor_widget import GestureRuleEditorWidget
from frontend.widgets.settings.settings_theme import (
    SettingsCard,
    SettingsPageHeader,
    apply_settings_theme,
    set_button_icon,
    set_button_role,
    set_label_role,
    set_label_tone,
)


@dataclass(frozen=True)
class _MacroTriggerContext:
    display_name: str
    default_description: str
    preview_pose_template: HandPoseTemplate


def _build_macro_preview_template() -> HandPoseTemplate:
    return build_pose_template(
        "Macro Trigger Preview",
        finger_curls={"index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
        thumb_curl=0.0,
    )


class MacroStepEditor(SettingsCard):
    changed = Signal()
    remove_requested = Signal(QWidget)
    move_up_requested = Signal(QWidget)
    move_down_requested = Signal(QWidget)

    def __init__(self, step: MacroActionStep | None = None, parent=None):
        super().__init__(surface="subtle-card", parent=parent)
        self._field_widgets = {}
        self._step = step or MacroActionStep.from_dict({"type": "tap_key", "params": {}})
        self._create_ui()
        index = self.step_type_combo.findData(self._step.step_type)
        self.step_type_combo.setCurrentIndex(index if index >= 0 else 0)
        self._rebuild_fields()

    def _create_ui(self):
        header = QHBoxLayout()
        header.addWidget(QLabel("Step Type"))
        self.step_type_combo = QComboBox()
        for step_type, definition in STEP_DEFINITIONS.items():
            self.step_type_combo.addItem(definition["label"], step_type)
        self.step_type_combo.currentIndexChanged.connect(self._rebuild_fields)
        header.addWidget(self.step_type_combo, 1)

        up_button = QPushButton("Up")
        set_button_role(up_button, "ghost")
        set_button_icon(up_button, "up")
        up_button.clicked.connect(lambda: self.move_up_requested.emit(self))
        header.addWidget(up_button)

        down_button = QPushButton("Down")
        set_button_role(down_button, "ghost")
        set_button_icon(down_button, "down")
        down_button.clicked.connect(lambda: self.move_down_requested.emit(self))
        header.addWidget(down_button)

        remove_button = QPushButton("Remove")
        set_button_role(remove_button, "danger")
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(remove_button)
        self.body_layout.addLayout(header)

        self.form = QFormLayout()
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(6)
        self.body_layout.addLayout(self.form)

    def _build_key_widget(self, value: str):
        combo = QComboBox()
        combo.setEditable(True)
        for option_value, option_label in KEY_OPTIONS:
            combo.addItem(option_label, option_value)
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.setEditText(str(value))
        combo.currentIndexChanged.connect(self.changed.emit)
        combo.editTextChanged.connect(self.changed.emit)
        return combo

    def _rebuild_fields(self):
        while self.form.rowCount():
            self.form.removeRow(0)
        self._field_widgets = {}

        step_type = self.current_step_type()
        definition = STEP_DEFINITIONS[step_type]
        params = self._step.params if self._step.step_type == step_type else {}
        for field in definition["fields"]:
            name = field["name"]
            value = params.get(name, field.get("default"))
            if field["type"] == "key":
                widget = self._build_key_widget(str(value))
            elif field["type"] == "key_list":
                widget = QLineEdit(", ".join(value if isinstance(value, list) else field.get("default", [])))
                widget.textChanged.connect(self.changed.emit)
            else:
                widget = QSpinBox()
                widget.setRange(int(field.get("min", -1_000_000)), int(field.get("max", 1_000_000)))
                widget.setValue(int(value))
                widget.valueChanged.connect(self.changed.emit)
            self._field_widgets[name] = (field, widget)
            self.form.addRow(field["label"], widget)
        self.changed.emit()

    def current_step_type(self) -> str:
        return str(self.step_type_combo.currentData())

    def to_step(self) -> MacroActionStep:
        params = {}
        for name, (field, widget) in self._field_widgets.items():
            if field["type"] == "key":
                params[name] = widget.currentText()
            elif field["type"] == "key_list":
                params[name] = [item.strip() for item in widget.text().split(",") if item.strip()]
            else:
                params[name] = int(widget.value())
        return MacroActionStep.from_dict({"type": self.current_step_type(), "params": params})


class MacroTriggerEditorWidget(QWidget):
    can_save_changed = Signal(bool)

    def __init__(self, *, config_source, point_trigger=None, rule_trigger=None, parent=None):
        super().__init__(parent)
        self.config_source = config_source
        self._default_rule_override = GestureRuleOverride(
            conditions=[],
            pending_frames=int(config_source.get("click_pending_frames", 3)),
            ending_frames=int(config_source.get("ending_frames", 2)),
        )
        self._context = _MacroTriggerContext(
            display_name="Macro Trigger",
            default_description="Create a standalone gesture that fires this macro once when recognized.",
            preview_pose_template=_build_macro_preview_template(),
        )
        self._can_save = False

        if point_trigger is not None:
            initial_kind = POINT_OVERRIDE_KIND
            initial_point_template = point_trigger.editor_pose_template or point_trigger.pose_template
            initial_hand = point_trigger.hand
            self._point_matcher_config = point_trigger.matcher_config
        else:
            initial_kind = RULE_OVERRIDE_KIND
            initial_point_template = self._context.preview_pose_template
            initial_hand = "right"
            self._point_matcher_config = PoseMatcherConfig()

        if rule_trigger is not None:
            initial_kind = RULE_OVERRIDE_KIND
            initial_rule_override = rule_trigger.rule_override
            initial_hand = rule_trigger.hand
        else:
            initial_rule_override = self._default_rule_override

        self._create_ui(initial_point_template, initial_rule_override)
        hand_index = self.hand_combo.findData(initial_hand)
        self.hand_combo.setCurrentIndex(hand_index if hand_index >= 0 else 0)
        self._set_selected_kind(initial_kind)

    @property
    def can_save(self) -> bool:
        return self._can_save

    def selected_kind(self) -> str:
        return RULE_OVERRIDE_KIND if self.rule_button.isChecked() else POINT_OVERRIDE_KIND

    def build_trigger(self):
        hand = str(self.hand_combo.currentData())
        if self.selected_kind() == RULE_OVERRIDE_KIND:
            return MacroRuleTrigger(
                hand=hand,
                rule_override=self.rule_editor.build_rule_override(),
            )
        result_template = self.point_editor.build_result_template()
        return MacroPointTrigger(
            hand=hand,
            pose_template=result_template,
            editor_pose_template=result_template,
            matcher_config=self._point_matcher_config,
        )

    def _create_ui(self, initial_point_template, initial_rule_override):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        summary = QLabel(
            "Choose one standalone trigger for this macro. Rule-based and 3D hand model triggers are mutually exclusive."
        )
        summary.setWordWrap(True)
        set_label_tone(summary, "muted")
        root.addWidget(summary)

        trigger_row = QHBoxLayout()
        trigger_row.setContentsMargins(0, 0, 0, 0)
        trigger_row.setSpacing(10)
        trigger_row.addWidget(QLabel("Trigger Hand"))
        self.hand_combo = QComboBox()
        self.hand_combo.addItem("Right", "right")
        self.hand_combo.addItem("Left", "left")
        self.hand_combo.addItem("Either", "either")
        self.hand_combo.currentIndexChanged.connect(self._refresh_can_save)
        trigger_row.addWidget(self.hand_combo)

        self.rule_button = QPushButton("Rule-Based")
        self.rule_button.setCheckable(True)
        set_button_role(self.rule_button, "segment")
        self.rule_button.clicked.connect(lambda: self._set_selected_kind(RULE_OVERRIDE_KIND))
        trigger_row.addSpacing(10)
        trigger_row.addWidget(self.rule_button)
        self.point_button = QPushButton("3D Hand Model")
        self.point_button.setCheckable(True)
        set_button_role(self.point_button, "segment")
        self.point_button.clicked.connect(lambda: self._set_selected_kind(POINT_OVERRIDE_KIND))
        trigger_row.addWidget(self.point_button)
        trigger_row.addStretch()
        root.addLayout(trigger_row)

        self.page_stack = QStackedWidget()
        self.rule_editor = GestureRuleEditorWidget(
            initial_rule_override=initial_rule_override,
            default_rule_override=self._default_rule_override,
            title_html="",
            parent=self,
        )
        self.point_editor = GesturePoseEditorWidget(
            self._context,
            initial_template=initial_point_template,
            validate_callback=None,
            parent=self,
        )
        self.point_editor_scroll = QScrollArea(self)
        self.point_editor_scroll.setWidgetResizable(True)
        self.point_editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.point_editor_scroll.setWidget(self.point_editor)
        self.page_stack.addWidget(self.rule_editor)
        self.page_stack.addWidget(self.point_editor_scroll)
        self.page_stack.setMinimumHeight(460)
        root.addWidget(self.page_stack, 1)

        self.rule_editor.can_save_changed.connect(self._refresh_can_save)
        self.point_editor.can_save_changed.connect(self._refresh_can_save)

    def _set_selected_kind(self, kind: str):
        is_rule = kind == RULE_OVERRIDE_KIND
        self.rule_button.setChecked(is_rule)
        self.point_button.setChecked(not is_rule)
        self.page_stack.setCurrentWidget(self.rule_editor if is_rule else self.point_editor_scroll)
        self._refresh_can_save()

    def _refresh_can_save(self, *_args):
        if self.selected_kind() == RULE_OVERRIDE_KIND:
            can_save = self.rule_editor.can_save
        else:
            can_save = self.point_editor.can_save
        if self._can_save != can_save:
            self._can_save = can_save
            self.can_save_changed.emit(can_save)


class MacroEditorDialog(QDialog):
    def __init__(self, *, config_source, existing_record: MacroRecord | None = None, parent=None):
        super().__init__(parent)
        self.existing_record = existing_record
        self.result_record: MacroRecord | None = None
        self._step_editors: list[MacroStepEditor] = []

        self.setWindowTitle("Edit Macro" if existing_record else "Create Macro")
        configure_bounded_dialog_window(
            self,
            default_size=QSize(1160, 820),
            min_size=QSize(920, 680),
            parent=parent,
        )

        point_trigger = existing_record.point_trigger if existing_record and existing_record.is_point_trigger else None
        rule_trigger = existing_record.rule_trigger if existing_record and existing_record.is_rule_trigger else None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        content_scroll = QScrollArea(self)
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_container = QFrame(self)
        content_root = QVBoxLayout(content_container)
        content_root.setContentsMargins(0, 0, 0, 0)
        content_root.setSpacing(14)

        header = SettingsPageHeader(
            "Edit Macro" if existing_record else "Create Macro",
            "Configure a standalone trigger gesture and the action chain it should execute in order.",
            parent=self,
        )
        content_root.addWidget(header)

        details_card = SettingsCard(surface="panel", parent=self)
        header_form = QFormLayout()
        self.name_edit = QLineEdit(existing_record.name if existing_record else "")
        self.name_edit.textChanged.connect(self._refresh_can_save)
        header_form.addRow("Name", self.name_edit)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Mouse", "mouse")
        self.mode_combo.addItem("Keyboard", "keyboard")
        self.mode_combo.addItem("Hotkey", "hotkey")
        if existing_record is not None:
            index = self.mode_combo.findData(existing_record.mode)
            self.mode_combo.setCurrentIndex(index if index >= 0 else 0)
        header_form.addRow("Mode", self.mode_combo)

        self.enabled_checkbox = QCheckBox("Enabled")
        self.enabled_checkbox.setChecked(existing_record.enabled if existing_record else True)
        header_form.addRow("State", self.enabled_checkbox)
        details_card.body_layout.addLayout(header_form)
        content_root.addWidget(details_card)

        trigger_card = SettingsCard(surface="panel", parent=self)
        trigger_title = QLabel("Trigger")
        set_label_role(trigger_title, "section-title")
        trigger_card.body_layout.addWidget(trigger_title)
        self.trigger_editor = MacroTriggerEditorWidget(
            config_source=config_source,
            point_trigger=point_trigger,
            rule_trigger=rule_trigger,
            parent=self,
        )
        self.trigger_editor.setMinimumHeight(580)
        self.trigger_editor.can_save_changed.connect(self._refresh_can_save)
        trigger_card.body_layout.addWidget(self.trigger_editor)
        trigger_card.setMinimumHeight(640)
        content_root.addWidget(trigger_card, 2)

        actions_card = SettingsCard(surface="panel", parent=self)
        actions_header = QHBoxLayout()
        actions_header.setContentsMargins(0, 0, 0, 0)
        actions_header.setSpacing(10)

        actions_title = QLabel("Actions")
        set_label_role(actions_title, "section-title")
        actions_header.addWidget(actions_title)

        add_step_button = QPushButton("Add Step")
        set_button_role(add_step_button, "primary")
        set_button_icon(add_step_button, "create")
        add_step_button.clicked.connect(self._add_step_editor)
        actions_header.addStretch()
        actions_header.addWidget(add_step_button)
        actions_card.body_layout.addLayout(actions_header)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.steps_layout = QVBoxLayout(container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(8)
        self.steps_layout.addStretch()
        scroll_area.setWidget(container)
        actions_card.body_layout.addWidget(scroll_area, 1)
        actions_card.setMinimumHeight(260)
        content_root.addWidget(actions_card, 1)

        content_scroll.setWidget(content_container)
        root.addWidget(content_scroll, 1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(12)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        set_label_tone(self.status_label, "muted")
        button_row.addWidget(self.status_label, 1)
        button_row.addStretch()
        self.save_button = QPushButton("Save")
        set_button_role(self.save_button, "primary")
        set_button_icon(self.save_button, "save")
        self.save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_button)
        cancel_button = QPushButton("Cancel")
        set_button_role(cancel_button, "secondary")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        root.addLayout(button_row)

        if existing_record:
            for step in existing_record.action_steps:
                self._add_step_editor(step)
        self._refresh_can_save()
        apply_settings_theme(self)

    def showEvent(self, event):
        super().showEvent(event)
        ensure_bounded_dialog_screen_tracking(self)
        apply_bounded_dialog_geometry(self, center=False)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            apply_bounded_dialog_geometry(self, center=False)

    def _add_step_editor(self, step: MacroActionStep | None = None):
        editor = MacroStepEditor(step=step, parent=self)
        editor.changed.connect(self._refresh_can_save)
        editor.remove_requested.connect(self._remove_step_editor)
        editor.move_up_requested.connect(self._move_step_editor_up)
        editor.move_down_requested.connect(self._move_step_editor_down)
        self._step_editors.append(editor)
        self.steps_layout.insertWidget(self.steps_layout.count() - 1, editor)
        self._refresh_can_save()

    def _remove_step_editor(self, editor: QWidget):
        if editor in self._step_editors:
            self._step_editors.remove(editor)
        self.steps_layout.removeWidget(editor)
        editor.deleteLater()
        self._refresh_can_save()

    def _move_step_editor_up(self, editor: QWidget):
        index = self._step_editors.index(editor)
        if index <= 0:
            return
        self._step_editors[index - 1], self._step_editors[index] = self._step_editors[index], self._step_editors[index - 1]
        self.steps_layout.insertWidget(index - 1, editor)
        self._refresh_can_save()

    def _move_step_editor_down(self, editor: QWidget):
        index = self._step_editors.index(editor)
        if index >= len(self._step_editors) - 1:
            return
        self._step_editors[index + 1], self._step_editors[index] = self._step_editors[index], self._step_editors[index + 1]
        self.steps_layout.insertWidget(index + 1, editor)
        self._refresh_can_save()

    def _build_action_steps(self) -> list[MacroActionStep]:
        return [editor.to_step() for editor in self._step_editors]

    def _refresh_can_save(self, *_args):
        validation_error = None
        can_save = bool(self.name_edit.text().strip()) and bool(self._step_editors) and self.trigger_editor.can_save
        if can_save:
            try:
                self._build_action_steps()
                self.trigger_editor.build_trigger()
            except Exception as exc:
                can_save = False
                validation_error = str(exc)

        if validation_error:
            self.status_label.setText(f"Macro is incomplete: {validation_error}")
            set_label_tone(self.status_label, "error")
        elif not self.name_edit.text().strip():
            self.status_label.setText("Enter a name for this macro.")
            set_label_tone(self.status_label, "muted")
        elif not self._step_editors:
            self.status_label.setText("Add at least one action step.")
            set_label_tone(self.status_label, "muted")
        elif not self.trigger_editor.can_save:
            self.status_label.setText("Trigger is incomplete.")
            set_label_tone(self.status_label, "warning")
        else:
            self.status_label.setText(f"{len(self._step_editors)} action step(s) configured.")
            set_label_tone(self.status_label, "success")
        self.save_button.setEnabled(can_save)

    def _on_save_clicked(self):
        trigger = self.trigger_editor.build_trigger()
        trigger_kind = self.trigger_editor.selected_kind()
        point_trigger = trigger if trigger_kind == POINT_OVERRIDE_KIND else None
        rule_trigger = trigger if trigger_kind == RULE_OVERRIDE_KIND else None
        self.result_record = MacroRecord.build_new(
            name=self.name_edit.text().strip(),
            mode=str(self.mode_combo.currentData()),
            trigger_kind=trigger_kind,
            point_trigger=point_trigger,
            rule_trigger=rule_trigger,
            action_steps=self._build_action_steps(),
            enabled=bool(self.enabled_checkbox.isChecked()),
            macro_id=self.existing_record.id if self.existing_record else None,
            created_at=self.existing_record.created_at if self.existing_record else None,
        )
        self.accept()
