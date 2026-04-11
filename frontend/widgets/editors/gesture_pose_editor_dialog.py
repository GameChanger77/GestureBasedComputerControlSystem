from __future__ import annotations

import numpy as np
from PySide6.QtCore import QSize
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.gesture_remap.pose_templates import HandPoseTemplate, PoseMatcherConfig, compare_pose_templates
from frontend.widgets.editors.dialog_windowing import configure_bounded_dialog_window
from frontend.widgets.editors.hand_rig_scene import HandRigScene
from frontend.widgets.settings.settings_theme import (
    SettingsCard,
    apply_settings_theme,
    set_button_icon,
    set_button_role,
    set_label_tone,
)


LANDMARK_NAMES = [
    "Wrist",
    "Thumb CMC",
    "Thumb MCP",
    "Thumb IP",
    "Thumb Tip",
    "Index MCP",
    "Index PIP",
    "Index DIP",
    "Index Tip",
    "Middle MCP",
    "Middle PIP",
    "Middle DIP",
    "Middle Tip",
    "Ring MCP",
    "Ring PIP",
    "Ring DIP",
    "Ring Tip",
    "Pinky MCP",
    "Pinky PIP",
    "Pinky DIP",
    "Pinky Tip",
]


class GesturePoseEditorWidget(QWidget):
    can_save_changed = Signal(bool)

    def __init__(
        self,
        gesture_definition,
        initial_template: HandPoseTemplate,
        validate_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.gesture_definition = gesture_definition
        self.default_template = gesture_definition.preview_pose_template
        self.current_template = initial_template
        self.validate_callback = validate_callback
        self.matcher_config = PoseMatcherConfig()
        self._suppress_updates = False
        self._landmarks = self.current_template.as_array().copy()
        self._can_save = True

        self._create_ui()
        self._apply_landmarks(self._landmarks)

    @property
    def can_save(self) -> bool:
        return self._can_save

    def build_result_template(self) -> HandPoseTemplate:
        return HandPoseTemplate.from_array(
            self.gesture_definition.display_name,
            self._landmarks,
        )

    def _create_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        title_card = SettingsCard(surface="subtle-card", parent=self)
        title = QLabel(
            f"<b>{self.gesture_definition.display_name}</b><br>"
            f"{self.gesture_definition.default_description}<br>"
            "Use the Blender hand as a stable reference model. Drag the landmark handles and skeleton overlay to author the saved pose, right-drag to orbit, use the wheel to zoom, or use the viewport buttons and numeric controls for exact view/landmark edits."
        )
        title.setWordWrap(True)
        title_card.body_layout.addWidget(title)
        root.addWidget(title_card)

        content = QHBoxLayout()
        content.setSpacing(12)

        hand_card = SettingsCard(surface="panel", parent=self)
        self.hand_view = HandRigScene()
        self.hand_view.setMinimumSize(520, 420)
        self.hand_view.landmark_selected.connect(self._on_landmark_handle_selected)
        self.hand_view.landmark_dragged.connect(self._on_landmark_dragged)
        self.hand_view.asset_failed.connect(self._on_asset_failed)
        hand_card.body_layout.addWidget(self.hand_view, 1)
        content.addWidget(hand_card, 3)

        controls_card = SettingsCard(surface="panel", parent=self)
        controls = controls_card.body_layout
        controls.setSpacing(10)

        view_controls = QHBoxLayout()
        rotate_left = QPushButton("Rotate Left")
        set_button_role(rotate_left, "ghost")
        rotate_left.clicked.connect(lambda: self.hand_view.orbit_by(delta_yaw=-12.0))
        view_controls.addWidget(rotate_left)
        rotate_right = QPushButton("Rotate Right")
        set_button_role(rotate_right, "ghost")
        rotate_right.clicked.connect(lambda: self.hand_view.orbit_by(delta_yaw=12.0))
        view_controls.addWidget(rotate_right)
        tilt_up = QPushButton("Tilt Up")
        set_button_role(tilt_up, "ghost")
        tilt_up.clicked.connect(lambda: self.hand_view.orbit_by(delta_pitch=-8.0))
        view_controls.addWidget(tilt_up)
        tilt_down = QPushButton("Tilt Down")
        set_button_role(tilt_down, "ghost")
        tilt_down.clicked.connect(lambda: self.hand_view.orbit_by(delta_pitch=8.0))
        view_controls.addWidget(tilt_down)
        zoom_in = QPushButton("Zoom In")
        set_button_role(zoom_in, "ghost")
        zoom_in.clicked.connect(lambda: self.hand_view.zoom_by(1.0))
        view_controls.addWidget(zoom_in)
        zoom_out = QPushButton("Zoom Out")
        set_button_role(zoom_out, "ghost")
        zoom_out.clicked.connect(lambda: self.hand_view.zoom_by(-1.0))
        view_controls.addWidget(zoom_out)
        controls.addLayout(view_controls)

        reset_view_button = QPushButton("Reset View")
        set_button_role(reset_view_button, "secondary")
        set_button_icon(reset_view_button, "reset")
        reset_view_button.clicked.connect(self.hand_view.reset_view)
        controls.addWidget(reset_view_button)

        self.asset_status_label = QLabel()
        self.asset_status_label.setWordWrap(True)
        self.asset_status_label.hide()
        controls.addWidget(self.asset_status_label)

        self.landmark_combo = QComboBox()
        for index, label in enumerate(LANDMARK_NAMES):
            self.landmark_combo.addItem(f"{index:02d} - {label}", index)
        self.landmark_combo.currentIndexChanged.connect(self._on_selected_landmark_changed)
        controls.addWidget(QLabel("Selected Landmark"))
        controls.addWidget(self.landmark_combo)

        form = QFormLayout()
        form.setSpacing(8)
        self._spinboxes = {}
        for axis in ("x", "y", "z"):
            spinbox = QDoubleSpinBox()
            spinbox.setRange(-2.5, 2.5)
            spinbox.setDecimals(3)
            spinbox.setSingleStep(0.01)
            spinbox.valueChanged.connect(lambda value, axis_name=axis: self._on_axis_changed(axis_name, value))
            form.addRow(axis.upper(), spinbox)
            self._spinboxes[axis] = spinbox
        controls.addLayout(form)

        nudge_controls = QVBoxLayout()
        nudge_controls.addWidget(QLabel("Nudge Selected Landmark"))
        for axis in ("x", "y", "z"):
            row = QHBoxLayout()
            minus_button = QPushButton(f"{axis.upper()} -")
            minus_button.clicked.connect(lambda _checked=False, axis_name=axis: self._nudge_axis(axis_name, -0.05))
            row.addWidget(minus_button)
            plus_button = QPushButton(f"{axis.upper()} +")
            plus_button.clicked.connect(lambda _checked=False, axis_name=axis: self._nudge_axis(axis_name, 0.05))
            row.addWidget(plus_button)
            nudge_controls.addLayout(row)
        controls.addLayout(nudge_controls)

        self.preview_status_label = QLabel()
        self.preview_status_label.setWordWrap(True)
        controls.addWidget(self.preview_status_label)

        self.conflict_status_label = QLabel()
        self.conflict_status_label.setWordWrap(True)
        controls.addWidget(self.conflict_status_label)

        self.restore_button = QPushButton("Restore Default Pose")
        set_button_role(self.restore_button, "secondary")
        set_button_icon(self.restore_button, "reset")
        self.restore_button.clicked.connect(self._restore_default_pose)
        controls.addWidget(self.restore_button)
        controls.addStretch()

        content.addWidget(controls_card, 2)
        root.addLayout(content, 1)
        apply_settings_theme(self)

    def _set_can_save(self, value: bool):
        value = bool(value)
        if self._can_save == value:
            return
        self._can_save = value
        self.can_save_changed.emit(value)

    def _on_asset_failed(self, message: str):
        self.asset_status_label.setText(message)
        self.asset_status_label.show()
        set_label_tone(self.asset_status_label, "error")
        self._set_can_save(False)

    def _apply_landmarks(
        self,
        landmarks: np.ndarray,
        edited_index: int | None = None,
        previous_landmarks: np.ndarray | None = None,
    ):
        requested = np.asarray(landmarks, dtype=np.float32)
        self.hand_view.set_landmarks(
            requested,
            edited_index=edited_index,
            previous_landmarks=previous_landmarks,
        )
        self._landmarks = self.hand_view.current_landmarks
        self.hand_view.set_selected_landmark(int(self.landmark_combo.currentData()))
        self._refresh_spinboxes()
        self._refresh_status()

    def _refresh_spinboxes(self):
        selected_index = int(self.landmark_combo.currentData())
        point = self._landmarks[selected_index]
        self._suppress_updates = True
        try:
            self._spinboxes["x"].setValue(float(point[0]))
            self._spinboxes["y"].setValue(float(point[1]))
            self._spinboxes["z"].setValue(float(point[2]))
        finally:
            self._suppress_updates = False

    def _refresh_status(self):
        candidate = self.build_result_template()
        delta = compare_pose_templates(self.default_template, candidate, self.matcher_config)
        self.preview_status_label.setText(
            f"Pose valid. Distance from default: {delta.score:.3f} "
            f"(landmarks {delta.landmark_score:.3f}, joints {delta.joint_angle_score:.3f})"
        )
        set_label_tone(self.preview_status_label, "muted")

        conflict_text = "No conflicts with other active gestures."
        can_save = self.hand_view.asset_error is None
        if callable(self.validate_callback):
            conflict = self.validate_callback(candidate, self.matcher_config)
            if conflict is not None:
                other_def, result = conflict
                other_name = getattr(other_def, "display_name", None) or getattr(other_def, "name", "Another gesture")
                conflict_text = (
                    f"Too close to '{other_name}' "
                    f"(score {result.score:.3f} <= {self.matcher_config.conflict_threshold:.3f})."
                )
                can_save = False
        self.conflict_status_label.setText(conflict_text)
        set_label_tone(self.conflict_status_label, "error" if not can_save else "success")
        self._set_can_save(can_save)

    def _apply_single_landmark_edit(self, index: int, target: np.ndarray):
        previous = self._landmarks.copy()
        updated = previous.copy()
        target = np.asarray(target, dtype=np.float32)
        updated[index] = target
        self._apply_landmarks(updated, edited_index=index, previous_landmarks=previous)

    def _on_landmark_handle_selected(self, index: int):
        self.landmark_combo.setCurrentIndex(int(index))

    def _on_landmark_dragged(self, index: int, x: float, y: float, z: float):
        self.landmark_combo.setCurrentIndex(int(index))
        self._apply_single_landmark_edit(index, np.asarray((x, y, z), dtype=np.float32))

    def _on_selected_landmark_changed(self):
        self.hand_view.set_selected_landmark(int(self.landmark_combo.currentData()))
        self._refresh_spinboxes()

    def _on_axis_changed(self, axis_name: str, value: float):
        if self._suppress_updates:
            return
        selected_index = int(self.landmark_combo.currentData())
        axis_index = {"x": 0, "y": 1, "z": 2}[axis_name]
        target = self._landmarks[selected_index].copy()
        target[axis_index] = float(value)
        self._apply_single_landmark_edit(selected_index, target)

    def _nudge_axis(self, axis_name: str, delta: float):
        selected_index = int(self.landmark_combo.currentData())
        axis_index = {"x": 0, "y": 1, "z": 2}[axis_name]
        target = self._landmarks[selected_index].copy()
        target[axis_index] = float(target[axis_index] + delta)
        self._apply_single_landmark_edit(selected_index, target)

    def _restore_default_pose(self):
        self._apply_landmarks(self.default_template.as_array())


class GesturePoseEditorDialog(QDialog):
    def __init__(
        self,
        gesture_definition,
        initial_template: HandPoseTemplate,
        validate_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.result_template: HandPoseTemplate | None = None
        self.editor_widget = GesturePoseEditorWidget(
            gesture_definition,
            initial_template=initial_template,
            validate_callback=validate_callback,
            parent=self,
        )

        self.setWindowTitle(f"Edit Gesture: {gesture_definition.display_name}")
        configure_bounded_dialog_window(
            self,
            default_size=QSize(1100, 740),
            min_size=QSize(860, 620),
            parent=parent,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.editor_widget)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(10, 0, 10, 10)
        button_row.addStretch()
        self.save_button = QPushButton("Save")
        set_button_role(self.save_button, "primary")
        set_button_icon(self.save_button, "save")
        self.save_button.setEnabled(self.editor_widget.can_save)
        self.save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_button)
        cancel_button = QPushButton("Cancel")
        set_button_role(cancel_button, "secondary")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        root.addLayout(button_row)

        self.editor_widget.can_save_changed.connect(self.save_button.setEnabled)
        apply_settings_theme(self)

    @property
    def hand_view(self):
        return self.editor_widget.hand_view

    @property
    def _landmarks(self):
        return self.editor_widget._landmarks

    def _apply_landmarks(self, *args, **kwargs):
        return self.editor_widget._apply_landmarks(*args, **kwargs)

    def _apply_single_landmark_edit(self, *args, **kwargs):
        return self.editor_widget._apply_single_landmark_edit(*args, **kwargs)

    def _on_save_clicked(self):
        self.result_template = self.editor_widget.build_result_template()
        self.accept()
