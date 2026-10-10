import pytest

from app.orchestration.steps import (InvalidTransition, StepAction, StepStatus, available_actions, next_status,
                                     next_to_start)

S, A = StepStatus, StepAction


def test_happy_path():
    s = S.PLANNED
    for action, expected in [(A.START, S.RUNNING), (A.FINISH, S.AWAITING_REVIEW), (A.ACCEPT, S.ACCEPTED)]:
        s = next_status(s, action)
        assert s is expected


def test_retry_returns_to_running_and_needs_a_note():
    assert next_status(S.AWAITING_REVIEW, A.RETRY, note="drop paywalled sources") is S.RUNNING
    with pytest.raises(InvalidTransition):
        next_status(S.AWAITING_REVIEW, A.RETRY)
    with pytest.raises(InvalidTransition):
        next_status(S.AWAITING_REVIEW, A.RETRY, note="   ")


def test_edit_keeps_the_step_in_review_and_reject_ends_it():
    assert next_status(S.AWAITING_REVIEW, A.EDIT) is S.AWAITING_REVIEW
    assert next_status(S.AWAITING_REVIEW, A.REJECT) is S.REJECTED


@pytest.mark.parametrize("status,action", [
    (S.PLANNED, A.ACCEPT), (S.RUNNING, A.ACCEPT), (S.RUNNING, A.REJECT), (S.ACCEPTED, A.RETRY),
    (S.REJECTED, A.ACCEPT), (S.ACCEPTED, A.START), (S.AWAITING_REVIEW, A.START),
])
def test_invalid_transitions_are_refused(status, action):
    with pytest.raises(InvalidTransition):
        next_status(status, action, note="n")


def test_ui_actions_only_exist_while_awaiting_review():
    assert set(available_actions(S.AWAITING_REVIEW)) == {A.ACCEPT, A.EDIT, A.RETRY, A.REJECT}
    for s in (S.PLANNED, S.RUNNING, S.ACCEPTED, S.REJECTED):
        assert available_actions(s) == []


def test_next_step_starts_only_after_the_previous_is_resolved():
    assert next_to_start([S.PLANNED, S.PLANNED]) == 0
    assert next_to_start([S.ACCEPTED, S.PLANNED, S.PLANNED]) == 1
    assert next_to_start([S.REJECTED, S.PLANNED]) == 1          # PM chose to proceed without that agent
    assert next_to_start([S.RUNNING, S.PLANNED]) is None
    assert next_to_start([S.AWAITING_REVIEW, S.PLANNED]) is None  # accepting is what starts the next
    assert next_to_start([S.ACCEPTED, S.ACCEPTED]) is None
    assert next_to_start([]) is None
