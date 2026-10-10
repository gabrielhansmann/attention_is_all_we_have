"""Guards against the backend and the database disagreeing about the step states and message kinds.
Reads the migration files, so it needs no database."""
import re
from pathlib import Path

from app.orchestration.steps import StepStatus

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


def check_values(sql: str, constraint: str) -> set[str]:
    """The quoted values of a named CHECK (... in (...)) constraint."""
    m = re.search(rf"constraint {constraint}\s+check \(status in \(([^)]*)\)", sql)
    assert m, f"constraint {constraint} not found"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def test_step_states_in_the_database_match_the_state_machine():
    sql = (MIGRATIONS / "20261011_chat_tables.sql").read_text()
    assert check_values(sql, "step_status_check") == {s.value for s in StepStatus}


def test_one_active_step_per_run_is_enforced_by_an_index():
    sql = (MIGRATIONS / "20261011_chat_tables.sql").read_text()
    m = re.search(r"unique index step_one_active_per_run on public\.step\(run_id\)\s+where status in \(([^)]*)\)", sql)
    assert m
    assert set(re.findall(r"'([^']+)'", m.group(1))) == {StepStatus.RUNNING.value, StepStatus.AWAITING_REVIEW.value}
