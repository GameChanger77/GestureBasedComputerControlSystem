from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TutorialStepDefinition:
    step_id: str
    title: str
    description: str
    asset_name: str
    challenge_kind: str
    prod_only: bool = False
    required_phrase: str = ""


def _tutorial_asset_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "tutorial"


def tutorial_asset_path(asset_name: str) -> Path:
    return _tutorial_asset_dir() / asset_name


def build_tutorial_steps() -> list[TutorialStepDefinition]:
    return [
        TutorialStepDefinition(
            step_id="move_mouse",
            title="Move the mouse",
            description="Hold the default mouse-move pose and move the cursor into the highlighted target.",
            asset_name="move_mouse.json",
            challenge_kind="move_mouse",
        ),
        TutorialStepDefinition(
            step_id="left_click",
            title="Perform a left click",
            description="Use the default left-click gesture while the cursor is over the tutorial target.",
            asset_name="left_click.json",
            challenge_kind="left_click",
        ),
        TutorialStepDefinition(
            step_id="right_click",
            title="Perform a right click",
            description="Use the default right-click gesture while the cursor is inside the marked area.",
            asset_name="right_click.json",
            challenge_kind="right_click",
        ),
        TutorialStepDefinition(
            step_id="scroll",
            title="Scroll up and down",
            description="Use the scroll gesture and complete both an upward and downward scroll inside the tutorial panel.",
            asset_name="scroll.json",
            challenge_kind="scroll",
        ),
        TutorialStepDefinition(
            step_id="switch_to_keyboard",
            title="Switch to keyboard mode",
            description="Perform the built-in switch gesture until the runtime changes from mouse mode to keyboard mode.",
            asset_name="switch_to_keyboard.json",
            challenge_kind="mode_keyboard",
        ),
        TutorialStepDefinition(
            step_id="drag_keyboard",
            title="Drag the keyboard",
            description="With the keyboard overlay visible in prod, use the default drag behavior to move it somewhere new on screen.",
            asset_name="drag_keyboard.json",
            challenge_kind="drag_keyboard",
            prod_only=True,
        ),
        TutorialStepDefinition(
            step_id="lock_keyboard",
            title="Lock the keyboard in place",
            description="After dragging the keyboard, close your hand to lock the keyboard overlay in place.",
            asset_name="lock_keyboard.json",
            challenge_kind="lock_keyboard",
            prod_only=True,
        ),
        TutorialStepDefinition(
            step_id="unlock_keyboard",
            title="Unlock the keyboard",
            description="Reopen your hand so the keyboard overlay unlocks and resumes following your drag anchor.",
            asset_name="unlock_keyboard.json",
            challenge_kind="unlock_keyboard",
            prod_only=True,
        ),
        TutorialStepDefinition(
            step_id="type_on_keyboard",
            title="Type on the keyboard",
            description="Use the default keyboard typing gesture to enter the phrase shown below into the tutorial field.",
            asset_name="type_keyboard.json",
            challenge_kind="type_keyboard",
            required_phrase="hello",
        ),
        TutorialStepDefinition(
            step_id="switch_to_mouse",
            title="Switch back to mouse mode",
            description="Perform the built-in exit gesture until the runtime switches back to mouse mode.",
            asset_name="switch_to_mouse.json",
            challenge_kind="mode_mouse",
        ),
    ]

