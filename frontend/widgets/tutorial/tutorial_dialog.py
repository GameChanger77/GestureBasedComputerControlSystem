from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QSize, QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from frontend.widgets.editors.dialog_windowing import (
    apply_bounded_dialog_geometry,
    configure_bounded_dialog_window,
    ensure_bounded_dialog_screen_tracking,
)
from frontend.widgets.settings.settings_theme import (
    SettingsBadge,
    SettingsCard,
    apply_app_theme,
    polish_widget,
    set_button_icon,
    set_button_role,
    set_label_role,
    set_label_tone,
)
from frontend.widgets.tutorial.tutorial_animation_widget import TutorialAnimationWidget
from frontend.widgets.tutorial.tutorial_confetti_overlay import TutorialConfettiOverlay
from frontend.widgets.tutorial.tutorial_session import TutorialSessionController
from frontend.widgets.tutorial.tutorial_steps import build_tutorial_steps, tutorial_asset_path


class TutorialDialog(QDialog):
    AUTO_ADVANCE_SECONDS = 3.0

    def __init__(
        self,
        parent,
        *,
        main_window,
        action,
        strategizer,
        ui_mode: str,
        production_keyboard_window=None,
    ):
        super().__init__(parent)
        self.main_window = main_window
        self.action = action
        self.strategizer = strategizer
        self.ui_mode = str(ui_mode)
        self.production_keyboard_window = production_keyboard_window
        self._controller = TutorialSessionController(build_tutorial_steps(), self.ui_mode)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._poll_runtime_state)
        self._auto_advance_timer = QTimer(self)
        self._auto_advance_timer.setInterval(100)
        self._auto_advance_timer.timeout.connect(self._on_auto_advance_tick)
        self._last_action_sequence = 0
        self._tracking_start_attempted = False
        self._tracking_start_error = ""
        self._step_runtime_state = {}
        self._target_frame = None
        self._left_click_target = None
        self._right_click_target = None
        self._scroll_challenge = None
        self._typing_input = None
        self._drag_rect_origin = None
        self._locked_rect_snapshot = None
        self._completion_deadline = 0.0
        self._completion_countdown_active = False
        self._completion_message = ""

        self.setWindowTitle("Default Gesture Tutorial")
        self.setModal(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        configure_bounded_dialog_window(
            self,
            default_size=QSize(1180, 860),
            min_size=QSize(920, 720),
            parent=parent,
        )
        apply_app_theme(self)
        self._build_ui()
        self._configure_current_step(reset_events=True)
        QTimer.singleShot(0, self._begin_session)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        header_card = SettingsCard(surface="panel")
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(12)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(6)
        eyebrow = QLabel("Guided Tutorial")
        set_label_role(eyebrow, "hero-eyebrow")
        copy.addWidget(eyebrow)

        self.title_label = QLabel("")
        set_label_role(self.title_label, "hero-title")
        copy.addWidget(self.title_label)

        self.description_label = QLabel("")
        self.description_label.setWordWrap(True)
        set_label_role(self.description_label, "hero-subtitle")
        copy.addWidget(self.description_label)
        header_row.addLayout(copy, 1)

        badge_col = QVBoxLayout()
        badge_col.setContentsMargins(0, 0, 0, 0)
        badge_col.setSpacing(8)
        self.progress_badge = SettingsBadge("", "accent")
        badge_col.addWidget(self.progress_badge, 0, Qt.AlignRight)
        badge_col.addStretch()
        header_row.addLayout(badge_col, 0)
        header_card.body_layout.addLayout(header_row)

        self.challenge_status_label = QLabel("")
        self.challenge_status_label.setWordWrap(True)
        set_label_role(self.challenge_status_label, "status-detail")
        header_card.body_layout.addWidget(self.challenge_status_label)
        root.addWidget(header_card)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(16)

        animation_card = SettingsCard(surface="card")
        animation_title = QLabel("Looped demo")
        set_label_role(animation_title, "section-title")
        animation_card.body_layout.addWidget(animation_title)
        self.animation_widget = TutorialAnimationWidget()
        animation_card.body_layout.addWidget(self.animation_widget, 1)
        content_row.addWidget(animation_card, 1)

        self.challenge_card = SettingsCard(surface="card")
        challenge_title = QLabel("Challenge")
        set_label_role(challenge_title, "section-title")
        self.challenge_card.body_layout.addWidget(challenge_title)

        self.challenge_scroll = QScrollArea()
        self.challenge_scroll.setWidgetResizable(True)
        self.challenge_scroll.setFrameShape(QFrame.NoFrame)
        self.challenge_body = QWidget()
        self.challenge_layout = QVBoxLayout(self.challenge_body)
        self.challenge_layout.setContentsMargins(0, 0, 0, 0)
        self.challenge_layout.setSpacing(12)
        self.challenge_scroll.setWidget(self.challenge_body)
        self.challenge_card.body_layout.addWidget(self.challenge_scroll, 1)
        content_row.addWidget(self.challenge_card, 1)

        root.addLayout(content_row, 1)

        self.confetti_overlay = TutorialConfettiOverlay(self)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(12)

        self.footer_status_label = QLabel("")
        self.footer_status_label.setWordWrap(True)
        set_label_role(self.footer_status_label, "status-detail")
        footer.addWidget(self.footer_status_label, 1)

         self.settings_button = QPushButton("Settings")
        set_button_role(self.settings_button, "secondary")
        set_button_icon(self.settings_button, "settings")
        self.settings_button.clicked.connect(self._open_settings)
        footer.addWidget(self.settings_button, 0)

        self.back_button = QPushButton("Back")
        set_button_role(self.back_button, "secondary")
        set_button_icon(self.back_button, "back")
        self.back_button.clicked.connect(self._go_back)
        footer.addWidget(self.back_button, 0)

        self.continue_button = QPushButton("Continue")
        set_button_role(self.continue_button, "primary")
        self.continue_button.clicked.connect(self._go_next)
        footer.addWidget(self.continue_button, 0)

        root.addLayout(footer)

    def _begin_session(self):
        self._poll_timer.start()
        self._ensure_tracking_ready()

    def _ensure_tracking_ready(self):
        if self._tracking_start_attempted:
            return
        self._tracking_start_attempted = True
        if self.main_window is None or not hasattr(self.main_window, "ensure_tracking_running"):
            self._tracking_start_error = "Tracking is unavailable for the tutorial."
            self._update_footer_status()
            return
        if not self.main_window.ensure_tracking_running():
            self._tracking_start_error = "Tracking failed to start. Resolve the runtime issue and reopen the tutorial."
        self._update_footer_status()

    def _tracking_ready(self) -> bool:
        tracker = getattr(self.main_window, "hand_tracker", None)
        return bool(tracker and tracker.isRunning())

    def _configure_current_step(self, *, reset_events: bool):
        self._stop_completion_feedback(reset_confetti=True)
        step = self._controller.current_step
        self.title_label.setText(step.title)
        description = step.description
        if self._controller.is_informational_step(step):
            description = (
                f"{step.description} This step is informational in dev mode because "
                "the draggable production keyboard surface only exists in prod."
            )
        self.description_label.setText(description)
        self.progress_badge.setText(f"Step {self._controller.current_index + 1} of {self._controller.total_steps}")
        self.animation_widget.set_asset(tutorial_asset_path(step.asset_name))
        self._step_runtime_state = {
            "scroll_up": False,
            "scroll_down": False,
        }
        self._target_frame = None
        self._left_click_target = None
        self._right_click_target = None
        self._scroll_challenge = None
        self._typing_input = None
        self._drag_rect_origin = self._current_prod_window_rect()
        self._locked_rect_snapshot = None
        self._clear_challenge_layout()
        self._build_current_challenge()
        self._apply_scope_for_step()
        if reset_events and self.action is not None:
            self._flush_action_events()
        if self._controller.is_informational_step():
            self._controller.mark_current_complete()
        self._update_navigation()
        self._update_footer_status()

    def _clear_challenge_layout(self):
        while self.challenge_layout.count():
            item = self.challenge_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_current_challenge(self):
        step = self._controller.current_step
        helper = QLabel(self._challenge_copy_for_step(step))
        helper.setWordWrap(True)
        set_label_tone(helper, "muted")
        self.challenge_layout.addWidget(helper)

        if self._controller.is_informational_step():
            info = SettingsCard(surface="subtle-card")
            label = QLabel("This step is prod-only. Review the looped demo, then continue when you are ready.")
            label.setWordWrap(True)
            set_label_role(label, "status-detail")
            info.body_layout.addWidget(label)
            self.challenge_layout.addWidget(info)
            self.challenge_layout.addStretch(1)
            return

        kind = step.challenge_kind
        if kind == "move_mouse":
            self._target_frame = self._build_mouse_target("Move the cursor into this target")
            self.challenge_layout.addWidget(self._target_frame)
        elif kind == "left_click":
            self._left_click_target = self._build_click_target("Use the left-click gesture here")
            self.challenge_layout.addWidget(self._left_click_target)
        elif kind == "right_click":
            self._right_click_target = self._build_click_target("Use the right-click gesture here", role="danger")
            self.challenge_layout.addWidget(self._right_click_target)
        elif kind == "scroll":
            self._scroll_challenge = self._build_scroll_challenge()
            self.challenge_layout.addWidget(self._scroll_challenge)
        elif kind == "type_keyboard":
            target = QLabel(f"Target phrase: {step.required_phrase}")
            set_label_role(target, "section-title")
            self.challenge_layout.addWidget(target)
            self._typing_input = QLineEdit()
            self._typing_input.setPlaceholderText("Use the gesture keyboard to type here")
            self._typing_input.textChanged.connect(self._on_typing_text_changed)
            self.challenge_layout.addWidget(self._typing_input)
        else:
            card = SettingsCard(surface="subtle-card")
            label = QLabel(self._challenge_runtime_hint(step))
            label.setWordWrap(True)
            set_label_role(label, "status-detail")
            card.body_layout.addWidget(label)
            self.challenge_layout.addWidget(card)

        self.challenge_layout.addStretch(1)

    def _challenge_copy_for_step(self, step):
        if step.challenge_kind == "scroll":
            return "Complete both an upward and downward scroll while the cursor stays inside the tutorial window."
        if step.challenge_kind == "type_keyboard":
            return "Typed output is captured into this field while the step is active."
        if step.challenge_kind.startswith("mode_"):
            return "Continue unlocks as soon as the real runtime mode changes."
        if step.challenge_kind in {"drag_keyboard", "lock_keyboard", "unlock_keyboard"}:
            return "The tutorial watches the real production keyboard overlay state."
        return "Complete the live challenge below to unlock Continue."

    def _challenge_runtime_hint(self, step):
        if step.challenge_kind == "mode_keyboard":
            return "Perform the built-in switch-to-keyboard gesture until the runtime mode changes to KEYBOARD."
        if step.challenge_kind == "mode_mouse":
            return "Perform the built-in switch-to-mouse gesture until the runtime mode changes back to MOUSE."
        if step.challenge_kind == "drag_keyboard":
            return "Move the production keyboard overlay to a visibly different position while it is unlocked."
        if step.challenge_kind == "lock_keyboard":
            return "Close your hand so the keyboard overlay locks in place."
        if step.challenge_kind == "unlock_keyboard":
            return "Reopen your hand so the keyboard unlocks and begins following again."
        return ""

    def _build_mouse_target(self, text: str):
        card = SettingsCard(surface="subtle-card")
        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        target = QFrame()
        target.setMinimumSize(140, 140)
        target.setMaximumSize(140, 140)
        target.setStyleSheet("background-color: #143326; border: 2px dashed #7cf2aa; border-radius: 18px;")
        target_layout = QVBoxLayout(target)
        target_layout.setContentsMargins(12, 12, 12, 12)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        set_label_role(label, "status-detail")
        target_layout.addStretch(1)
        target_layout.addWidget(label)
        target_layout.addStretch(1)
        outer.addWidget(target, 0)
        card.body_layout.addLayout(outer)
        return card

    def _build_click_target(self, text: str, *, role: str = "primary"):
        button = QPushButton(text)
        set_button_role(button, role)
        button.setMinimumHeight(58)
        button.setEnabled(False)
        return button

    def _build_scroll_challenge(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(220)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for index in range(12):
            label = QLabel(f"Scroll challenge content row {index + 1}")
            set_label_role(label, "status-detail")
            label.setMinimumHeight(26)
            layout.addWidget(label)
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _go_back(self):
        self._stop_completion_feedback(reset_confetti=True)
        if self._controller.go_back():
            self._configure_current_step(reset_events=True)

    def _go_next(self):
        self._stop_completion_feedback(reset_confetti=True)
        if self._controller.current_index == self._controller.total_steps - 1 and self._controller.can_continue():
            self.accept()
            return
        if self._controller.go_next():
            self._configure_current_step(reset_events=True)

    def _mark_current_complete(self, message: str):
        if self._controller.can_continue():
            return
        self._controller.mark_current_complete()
        self._completion_message = message
        self.challenge_status_label.setText(message)
        self.footer_status_label.setText(message)
        self.confetti_overlay.burst()
        self._completion_deadline = time.monotonic() + self.AUTO_ADVANCE_SECONDS
        self._completion_countdown_active = True
        self._auto_advance_timer.start()
        self._update_navigation()

    def _stop_completion_feedback(self, *, reset_confetti: bool):
        self._auto_advance_timer.stop()
        self._completion_deadline = 0.0
        self._completion_countdown_active = False
        self._completion_message = ""
        if reset_confetti:
            self.confetti_overlay.stop()

    def _remaining_countdown_seconds(self) -> int:
        if not self._completion_countdown_active:
            return 0
        return max(1, int(math.ceil(max(0.0, self._completion_deadline - time.monotonic()))))

    def _on_auto_advance_tick(self):
        if not self._completion_countdown_active:
            self._auto_advance_timer.stop()
            return
        if time.monotonic() >= self._completion_deadline:
            self._stop_completion_feedback(reset_confetti=True)
            self._go_next()
            return
        self._update_navigation()

    def _update_navigation(self):
        self.back_button.setEnabled(self._controller.can_go_back())
        can_continue = self._controller.can_continue()
        self.continue_button.setEnabled(can_continue)
        base_label = "Finish" if self._controller.current_index == self._controller.total_steps - 1 else "Continue"
        if can_continue and self._completion_countdown_active:
            self.continue_button.setText(f"{base_label} ({self._remaining_countdown_seconds()})")
        else:
            self.continue_button.setText(base_label)
        self.continue_button.setProperty("tutorialContinueLocked", not can_continue)
        set_button_icon(self.continue_button, "unlock" if can_continue else "lock")
        if can_continue:
            self.continue_button.setCursor(Qt.PointingHandCursor)
        else:
            self.continue_button.setCursor(Qt.ForbiddenCursor)
        polish_widget(self.continue_button)

    def _update_footer_status(self):
        if self._tracking_start_error:
            self.challenge_status_label.setText(self._tracking_start_error)
            self.footer_status_label.setText(self._tracking_start_error)
            set_label_tone(self.footer_status_label, "error")
            return

        if not self._tracking_ready() and not self._controller.is_informational_step():
            waiting = "Starting tracking for the tutorial..."
            self.challenge_status_label.setText(waiting)
            self.footer_status_label.setText(waiting)
            set_label_tone(self.footer_status_label, "warning")
            return

        if self._controller.can_continue():
            text = self.challenge_status_label.text() or "Challenge complete."
            self.footer_status_label.setText(text)
            set_label_tone(self.footer_status_label, "success")
            return

        text = "Complete the current challenge to unlock Continue."
        self.challenge_status_label.setText(text)
        self.footer_status_label.setText(text)
        set_label_tone(self.footer_status_label, "muted")

    def _poll_runtime_state(self):
        if self.action is not None:
            for event in self.action.get_action_events(after_sequence=self._last_action_sequence):
                self._last_action_sequence = max(self._last_action_sequence, int(event["sequence"]))
                self._process_action_event(event)
        self._process_runtime_completion()
        self._update_navigation()
        self._update_footer_status()

    def _process_action_event(self, event):
        if self._tracking_start_error:
            return
        if not self._tracking_ready() and not self._controller.is_informational_step():
            return

        step = self._controller.current_step
        event_type = event.get("type")
        if step.challenge_kind == "move_mouse" and event_type == "cursor_move":
            if self._global_event_hits_widget(event, self._target_frame):
                self._mark_current_complete("Mouse target reached.")
        elif step.challenge_kind == "left_click" and event_type == "left_click":
            if self._global_event_hits_widget(event, self._left_click_target):
                self._mark_current_complete("Left click detected inside the tutorial target.")
        elif step.challenge_kind == "right_click" and event_type == "right_click":
            if self._global_event_hits_widget(event, self._right_click_target):
                self._mark_current_complete("Right click detected inside the tutorial target.")
        elif step.challenge_kind == "scroll" and event_type == "scroll":
            if self._global_event_hits_widget(event, self._scroll_challenge):
                delta_y = int(event.get("delta_y", 0))
                if delta_y > 0:
                    self._step_runtime_state["scroll_up"] = True
                if delta_y < 0:
                    self._step_runtime_state["scroll_down"] = True
                if self._step_runtime_state["scroll_up"] and self._step_runtime_state["scroll_down"]:
                    self._mark_current_complete("Detected both upward and downward scroll gestures.")
        elif step.challenge_kind == "type_keyboard" and event_type == "type_text":
            text = str(event.get("text", ""))
            if self._typing_input is not None:
                merged = f"{self._typing_input.text()}{text}"
                self._typing_input.setText(merged)
                self._typing_input.setCursorPosition(len(merged))

    def _process_runtime_completion(self):
        if self._tracking_start_error:
            return
        if not self._tracking_ready() and not self._controller.is_informational_step():
            return

        step = self._controller.current_step
        mode_name = self._current_mode_name()
        if step.challenge_kind == "mode_keyboard" and mode_name == "KEYBOARD":
            self._mark_current_complete("Keyboard mode activated.")
        elif step.challenge_kind == "mode_mouse" and mode_name == "MOUSE":
            self._mark_current_complete("Mouse mode activated.")
        elif step.challenge_kind == "drag_keyboard":
            overlay = self._current_overlay_data()
            rect = self._current_prod_window_rect()
            if rect and self._drag_rect_origin is None:
                self._drag_rect_origin = rect
            if overlay and not overlay.get("prod_window_locked", True):
                origin = self._drag_rect_origin
                if rect and origin and self._rect_distance(origin, rect) >= 36:
                    self._mark_current_complete("Keyboard overlay moved successfully.")
        elif step.challenge_kind == "lock_keyboard":
            overlay = self._current_overlay_data()
            if overlay and overlay.get("prod_window_locked", False):
                self._locked_rect_snapshot = self._current_prod_window_rect()
                self._mark_current_complete("Keyboard overlay locked in place.")
        elif step.challenge_kind == "unlock_keyboard":
            overlay = self._current_overlay_data()
            rect = self._current_prod_window_rect()
            if rect and self._locked_rect_snapshot is None and overlay and overlay.get("prod_window_locked", False):
                self._locked_rect_snapshot = rect
            if overlay and not overlay.get("prod_window_locked", True):
                reference = self._locked_rect_snapshot or self._drag_rect_origin
                if rect and reference and self._rect_distance(reference, rect) >= 12:
                    self._mark_current_complete("Keyboard overlay unlocked and resumed following.")

    def _current_mode_name(self) -> str:
        if self.strategizer and hasattr(self.strategizer, "get_mode_name"):
            return str(self.strategizer.get_mode_name()).upper()
        return "UNKNOWN"

    def _current_overlay_data(self):
        if self.strategizer and hasattr(self.strategizer, "get_keyboard_overlay_data"):
            return self.strategizer.get_keyboard_overlay_data()
        return None

    def _current_prod_window_rect(self):
        overlay = self._current_overlay_data() or {}
        rect = overlay.get("prod_window_rect_px") or {}
        if not rect:
            return None
        return (
            int(rect.get("x", 0)),
            int(rect.get("y", 0)),
            int(rect.get("w", 0)),
            int(rect.get("h", 0)),
        )

    def _rect_distance(self, first, second) -> int:
        return abs(first[0] - second[0]) + abs(first[1] - second[1])

    def _on_typing_text_changed(self, value: str):
        phrase = self._controller.current_step.required_phrase.lower()
        if phrase and value.strip().lower() == phrase:
            self._mark_current_complete(f"Typed the target phrase: {phrase}")

    def _global_event_hits_widget(self, event, widget) -> bool:
        if widget is None or not widget.isVisible():
            return False
        global_x = int(event.get("global_x", -99999))
        global_y = int(event.get("global_y", -99999))
        local_point = widget.mapFromGlobal(QPoint(global_x, global_y))
        return widget.rect().contains(local_point)

    def _apply_scope_for_step(self):
        if self.action is None:
            return
        kind = self._controller.current_step.challenge_kind
        if kind in {"move_mouse", "left_click", "right_click", "scroll"}:
            top_left = self.mapToGlobal(QPoint(0, 0))
            self.action.set_tutorial_scope(
                bounds=(
                    top_left.x() - int(getattr(self.action, "screen_origin_x", 0)),
                    top_left.y() - int(getattr(self.action, "screen_origin_y", 0)),
                    self.width(),
                    self.height(),
                ),
                capture_text=False,
            )
        elif kind == "type_keyboard":
            self.action.set_tutorial_scope(bounds=None, capture_text=True)
            if self._typing_input is not None:
                self._typing_input.setFocus(Qt.OtherFocusReason)
        else:
            self.action.clear_tutorial_scope()

    def _flush_action_events(self):
        if self.action is None:
            return
        events = self.action.get_action_events(after_sequence=self._last_action_sequence)
        if events:
            self._last_action_sequence = max(int(event["sequence"]) for event in events)

    def _layout_confetti_overlay(self):
        self.confetti_overlay.setGeometry(self.rect())
        self.confetti_overlay.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        ensure_bounded_dialog_screen_tracking(self)
        apply_bounded_dialog_geometry(self, center=False)
        self._apply_scope_for_step()
        self._layout_confetti_overlay()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_scope_for_step()
        self._layout_confetti_overlay()
        apply_bounded_dialog_geometry(self, center=False)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._apply_scope_for_step()
        self._layout_confetti_overlay()

    def closeEvent(self, event):
        self._poll_timer.stop()
        self._stop_completion_feedback(reset_confetti=True)
        if self.action is not None:
            self.action.clear_tutorial_scope()
        super().closeEvent(event)
