"""Step state machine for an orchestrated run (docs/architecture/02, decision 0018).

The orchestrator creates a step when it decides to call an agent: running -> accepted (the agent answered and the
Critic passed it) or rejected (the agent failed). No person approves a step. `planned` and `awaiting_review` stay in
the enum because the database constraint still allows them (decisions 0005 and 0015); nothing enters them now.
Pure Python, no I/O.
"""
from __future__ import annotations

from enum import Enum


class StepStatus(str, Enum):
    PLANNED = "planned"                 # unused since decision 0018
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"  # unused since decision 0018
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class StepAction(str, Enum):
    FINISH = "finish"      # the agent answered and the Critic passed its output
    FAIL = "fail"          # the agent could not produce an output


class InvalidTransition(ValueError):
    pass


_TRANSITIONS: dict[tuple[StepStatus, StepAction], StepStatus] = {
    (StepStatus.RUNNING, StepAction.FINISH): StepStatus.ACCEPTED,
    (StepStatus.RUNNING, StepAction.FAIL): StepStatus.REJECTED,
}


def next_status(status: StepStatus, action: StepAction) -> StepStatus:
    """Return the new status or raise InvalidTransition."""
    try:
        return _TRANSITIONS[(status, action)]
    except KeyError:
        raise InvalidTransition(f"cannot {action.value} a step that is {status.value}") from None
