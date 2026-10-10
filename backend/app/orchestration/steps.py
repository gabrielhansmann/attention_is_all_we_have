"""Step state machine for a pipeline run (docs/architecture/02, decision 0005).

planned -> running -> awaiting_review -> accepted | rejected, with Retry looping back to running.
Accepting a step is what starts the next planned one; there is no separate "run" click.
Pure Python, no I/O, so it is the single place where the rules live and is easy to test.
"""
from __future__ import annotations

from enum import Enum


class StepStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class StepAction(str, Enum):
    START = "start"        # orchestrator, when the previous step is accepted
    FINISH = "finish"      # agent done and the Critic passed its output
    ACCEPT = "accept"      # PM
    EDIT = "edit"          # PM edits the summary; the step stays in review
    RETRY = "retry"        # PM with a steering note; the same agent re-runs
    REJECT = "reject"      # PM


class InvalidTransition(ValueError):
    pass


_TRANSITIONS: dict[tuple[StepStatus, StepAction], StepStatus] = {
    (StepStatus.PLANNED, StepAction.START): StepStatus.RUNNING,
    (StepStatus.RUNNING, StepAction.FINISH): StepStatus.AWAITING_REVIEW,
    (StepStatus.AWAITING_REVIEW, StepAction.ACCEPT): StepStatus.ACCEPTED,
    (StepStatus.AWAITING_REVIEW, StepAction.EDIT): StepStatus.AWAITING_REVIEW,
    (StepStatus.AWAITING_REVIEW, StepAction.RETRY): StepStatus.RUNNING,
    (StepStatus.AWAITING_REVIEW, StepAction.REJECT): StepStatus.REJECTED,
}
PM_ACTIONS = {StepAction.ACCEPT, StepAction.EDIT, StepAction.RETRY, StepAction.REJECT}


def next_status(status: StepStatus, action: StepAction, *, note: str | None = None) -> StepStatus:
    """Return the new status or raise InvalidTransition. A retry needs a steering note."""
    if action is StepAction.RETRY and not (note and note.strip()):
        raise InvalidTransition("retry needs a steering note")
    try:
        return _TRANSITIONS[(status, action)]
    except KeyError:
        raise InvalidTransition(f"cannot {action.value} a step that is {status.value}") from None


def available_actions(status: StepStatus) -> list[StepAction]:
    """What the UI may offer on a step card in this state."""
    return [a for (s, a) in _TRANSITIONS if s is status and a in PM_ACTIONS]


def next_to_start(statuses: list[StepStatus]) -> int | None:
    """Index of the planned step to start now, or None.

    Steps run strictly one at a time, in plan order: nothing starts while a step is running or
    waiting for review, and only once every earlier step is accepted or rejected (a rejected step is a
    skipped agent the PM chose to proceed without).
    """
    if any(s in (StepStatus.RUNNING, StepStatus.AWAITING_REVIEW) for s in statuses):
        return None
    for i, s in enumerate(statuses):
        if s is StepStatus.PLANNED:
            return i
    return None
