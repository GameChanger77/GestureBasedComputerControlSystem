from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QSize, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
    QSpinBox,
)

from backend.custom_rules.condition_catalog import CONDITION_DEFINITIONS, LANDMARK_OPTIONS
from backend.gesture_remap.pose_templates import HandPoseTemplate, PoseMatcherConfig, build_pose_template
from backend.gesture_remap.rule_overrides import (
    GestureRuleOverride,
    POINT_OVERRIDE_KIND,
    RULE_OVERRIDE_KIND,
)
from backend.macros.macro_models import (
    DOMINANT_TRIGGER_HAND,
    MacroPointTrigger,
    MacroRecord,
    MacroRuleTrigger,
    MacroSwipeConfig,
    RULE_TRIGGER_TYPE_POSE,
    RULE_TRIGGER_TYPE_SWIPE,
)
from backend.platforms.KeyMappings import (
    format_shortcut_key_label,
    get_shortcut_key_options,
    normalize_shortcut_key,
    summarize_shortcut_keys,
)
from backend.platforms.KeyboardBackendFactory import normalize_os_name
from frontend.widgets.editors.dialog_windowing import (
    apply_bounded_dialog_geometry,
    configure_bounded_dialog_window,
    ensure_bounded_dialog_screen_tracking,
)
from frontend.widgets.editors.gesture_pose_editor_dialog import GesturePoseEditorWidget
from frontend.widgets.editors.gesture_rule_editor_widget import GestureRuleEditorWidget, RuleConditionEditor
from frontend.widgets.settings.settings_theme import (
    SettingsCard,
    SettingsPageHeader,
    apply_settings_theme,
    set_button_icon,
    set_button_role,
    set_label_role,
    set_label_tone,
)


