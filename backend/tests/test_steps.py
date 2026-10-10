import pytest

from app.orchestration.steps import InvalidTransition, StepAction, StepStatus, next_status


def test_a_running_step_ends_accepted_or_rejected():
    assert next_status(StepStatus.RUNNING, StepAction.FINISH) is StepStatus.ACCEPTED
    assert next_status(StepStatus.RUNNING, StepAction.FAIL) is StepStatus.REJECTED


def test_nothing_else_is_allowed():
    for status in StepStatus:
        for action in StepAction:
            if (status, action) in {(StepStatus.RUNNING, StepAction.FINISH), (StepStatus.RUNNING, StepAction.FAIL)}:
                continue
            with pytest.raises(InvalidTransition):
                next_status(status, action)
