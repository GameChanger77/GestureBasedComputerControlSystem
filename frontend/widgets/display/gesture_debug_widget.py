from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from frontend.widgets.settings.settings_theme import (
    SettingsBadge,
    SettingsCard,
    apply_app_theme,
    polish_widget,
    set_label_role,
)


class GestureDebugWidget(QWidget):
    """Dev-only widget for inspecting live hand state and gesture arbitration."""

    def __init__(self):
        super().__init__()
        self._hand_presence_badges: dict[str, SettingsBadge] = {}
        self._hand_extended_labels: dict[str, QLabel] = {}
        self._hand_curled_labels: dict[str, QLabel] = {}
        self._hand_pinch_labels: dict[str, QLabel] = {}
        self._mode_switch_value = None
        self._mode_candidates_value = None
        self._action_value = None
        self._init_ui()
        self.reset()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(320)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        root_layout.addWidget(scroll)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        scroll.setWidget(content)

        shell = SettingsCard(surface="card")
        shell.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        content_layout.addWidget(shell)
        content_layout.addStretch(1)

        title = QLabel("Gesture Debug")
        set_label_role(title, "section-title")
        shell.body_layout.addWidget(title)

        subtitle = QLabel("Live finger state, gesture arbitration, and current winning action for this frame.")
        subtitle.setWordWrap(True)
        set_label_role(subtitle, "status-detail")
        shell.body_layout.addWidget(subtitle)

        hands_card = SettingsCard(surface="subtle-card")
        hands_card.setMinimumHeight(170)
        hands_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        hands_title = QLabel("Hands")
        set_label_role(hands_title, "card-title")
        hands_card.body_layout.addWidget(hands_title)

        hands_grid = QGridLayout()
        hands_grid.setContentsMargins(0, 6, 0, 0)
        hands_grid.setHorizontalSpacing(14)
        hands_grid.setVerticalSpacing(12)
        for column, side in enumerate(("Left", "Right")):
            hand_card = SettingsCard(surface="subtle-card")
            hand_card.setMinimumHeight(110)
            hand_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            hand_title_row = QHBoxLayout()
            hand_title_row.setContentsMargins(0, 0, 0, 0)
            hand_title_row.setSpacing(8)

            hand_title = QLabel(f"{side} Hand")
            set_label_role(hand_title, "metric-caption")
            hand_title_row.addWidget(hand_title, 0)

            badge = SettingsBadge("Not detected", "default")
            self._hand_presence_badges[side] = badge
            hand_title_row.addWidget(badge, 0, Qt.AlignLeft)
            hand_title_row.addStretch()
            hand_card.body_layout.addLayout(hand_title_row)

            extended_label = QLabel()
            extended_label.setWordWrap(True)
            set_label_role(extended_label, "status-detail")
            hand_card.body_layout.addWidget(extended_label)
            self._hand_extended_labels[side] = extended_label

            curled_label = QLabel()
            curled_label.setWordWrap(True)
            set_label_role(curled_label, "status-detail")
            hand_card.body_layout.addWidget(curled_label)
            self._hand_curled_labels[side] = curled_label

            pinch_label = QLabel()
            pinch_label.setWordWrap(True)
            set_label_role(pinch_label, "status-detail")
            hand_card.body_layout.addWidget(pinch_label)
            self._hand_pinch_labels[side] = pinch_label

            hands_grid.addWidget(hand_card, 0, column)
        hands_card.body_layout.addLayout(hands_grid)
        shell.body_layout.addWidget(hands_card)

        gestures_card = SettingsCard(surface="subtle-card")
        gestures_card.setMinimumHeight(175)
        gestures_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        gestures_title = QLabel("Gestures")
        set_label_role(gestures_title, "card-title")
        gestures_card.body_layout.addWidget(gestures_title)

        mode_switch_caption = QLabel("Mode Switch Candidates")
        set_label_role(mode_switch_caption, "metric-caption")
        gestures_card.body_layout.addWidget(mode_switch_caption)
        self._mode_switch_value = QLabel()
        self._mode_switch_value.setWordWrap(True)
        set_label_role(self._mode_switch_value, "status-detail")
        gestures_card.body_layout.addWidget(self._mode_switch_value)

        mode_caption = QLabel("Current Mode Candidates")
        set_label_role(mode_caption, "metric-caption")
        gestures_card.body_layout.addWidget(mode_caption)
        self._mode_candidates_value = QLabel()
        self._mode_candidates_value.setWordWrap(True)
        set_label_role(self._mode_candidates_value, "status-detail")
        gestures_card.body_layout.addWidget(self._mode_candidates_value)
        shell.body_layout.addWidget(gestures_card)

        action_card = SettingsCard(surface="subtle-card")
        action_card.setMinimumHeight(110)
        action_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        action_title = QLabel("Action")
        set_label_role(action_title, "card-title")
        action_card.body_layout.addWidget(action_title)
        self._action_value = QLabel()
        self._action_value.setWordWrap(True)
        set_label_role(self._action_value, "status-detail")
        action_card.body_layout.addWidget(self._action_value)
        shell.body_layout.addWidget(action_card)

        apply_app_theme(self)

    def update_debug(self, snapshot: dict | None):
        if not snapshot:
            self.reset()
            return

        hands_by_side = {entry.get("side", ""): entry for entry in snapshot.get("hands", [])}
        for side in ("Left", "Right"):
            self._update_hand(side, hands_by_side.get(side))

        self._mode_switch_value.setText(self._format_gesture_entries(snapshot.get("mode_switch_candidates", [])))
        self._mode_candidates_value.setText(self._format_gesture_entries(snapshot.get("mode_candidates", [])))

        winning_action = snapshot.get("winning_action")
        action_debug = snapshot.get("action_debug") or {}
        self._action_value.setText(self._format_action_block(winning_action, action_debug))
        self._action_value.setProperty("textTone", "success" if winning_action else "muted")
        polish_widget(self._action_value)
        polish_widget(self._mode_switch_value)
        polish_widget(self._mode_candidates_value)

    def _update_hand(self, side: str, hand_entry: dict | None):
        badge = self._hand_presence_badges[side]
        extended_label = self._hand_extended_labels[side]
        curled_label = self._hand_curled_labels[side]
        pinch_label = self._hand_pinch_labels[side]

        if not hand_entry or not hand_entry.get("present"):
            badge.update_badge("Not detected", "default")
            extended_label.setText("Extended: None")
            curled_label.setText("Curled: Thumb, Index, Middle, Ring, Pinky")
            pinch_label.setText("Pinches: None")
            extended_label.setProperty("textTone", "muted")
            curled_label.setProperty("textTone", "muted")
            pinch_label.setProperty("textTone", "muted")
            polish_widget(extended_label)
            polish_widget(curled_label)
            polish_widget(pinch_label)
            return

        badge.update_badge("Detected", "success")
        extended = hand_entry.get("extended_fingers", [])
        curled = hand_entry.get("curled_fingers", [])
        pinches = hand_entry.get("detected_pinches", [])
        extended_label.setText(f"Extended: {', '.join(extended) if extended else 'None'}")
        curled_label.setText(f"Curled: {', '.join(curled) if curled else 'None'}")
        pinch_label.setText(f"Pinches: {', '.join(pinches) if pinches else 'None'}")
        extended_label.setProperty("textTone", None)
        curled_label.setProperty("textTone", "muted")
        pinch_label.setProperty("textTone", "accent" if pinches else "muted")
        polish_widget(extended_label)
        polish_widget(curled_label)
        polish_widget(pinch_label)

    def _format_gesture_entries(self, entries: list[dict]) -> str:
        if not entries:
            return "No gesture candidates evaluated this frame."

        lines = []
        for entry in entries:
            name = entry.get("name", "Unknown")
            priority = entry.get("priority", 0)
            state = str(entry.get("state", "unknown")).replace("_", " ").title()
            markers = []
            if entry.get("executed"):
                markers.append("executed")
            elif entry.get("suppressed"):
                markers.append("suppressed")
            elif entry.get("active"):
                markers.append("active")
            elif entry.get("detected"):
                markers.append("detected")
            note = str(entry.get("note", "") or "").strip()
            suffix_parts = [state]
            if markers:
                suffix_parts.append(", ".join(markers))
            if note:
                suffix_parts.append(note)
            lines.append(f"{name} (p{priority}) - {' | '.join(suffix_parts)}")
        return "\n".join(lines)

    def _format_action_block(self, winning_action: dict | None, action_debug: dict) -> str:
        lines = []
        if winning_action:
            name = winning_action.get("name", "Unknown action")
            note = str(winning_action.get("note", "") or "").strip()
            lines.append(f"{name}{f' - {note}' if note else ''}")
        else:
            lines.append("No action this frame.")

        cursor = action_debug.get("cursor") or {}
        lines.append(
            "Cursor: "
            f"local ({cursor.get('local_x', 0)}, {cursor.get('local_y', 0)}) "
            f"| global ({cursor.get('global_x', 0)}, {cursor.get('global_y', 0)})"
        )

        latest_event = action_debug.get("latest_action_event") or {}
        if latest_event:
            event_type = str(latest_event.get("type", "unknown")).replace("_", " ")
            details = []
            if "delta_y" in latest_event:
                details.append(f"dy={latest_event.get('delta_y')}")
            if "delta_x" in latest_event:
                details.append(f"dx={latest_event.get('delta_x')}")
            if "key" in latest_event:
                details.append(f"key={latest_event.get('key')}")
            if "text" in latest_event:
                details.append(f"text={latest_event.get('text')}")
            latest_line = f"Latest event: {event_type}"
            if details:
                latest_line += f" ({', '.join(details)})"
            lines.append(latest_line)
        return "\n".join(lines)

    def reset(self):
        for side in ("Left", "Right"):
            self._update_hand(side, None)
        self._mode_switch_value.setText("No gesture candidates evaluated this frame.")
        self._mode_switch_value.setProperty("textTone", "muted")
        self._mode_candidates_value.setText("No gesture candidates evaluated this frame.")
        self._mode_candidates_value.setProperty("textTone", "muted")
        self._action_value.setText(self._format_action_block(None, {}))
        self._action_value.setProperty("textTone", "muted")
        polish_widget(self._mode_switch_value)
        polish_widget(self._mode_candidates_value)
        polish_widget(self._action_value)
