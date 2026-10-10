"""The LangGraph side of the loop (decision 0019): resuming an interrupted run, never calling an agent twice, the
run lock, and the real Postgres checkpointer. Against the real database, app tables rolled back (see conftest.db)."""
import os
from contextlib import nullcontext

import psycopg
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.orchestration import loop, service
from app.orchestration.agents import RUNNERS
from orch_fakes import FEEDBACK, FINISH, TREND, FakeAgent, ScriptedOrchestrator, call


class Crash(BaseException):
    """A process dying: not an Exception, so nothing in the loop handles it and the run is left as it was."""


def opened(db, orchestrator):
    cid = service.create_conversation(db)["id"]
    return service.post_request(db, cid, "competitive trends", orchestrator)["run"]


def thread(db, run):
    return {"run": db.execute("select * from public.pipeline_run where id = %s", (run["id"],)).fetchone(),
            "steps": service.list_steps(db, run["id"]), "messages": service.list_messages(db, run["conversation_id"])}


def drive(db, run, orchestrator, runners, saver, **kw):
    loop.orchestrate(lambda: nullcontext(db), run["id"], orchestrator, runners, checkpointer=lambda: nullcontext(saver), **kw)


@pytest.fixture
def runners():
    return {name: FakeAgent(name) for name in RUNNERS}


def test_the_graph_has_the_four_nodes_and_the_loop_edges():
    graph = loop.build_graph(lambda: nullcontext(None), ScriptedOrchestrator(), {}).compile()
    drawn = graph.get_graph()
    assert {"decide", "validate", "run_agent", "finish"} <= set(drawn.nodes)
    edges = {(e.source, e.target) for e in drawn.edges}
    assert ("run_agent", "decide") in edges and ("validate", "decide") in edges and ("finish", "__end__") in edges


def test_a_run_interrupted_between_agents_continues_without_repeating_the_first(db, runners):
    saver = InMemorySaver()
    first = ScriptedOrchestrator(call(FEEDBACK), Crash())
    run = opened(db, first)
    with pytest.raises(Crash):
        drive(db, run, first, runners, saver)
    assert [(s["agent_name"], s["status"]) for s in thread(db, run)["steps"]] == [(FEEDBACK, "accepted")]
    assert thread(db, run)["run"]["status"] == "in_progress"

    second = ScriptedOrchestrator(call(TREND), FINISH)           # the process is back; same run, same checkpointer
    drive(db, run, second, runners, saver, resume_only=True)
    after = thread(db, run)
    assert after["run"]["status"] == "completed" and after["messages"][-1]["kind"] == "final_result"
    assert [(s["agent_name"], s["status"]) for s in after["steps"]] == [(FEEDBACK, "accepted"), (TREND, "accepted")]
    assert len(runners[FEEDBACK].seen) == 1                       # not run again
    assert [o.agent for o in second.calls[0]["history"]] == [FEEDBACK]   # the history comes from the tables


def test_an_agent_that_was_running_when_the_process_died_runs_again_in_the_same_step(db, runners):
    saver = InMemorySaver()
    runners[FEEDBACK] = FakeAgent(FEEDBACK, Crash())
    first = ScriptedOrchestrator(call(FEEDBACK), FINISH)
    run = opened(db, first)
    with pytest.raises(Crash):
        drive(db, run, first, runners, saver)
    assert [(s["agent_name"], s["status"]) for s in thread(db, run)["steps"]] == [(FEEDBACK, "running")]

    runners[FEEDBACK] = FakeAgent(FEEDBACK)
    drive(db, run, ScriptedOrchestrator(FINISH), runners, saver, resume_only=True)
    after = thread(db, run)
    assert [(s["agent_name"], s["status"]) for s in after["steps"]] == [(FEEDBACK, "accepted")]   # one step, not two
    assert len(runners[FEEDBACK].seen) == 1 and after["run"]["status"] == "completed"
    assert [m["kind"] for m in after["messages"]].count("system_note") == 1                       # one "Calling ..." note


