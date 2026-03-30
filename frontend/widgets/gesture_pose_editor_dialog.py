from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from backend.gesture_remap.pose_templates import HandPoseTemplate, PoseMatcherConfig, compare_pose_templates
from frontend.widgets.hand_rig_scene import HandRigScene


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


class GesturePoseEditorDialog(QDialog):
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
        self.result_template: HandPoseTemplate | None = None
        self._suppress_updates = False
        self._landmarks = self.current_template.as_array().copy()

        self.setWindowTitle(f"Edit Gesture: {gesture_definition.display_name}")
        self.resize(1220, 780)
        self._create_ui()
        self._apply_landmarks(self._landmarks)

    def _create_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        title = QLabel(
            f"<b>{self.gesture_definition.display_name}</b><br>"
            f"{self.gesture_definition.default_description}<br>"
            "Use the Blender hand as a stable reference model. Drag the landmark handles and skeleton overlay to author the saved pose, right-drag to orbit, use the wheel to zoom, or use the viewport buttons and numeric controls for exact view/landmark edits."
        )
        title.setWordWrap(True)
        root.addWidget(title)

        content = QHBoxLayout()
        content.setSpacing(12)

        self.hand_view = HandRigScene()
        self.hand_view.setMinimumWidth(740)
        self.hand_view.landmark_selected.connect(self._on_landmark_handle_selected)
        self.hand_view.landmark_dragged.connect(self._on_landmark_dragged)
        self.hand_view.asset_failed.connect(self._on_asset_failed)
        content.addWidget(self.hand_view, 3)

        controls = QVBoxLayout()
        controls.setSpacing(10)

        view_controls = QHBoxLayout()
        rotate_left = QPushButton("Rotate Left")
        rotate_left.clicked.connect(lambda: self.hand_view.orbit_by(delta_yaw=-12.0))
        view_controls.addWidget(rotate_left)
        rotate_right = QPushButton("Rotate Right")
        rotate_right.clicked.connect(lambda: self.hand_view.orbit_by(delta_yaw=12.0))
        view_controls.addWidget(rotate_right)
        tilt_up = QPushButton("Tilt Up")
        tilt_up.clicked.connect(lambda: self.hand_view.orbit_by(delta_pitch=-8.0))
        view_controls.addWidget(tilt_up)
        tilt_down = QPushButton("Tilt Down")
        tilt_down.clicked.connect(lambda: self.hand_view.orbit_by(delta_pitch=8.0))
        view_controls.addWidget(tilt_down)
        zoom_in = QPushButton("Zoom In")
        zoom_in.clicked.connect(lambda: self.hand_view.zoom_by(1.0))
        view_controls.addWidget(zoom_in)
        zoom_out = QPushButton("Zoom Out")
        zoom_out.clicked.connect(lambda: self.hand_view.zoom_by(-1.0))
        view_controls.addWidget(zoom_out)
        controls.addLayout(view_controls)

        reset_view_button = QPushButton("Reset View")
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
        self.restore_button.clicked.connect(self._restore_default_pose)
        controls.addWidget(self.restore_button)
        controls.addStretch()

        button_row = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_button)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        controls.addLayout(button_row)

        content.addLayout(controls, 2)
        root.addLayout(content, 1)

    def _on_asset_failed(self, message: str):
        self.asset_status_label.setText(message)
        self.asset_status_label.show()
        self.save_button.setEnabled(False)

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
        candidate = HandPoseTemplate.from_array(self.gesture_definition.display_name, self._landmarks)
        delta = compare_pose_templates(self.default_template, candidate, self.matcher_config)
        self.preview_status_label.setText(
            f"Pose valid. Distance from default: {delta.score:.3f} "
            f"(landmarks {delta.landmark_score:.3f}, joints {delta.joint_angle_score:.3f})"
        )

        conflict_text = "No conflicts with other active gestures."
        can_save = self.hand_view.asset_error is None
        if callable(self.validate_callback):
            conflict = self.validate_callback(candidate, self.matcher_config)
            if conflict is not None:
                other_def, result = conflict
                conflict_text = (
                    f"Too close to '{other_def.display_name}' "
                    f"(score {result.score:.3f} <= {self.matcher_config.conflict_threshold:.3f})."
                )
                can_save = False
        self.conflict_status_label.setText(conflict_text)
        self.save_button.setEnabled(can_save)

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

    def _on_save_clicked(self):
        self.result_template = HandPoseTemplate.from_array(
            self.gesture_definition.display_name,
            self._landmarks,
        )
        self.accept()
