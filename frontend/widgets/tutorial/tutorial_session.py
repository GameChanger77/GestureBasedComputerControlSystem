from __future__ import annotations

from frontend.widgets.tutorial.tutorial_steps import TutorialStepDefinition


class TutorialSessionController:
    def __init__(self, steps: list[TutorialStepDefinition], ui_mode: str):
        self._steps = list(steps)
        self.ui_mode = str(ui_mode)
        self._current_index = 0
        self._completed_step_ids: set[str] = set()

    @property
    def total_steps(self) -> int:
        return len(self._steps)

    @property
    def current_step(self) -> TutorialStepDefinition:
        return self._steps[self._current_index]

    @property
    def current_index(self) -> int:
        return self._current_index

    def reset(self):
        self._current_index = 0
        self._completed_step_ids.clear()

    def can_go_back(self) -> bool:
        return self._current_index > 0

    def is_informational_step(self, step: TutorialStepDefinition | None = None) -> bool:
        candidate = step or self.current_step
        return bool(candidate.prod_only and self.ui_mode == "dev")

    def can_continue(self) -> bool:
        if self.is_informational_step():
            return True
        return self.current_step.step_id in self._completed_step_ids

    def mark_current_complete(self):
        self._completed_step_ids.add(self.current_step.step_id)

    def go_next(self) -> bool:
        if not self.can_continue():
            return False
        if self._current_index >= len(self._steps) - 1:
            return False
        self._current_index += 1
        return True

    def go_back(self) -> bool:
        if not self.can_go_back():
            return False
        self._current_index -= 1
        return True