def test_a_step_that_finished_before_the_interruption_is_not_called_again(db, runners):
    """The crash came after the agent finished but before the graph moved on: the pending call must be skipped."""
    saver = InMemorySaver()
    orchestrator = ScriptedOrchestrator(call(FEEDBACK), FINISH)
    run = opened(db, orchestrator)
    graph = loop.build_graph(lambda: nullcontext(db), orchestrator, runners).compile(checkpointer=saver)
    config = {"configurable": {"thread_id": str(run["id"])}}
    # run it normally, then roll the graph state back to just before run_agent and resume
    drive(db, run, orchestrator, runners, saver)
    assert len(runners[FEEDBACK].seen) == 1
    before = [s for s in graph.get_state_history(config) if s.next == ("run_agent",)][0]
    resumed = ScriptedOrchestrator(FINISH)
    loop.build_graph(lambda: nullcontext(db), resumed, runners).compile(checkpointer=saver).invoke(None, before.config)
    assert len(runners[FEEDBACK].seen) == 1                       # still one call
    assert [s["agent_name"] for s in thread(db, run)["steps"]] == [FEEDBACK]


def test_a_run_that_is_already_being_driven_elsewhere_is_left_alone(db, runners):
    url = os.environ["SUPABASE_DB_URL"]
    orchestrator = ScriptedOrchestrator(call(FEEDBACK), FINISH)
    run = opened(db, orchestrator)
    with psycopg.connect(url, autocommit=True) as other:
        other.execute("select pg_advisory_lock(hashtextextended(%s, 0))", (str(run["id"]),))
        try:
            drive(db, run, orchestrator, runners, InMemorySaver())
        finally:
            other.execute("select pg_advisory_unlock(hashtextextended(%s, 0))", (str(run["id"]),))
    assert orchestrator.calls == [] and thread(db, run)["steps"] == []
    drive(db, run, orchestrator, runners, InMemorySaver())        # lock released: it runs
    assert thread(db, run)["run"]["status"] == "completed"


def test_resume_only_leaves_a_run_with_steps_but_no_checkpoint_alone(db, runners):
    """A run from before decision 0019 has steps and no checkpoint: it must not be picked up by the new loop."""
    orchestrator = ScriptedOrchestrator(call(TREND), FINISH)
    run = opened(db, orchestrator)
    db.execute("insert into public.step (run_id, agent_name, stage, position, status) values (%s, %s, 1, 1, 'awaiting_review')",
               (run["id"], FEEDBACK))
    drive(db, run, orchestrator, runners, InMemorySaver(), resume_only=True)
    assert orchestrator.calls == [] and thread(db, run)["run"]["status"] == "in_progress"


def test_resume_only_starts_a_run_that_crashed_before_its_first_step(db, runners):
    orchestrator = ScriptedOrchestrator(call(FEEDBACK), FINISH)
    run = opened(db, orchestrator)
    drive(db, run, orchestrator, runners, InMemorySaver(), resume_only=True)
    assert thread(db, run)["run"]["status"] == "completed"


def test_resume_unfinished_starts_one_thread_per_open_run(monkeypatch):
    started = []

    class Rows:
        def fetchall(self):
            return [{"id": "run-a"}, {"id": "run-b"}]

    class Conn:
        def execute(self, *a):
            return Rows()

    monkeypatch.setattr(loop, "orchestrate", lambda *a: started.append(a[1]))
    threads = loop.resume_unfinished(lambda: nullcontext(Conn()), ScriptedOrchestrator(), {}, lambda: nullcontext(None))
    for t in threads:
        t.join(2)
    assert sorted(started) == ["run-a", "run-b"]


def test_the_postgres_checkpointer_keeps_state_across_processes(db, runners):
    """Real checkpoint tables: crash, then continue with a fresh saver connection. Cleans up what it wrote."""
    first = ScriptedOrchestrator(call(FEEDBACK), Crash())
    run = opened(db, first)
    key = str(run["id"])
    url = os.environ["SUPABASE_DB_URL"]
    try:
        with pytest.raises(Crash):
            loop.orchestrate(lambda: nullcontext(db), run["id"], first, runners)       # default: postgres_checkpointer
        with psycopg.connect(url) as c:
            assert c.execute("select count(*) from public.checkpoints where thread_id = %s", (key,)).fetchone()[0] > 0
        second = ScriptedOrchestrator(call(TREND), FINISH)
        loop.orchestrate(lambda: nullcontext(db), run["id"], second, runners, resume_only=True)
        assert thread(db, run)["run"]["status"] == "completed" and len(runners[FEEDBACK].seen) == 1
    finally:
        with psycopg.connect(url, autocommit=True) as c:
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
                c.execute(f"delete from public.{table} where thread_id = %s", (key,))