class _NoWheelComboBox(QComboBox):
    """Editable combo box that keeps typing/autocomplete but ignores wheel scrolling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view().installEventFilter(self)
        self.view().viewport().installEventFilter(self)

    def wheelEvent(self, event):
        event.ignore()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel:
            event.ignore()
            return True
        return super().eventFilter(watched, event)


@dataclass(frozen=True)
class _MacroTriggerContext:
    display_name: str
    default_description: str
    preview_pose_template: HandPoseTemplate


_MACRO_EXCLUDED_RULE_OPS = {"hand_exists", "hand_count_eq"}
_MACRO_ALLOWED_RULE_OPS = tuple(
    op for op in CONDITION_DEFINITIONS.keys() if op not in _MACRO_EXCLUDED_RULE_OPS
)


def _build_macro_preview_template() -> HandPoseTemplate:
    return build_pose_template(
        "Macro Trigger Preview",
        finger_curls={"index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
        thumb_curl=0.0,
    )


class _ShortcutChip(SettingsCard):
    remove_requested = Signal(QWidget)

    def __init__(self, label: str, parent=None):
        super().__init__(surface="subtle-card", parent=parent)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(QLabel(label))
        row.addStretch()
        remove_button = QPushButton("Remove")
        set_button_role(remove_button, "danger")
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        row.addWidget(remove_button)
        self.body_layout.addLayout(row)


class ShortcutChordEditor(QWidget):
    can_save_changed = Signal(bool)

    def __init__(self, *, shortcut_keys=None, target_os: str | None = None, parent=None):
        super().__init__(parent)
        self.target_os = normalize_os_name(target_os)
        self._shortcut_keys = list(shortcut_keys or [])
        self._chips: list[_ShortcutChip] = []
        self._can_save = False
        self._create_ui()
        self._refresh()

    @property
    def can_save(self) -> bool:
        return self._can_save

    def build_shortcut_keys(self) -> list[str]:
        return list(self._shortcut_keys)

    def _create_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        summary = QLabel("Add the keys that should be pressed together as one shortcut chord.")
        summary.setWordWrap(True)
        set_label_tone(summary, "muted")
        root.addWidget(summary)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.setSpacing(8)
        self.key_combo = _NoWheelComboBox()
        self.key_combo.setEditable(True)
        for option_value, option_label in get_shortcut_key_options(self.target_os):
            self.key_combo.addItem(option_label, option_value)
        add_row.addWidget(self.key_combo, 1)

        add_button = QPushButton("Add Key")
        set_button_role(add_button, "primary")
        set_button_icon(add_button, "create")
        add_button.clicked.connect(self._add_selected_key)
        add_row.addWidget(add_button)

        clear_button = QPushButton("Clear")
        set_button_role(clear_button, "secondary")
        clear_button.clicked.connect(self._clear_keys)
        add_row.addWidget(clear_button)
        root.addLayout(add_row)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        container = QWidget()
        self.chips_layout = QVBoxLayout(container)
        self.chips_layout.setContentsMargins(0, 0, 0, 0)
        self.chips_layout.setSpacing(8)
        self.chips_layout.addStretch()
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(container)
        scroll.setMinimumHeight(180)
        root.addWidget(scroll, 1)

    def _set_can_save(self, can_save: bool):
        can_save = bool(can_save)
        if self._can_save == can_save:
            return
        self._can_save = can_save
        self.can_save_changed.emit(can_save)

    def _add_selected_key(self):
        raw_value = self.key_combo.currentData()
        if raw_value is None:
            raw_value = self.key_combo.currentText()
        normalized = normalize_shortcut_key(raw_value, self.target_os)
        if not normalized:
            self.status_label.setText(f"'{self.key_combo.currentText().strip()}' is not a valid key for {self.target_os}.")
            set_label_tone(self.status_label, "error")
            return
        if normalized not in self._shortcut_keys:
            self._shortcut_keys.append(normalized)
        self.key_combo.setEditText("")
        self._refresh()

    def _clear_keys(self):
        if not self._shortcut_keys:
            return
        self._shortcut_keys = []
        self._refresh()

    def _remove_chip(self, chip: QWidget):
        for index, existing in enumerate(list(self._chips)):
            if existing is chip:
                del self._shortcut_keys[index]
                break
        self._refresh()

    def _refresh(self):
        for chip in self._chips:
            self.chips_layout.removeWidget(chip)
            chip.deleteLater()
        self._chips = []

        for key in self._shortcut_keys:
            chip = _ShortcutChip(format_shortcut_key_label(key, self.target_os), parent=self)
            chip.remove_requested.connect(self._remove_chip)
            self._chips.append(chip)
            self.chips_layout.insertWidget(self.chips_layout.count() - 1, chip)

        if self._shortcut_keys:
            self.summary_label.setText(f"Shortcut: {summarize_shortcut_keys(self._shortcut_keys, self.target_os)}")
            set_label_tone(self.summary_label, "success")
            self.status_label.setText(f"{len(self._shortcut_keys)} key(s) will be pressed together.")
            set_label_tone(self.status_label, "muted")
        else:
            self.summary_label.setText("Shortcut: none")
            set_label_tone(self.summary_label, "muted")
            self.status_label.setText("Add at least one key to build a shortcut.")
            set_label_tone(self.status_label, "warning")

        self._set_can_save(bool(self._shortcut_keys))


class MacroSwipeTriggerEditorWidget(QWidget):
    can_save_changed = Signal(bool)

    def __init__(
        self,
        *,
        config_source,
        initial_trigger: MacroRuleTrigger | None = None,
        allowed_ops: list[str] | tuple[str, ...] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.config_source = config_source
        self._allowed_ops = list(allowed_ops or CONDITION_DEFINITIONS.keys())
        self._default_start_rule = GestureRuleOverride(
            conditions=[],
            pending_frames=1,
            ending_frames=1,
        )
        self._default_swipe_config = MacroSwipeConfig.from_dict({})
        self._condition_editors: list[RuleConditionEditor] = []
        self._can_save = False
        self._create_ui()

        if initial_trigger is not None and initial_trigger.is_swipe_trigger:
            self._load_trigger(initial_trigger)
        else:
            self._load_defaults()

    @property
    def can_save(self) -> bool:
        return self._can_save

    def build_trigger(self, hand: str) -> MacroRuleTrigger:
        swipe_config = MacroSwipeConfig.from_dict(
            {
                "tracked_point": self.tracked_point_combo.currentData(),
                "direction": self.direction_combo.currentData(),
                "min_displacement": float(self.min_displacement_spinbox.value()),
                "min_speed": float(self.min_speed_spinbox.value()),
                "min_smoothness": float(self.min_smoothness_spinbox.value()),
                "start_confirm_frames": int(self.start_confirm_frames_spinbox.value()),
                "timeout_frames": int(self.timeout_frames_spinbox.value()),
            }
        )
        start_rule_override = GestureRuleOverride.from_dict(
            {
                "conditions": [editor.to_condition() for editor in self._condition_editors],
                "confirm": {"pending_frames": 1, "ending_frames": 1},
            }
        )
        return MacroRuleTrigger(
            hand=hand,
            trigger_type=RULE_TRIGGER_TYPE_SWIPE,
            rule_override=None,
            start_rule_override=start_rule_override,
            swipe_config=swipe_config,
        )

    def _create_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        intro = QLabel(
            "Define the starting pose for the swipe, then tune the motion thresholds that confirm a left, right, up, or down swipe."
        )
        intro.setWordWrap(True)
        set_label_tone(intro, "muted")
        root.addWidget(intro)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)
        add_button = QPushButton("Add Start Condition")
        set_button_role(add_button, "primary")
        set_button_icon(add_button, "create")
        add_button.clicked.connect(lambda: self._add_condition_editor())
        actions_row.addWidget(add_button)
        restore_button = QPushButton("Restore Swipe Defaults")
        set_button_role(restore_button, "secondary")
        set_button_icon(restore_button, "reset")
        restore_button.clicked.connect(self._load_defaults)
        actions_row.addWidget(restore_button)
        actions_row.addStretch()
        root.addLayout(actions_row)

        motion_group = QGroupBox("Swipe Motion")
        motion_form = QFormLayout(motion_group)
        self.tracked_point_combo = QComboBox()
        for value, label in LANDMARK_OPTIONS:
            self.tracked_point_combo.addItem(label, value)
        self.tracked_point_combo.currentIndexChanged.connect(self._refresh_status)
        motion_form.addRow("Tracked Point", self.tracked_point_combo)

        self.direction_combo = QComboBox()
        self.direction_combo.addItem("Left", "left")
        self.direction_combo.addItem("Right", "right")
        self.direction_combo.addItem("Up", "up")
        self.direction_combo.addItem("Down", "down")
        self.direction_combo.currentIndexChanged.connect(self._refresh_status)
        motion_form.addRow("Direction", self.direction_combo)

        self.min_displacement_spinbox = QDoubleSpinBox()
        self.min_displacement_spinbox.setRange(0.01, 1.0)
        self.min_displacement_spinbox.setDecimals(3)
        self.min_displacement_spinbox.setSingleStep(0.01)
        self.min_displacement_spinbox.valueChanged.connect(self._refresh_status)
        motion_form.addRow("Min Displacement", self.min_displacement_spinbox)

        self.min_speed_spinbox = QDoubleSpinBox()
        self.min_speed_spinbox.setRange(0.01, 10.0)
        self.min_speed_spinbox.setDecimals(3)
        self.min_speed_spinbox.setSingleStep(0.05)
        self.min_speed_spinbox.valueChanged.connect(self._refresh_status)
        motion_form.addRow("Min Speed", self.min_speed_spinbox)

        self.min_smoothness_spinbox = QDoubleSpinBox()
        self.min_smoothness_spinbox.setRange(0.0, 1.0)
        self.min_smoothness_spinbox.setDecimals(3)
        self.min_smoothness_spinbox.setSingleStep(0.05)
        self.min_smoothness_spinbox.valueChanged.connect(self._refresh_status)
        motion_form.addRow("Min Straightness", self.min_smoothness_spinbox)

        self.start_confirm_frames_spinbox = QSpinBox()
        self.start_confirm_frames_spinbox.setRange(1, 60)
        self.start_confirm_frames_spinbox.valueChanged.connect(self._refresh_status)
        motion_form.addRow("Start Confirm Frames", self.start_confirm_frames_spinbox)

        self.timeout_frames_spinbox = QSpinBox()
        self.timeout_frames_spinbox.setRange(2, 120)
        self.timeout_frames_spinbox.valueChanged.connect(self._refresh_status)
        motion_form.addRow("Timeout Frames", self.timeout_frames_spinbox)
        root.addWidget(motion_group)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        container = QWidget()
        self.conditions_layout = QVBoxLayout(container)
        self.conditions_layout.setContentsMargins(0, 0, 0, 0)
        self.conditions_layout.setSpacing(8)
        self.conditions_layout.addStretch()
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(container)
        scroll.setMinimumHeight(240)
        root.addWidget(scroll, 1)

    def _set_can_save(self, can_save: bool):
        can_save = bool(can_save)
        if self._can_save == can_save:
            return
        self._can_save = can_save
        self.can_save_changed.emit(can_save)

    def _load_defaults(self):
        while self._condition_editors:
            self._remove_condition_editor(self._condition_editors[0])
        self._apply_swipe_config(self._default_swipe_config)
        self._refresh_status()

    def _load_trigger(self, trigger: MacroRuleTrigger):
        while self._condition_editors:
            self._remove_condition_editor(self._condition_editors[0])
        for condition in trigger.start_rule_override.conditions:
            self._add_condition_editor(condition)
        self._apply_swipe_config(trigger.swipe_config)
        self._refresh_status()

    def _apply_swipe_config(self, swipe_config: MacroSwipeConfig):
        self.tracked_point_combo.setCurrentIndex(
            max(0, self.tracked_point_combo.findData(swipe_config.tracked_point))
        )
        self.direction_combo.setCurrentIndex(max(0, self.direction_combo.findData(swipe_config.direction)))
        self.min_displacement_spinbox.setValue(float(swipe_config.min_displacement))
        self.min_speed_spinbox.setValue(float(swipe_config.min_speed))
        self.min_smoothness_spinbox.setValue(float(swipe_config.min_smoothness))
        self.start_confirm_frames_spinbox.setValue(int(swipe_config.start_confirm_frames))
        self.timeout_frames_spinbox.setValue(int(swipe_config.timeout_frames))

    def _add_condition_editor(self, condition: dict | None = None):
        editor = RuleConditionEditor(condition=condition, allowed_ops=self._allowed_ops, parent=self)
        editor.changed.connect(self._refresh_status)
        editor.remove_requested.connect(self._remove_condition_editor)
        self._condition_editors.append(editor)
        self.conditions_layout.insertWidget(self.conditions_layout.count() - 1, editor)
        self._refresh_status()

    def _remove_condition_editor(self, editor: QWidget):
        if editor in self._condition_editors:
            self._condition_editors.remove(editor)
        self.conditions_layout.removeWidget(editor)
        editor.deleteLater()
        self._refresh_status()

    def _refresh_status(self, *_args):
        can_save = len(self._condition_editors) > 0
        validation_error = None
        if can_save:
            try:
                self.build_trigger(DOMINANT_TRIGGER_HAND)
            except Exception as exc:
                can_save = False
                validation_error = str(exc)

        if validation_error:
            self.status_label.setText(f"Swipe trigger is incomplete: {validation_error}")
            set_label_tone(self.status_label, "error")
        elif not self._condition_editors:
            self.status_label.setText("Add at least one start condition for the swipe.")
            set_label_tone(self.status_label, "warning")
        else:
            self.status_label.setText(
                f"Swipe trigger ready: {self.direction_combo.currentText().lower()} swipe from "
                f"{self.tracked_point_combo.currentText().lower()}."
            )
            set_label_tone(self.status_label, "success")
        self._set_can_save(can_save)


class MacroRuleTriggerEditorWidget(QWidget):
    can_save_changed = Signal(bool)

    def __init__(self, *, config_source, rule_trigger: MacroRuleTrigger | None = None, parent=None):
        super().__init__(parent)
        self._default_rule_override = GestureRuleOverride(
            conditions=[],
            pending_frames=int(config_source.get("click_pending_frames", 3)),
            ending_frames=int(config_source.get("ending_frames", 2)),
        )
        self._can_save = False
        self._create_ui(config_source, rule_trigger)

    @property
    def can_save(self) -> bool:
        return self._can_save

    def selected_trigger_type(self) -> str:
        return RULE_TRIGGER_TYPE_SWIPE if self.swipe_button.isChecked() else RULE_TRIGGER_TYPE_POSE

    def build_trigger(self, hand: str) -> MacroRuleTrigger:
        if self.selected_trigger_type() == RULE_TRIGGER_TYPE_SWIPE:
            return self.swipe_editor.build_trigger(hand)
        return MacroRuleTrigger(
            hand=hand,
            trigger_type=RULE_TRIGGER_TYPE_POSE,
            rule_override=self.pose_editor.build_rule_override(),
            start_rule_override=None,
            swipe_config=None,
        )

    def _create_ui(self, config_source, rule_trigger):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        summary = QLabel("Choose either a static rule-based pose or a swipe that starts from a rule-defined pose.")
        summary.setWordWrap(True)
        set_label_tone(summary, "muted")
        root.addWidget(summary)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(8)
        self.pose_button = QPushButton("Pose")
        self.pose_button.setCheckable(True)
        set_button_role(self.pose_button, "segment")
        self.pose_button.clicked.connect(lambda: self._set_selected_trigger_type(RULE_TRIGGER_TYPE_POSE))
        toggle_row.addWidget(self.pose_button)
        self.swipe_button = QPushButton("Swipe")
        self.swipe_button.setCheckable(True)
        set_button_role(self.swipe_button, "segment")
        self.swipe_button.clicked.connect(lambda: self._set_selected_trigger_type(RULE_TRIGGER_TYPE_SWIPE))
        toggle_row.addWidget(self.swipe_button)
        toggle_row.addStretch()
        root.addLayout(toggle_row)

        initial_rule_override = (
            rule_trigger.rule_override
            if rule_trigger is not None and rule_trigger.is_pose_trigger
            else self._default_rule_override
        )
        self.pose_editor = GestureRuleEditorWidget(
            initial_rule_override=initial_rule_override,
            default_rule_override=self._default_rule_override,
            title_html=(
                "<b>Rule-Based Pose Trigger</b><br>"
                "Configure the hand pose that should activate this shortcut."
            ),
            allowed_ops=_MACRO_ALLOWED_RULE_OPS,
            parent=self,
        )
        self.swipe_editor = MacroSwipeTriggerEditorWidget(
            config_source=config_source,
            initial_trigger=rule_trigger if rule_trigger is not None and rule_trigger.is_swipe_trigger else None,
            allowed_ops=_MACRO_ALLOWED_RULE_OPS,
            parent=self,
        )
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.pose_editor)
        self.stack.addWidget(self.swipe_editor)
        root.addWidget(self.stack, 1)

        self.pose_editor.can_save_changed.connect(self._refresh_can_save)
        self.swipe_editor.can_save_changed.connect(self._refresh_can_save)
        initial_type = (
            RULE_TRIGGER_TYPE_SWIPE
            if rule_trigger is not None and rule_trigger.is_swipe_trigger
            else RULE_TRIGGER_TYPE_POSE
        )
        self._set_selected_trigger_type(initial_type)

    def _set_selected_trigger_type(self, trigger_type: str):
        is_swipe = trigger_type == RULE_TRIGGER_TYPE_SWIPE
        self.pose_button.setChecked(not is_swipe)
        self.swipe_button.setChecked(is_swipe)
        self.stack.setCurrentWidget(self.swipe_editor if is_swipe else self.pose_editor)
        self._refresh_can_save()

    def _refresh_can_save(self, *_args):
        can_save = self.swipe_editor.can_save if self.selected_trigger_type() == RULE_TRIGGER_TYPE_SWIPE else self.pose_editor.can_save
        if self._can_save != can_save:
            self._can_save = can_save
            self.can_save_changed.emit(can_save)


class MacroTriggerEditorWidget(QWidget):
    can_save_changed = Signal(bool)

    def __init__(
        self,
        *,
        config_source,
        point_trigger=None,
        rule_trigger=None,
        validate_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.validate_callback = validate_callback
        self._context = _MacroTriggerContext(
            display_name="Macro Trigger",
            default_description="Create a standalone gesture that fires this shortcut once when recognized.",
            preview_pose_template=_build_macro_preview_template(),
        )
        self._can_save = False
        self._point_matcher_config = point_trigger.matcher_config if point_trigger is not None else PoseMatcherConfig()
        initial_point_template = (
            point_trigger.editor_pose_template or point_trigger.pose_template
            if point_trigger is not None
            else self._context.preview_pose_template
        )
        self._create_ui(config_source, initial_point_template, rule_trigger)
        initial_kind = RULE_OVERRIDE_KIND if rule_trigger is not None else POINT_OVERRIDE_KIND if point_trigger is not None else RULE_OVERRIDE_KIND
        self._set_selected_kind(initial_kind)

    @property
    def can_save(self) -> bool:
        return self._can_save

    def selected_kind(self) -> str:
        return RULE_OVERRIDE_KIND if self.rule_button.isChecked() else POINT_OVERRIDE_KIND

    def build_trigger(self):
        hand = DOMINANT_TRIGGER_HAND
        if self.selected_kind() == RULE_OVERRIDE_KIND:
            return self.rule_editor.build_trigger(hand)
        result_template = self.point_editor.build_result_template()
        return MacroPointTrigger(
            hand=hand,
            pose_template=result_template,
            editor_pose_template=result_template,
            matcher_config=self._point_matcher_config,
        )

    def refresh_validation(self):
        if self.selected_kind() == POINT_OVERRIDE_KIND:
            self.point_editor._refresh_status()

    def _create_ui(self, config_source, initial_point_template, rule_trigger):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        summary = QLabel(
            "Choose one standalone trigger for this shortcut. Rule-based and 3D hand model triggers are mutually exclusive, and the trigger always uses the configured dominant hand."
        )
        summary.setWordWrap(True)
        set_label_tone(summary, "muted")
        root.addWidget(summary)

        trigger_row = QHBoxLayout()
        trigger_row.setContentsMargins(0, 0, 0, 0)
        trigger_row.setSpacing(10)

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
        self.rule_editor = MacroRuleTriggerEditorWidget(
            config_source=config_source,
            rule_trigger=rule_trigger,
            parent=self,
        )
        self.point_editor = GesturePoseEditorWidget(
            self._context,
            initial_template=initial_point_template,
            validate_callback=self.validate_callback,
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
        self.refresh_validation()

    def _refresh_can_save(self, *_args):
        can_save = self.rule_editor.can_save if self.selected_kind() == RULE_OVERRIDE_KIND else self.point_editor.can_save
        if self._can_save != can_save:
            self._can_save = can_save
            self.can_save_changed.emit(can_save)


class MacroEditorDialog(QDialog):
    def __init__(
        self,
        *,
        config_source,
        existing_record: MacroRecord | None = None,
        validate_point_trigger_callback=None,
        target_os: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.existing_record = existing_record
        self.target_os = normalize_os_name(target_os)
        self.result_record: MacroRecord | None = None
        self.setWindowTitle("Edit Macro" if existing_record else "Create Macro")
        configure_bounded_dialog_window(
            self,
            default_size=QSize(1120, 820),
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
            "Configure one trigger gesture and one shortcut chord. Each macro fires once per activation and must disengage before it can fire again.",
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
            self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(existing_record.mode)))
        self.mode_combo.currentIndexChanged.connect(self._refresh_can_save)
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
            validate_callback=None,
            parent=self,
        )
        if callable(validate_point_trigger_callback):
            self.trigger_editor.point_editor.validate_callback = (
                lambda candidate, matcher_config: validate_point_trigger_callback(
                    macro_id=self.existing_record.id if self.existing_record else None,
                    mode=str(self.mode_combo.currentData()),
                    candidate_template=candidate,
                    matcher_config=matcher_config,
                )
            )
            self.trigger_editor.refresh_validation()
        self.trigger_editor.setMinimumHeight(580)
        self.trigger_editor.can_save_changed.connect(self._refresh_can_save)
        trigger_card.body_layout.addWidget(self.trigger_editor)
        trigger_card.setMinimumHeight(640)
        content_root.addWidget(trigger_card, 2)

        shortcut_card = SettingsCard(surface="panel", parent=self)
        shortcut_title = QLabel("Shortcut")
        set_label_role(shortcut_title, "section-title")
        shortcut_card.body_layout.addWidget(shortcut_title)
        self.shortcut_editor = ShortcutChordEditor(
            shortcut_keys=existing_record.shortcut_keys if existing_record else [],
            target_os=self.target_os,
            parent=self,
        )
        self.shortcut_editor.can_save_changed.connect(self._refresh_can_save)
        shortcut_card.body_layout.addWidget(self.shortcut_editor)
        content_root.addWidget(shortcut_card, 1)

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

        self.mode_combo.currentIndexChanged.connect(lambda *_args: self.trigger_editor.refresh_validation())
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

    def _refresh_can_save(self, *_args):
        validation_error = None
        can_save = (
            bool(self.name_edit.text().strip())
            and self.trigger_editor.can_save
            and self.shortcut_editor.can_save
        )
        if can_save:
            try:
                self.trigger_editor.build_trigger()
                self.shortcut_editor.build_shortcut_keys()
            except Exception as exc:
                can_save = False
                validation_error = str(exc)

        if validation_error:
            self.status_label.setText(f"Macro is incomplete: {validation_error}")
            set_label_tone(self.status_label, "error")
        elif not self.name_edit.text().strip():
            self.status_label.setText("Enter a name for this macro.")
            set_label_tone(self.status_label, "muted")
        elif not self.trigger_editor.can_save:
            self.status_label.setText("Trigger is incomplete.")
            set_label_tone(self.status_label, "warning")
        elif not self.shortcut_editor.can_save:
            self.status_label.setText("Shortcut is incomplete.")
            set_label_tone(self.status_label, "warning")
        else:
            self.status_label.setText(
                f"Shortcut ready: {summarize_shortcut_keys(self.shortcut_editor.build_shortcut_keys(), self.target_os)}"
            )
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
            shortcut_keys=self.shortcut_editor.build_shortcut_keys(),
            enabled=bool(self.enabled_checkbox.isChecked()),
            macro_id=self.existing_record.id if self.existing_record else None,
            created_at=self.existing_record.created_at if self.existing_record else None,
            target_os=self.target_os,
        )
        self.accept()
