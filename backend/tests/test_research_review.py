"""Research checks are deterministic and never fetch or invent evidence."""
from app.orchestration.review import build_review


def step(output, status="accepted"):
    return {"status": status, "structured_output_refs": {"output": output}}


def finding(id, signal, market, source, level="Verified"):
    return {"id": id, "signal_type": signal, "market": market, "source_file": source,
            "locator": f"sheet Feedback, row {id}", "text": f"Statement {id}", "evidence_level": level}


def test_challenge_market_map_and_ranked_research_actions():
    steps = [step({"findings": [finding("a", "complaint", "US", "owners.xlsx"),
                                 finding("b", "praise", "EU", "study.xlsx", "Interpreted"),
                                 finding("c", "praise", "CN", "discarded.xlsx")]}),
             step({"requirements": [{"id": "r1", "title": "Improve seat comfort",
                                      "linked_finding_ids": ["a", "b"]}]})]
    result = build_review({"market": "ALL"}, steps)
    review = result["requirements"][0]
    assert [f["finding_id"] for f in review["support"]] == ["a"]
    assert review["counter"] == [{"finding_id": "b", "text": "Statement b", "source": "study.xlsx",
                                  "locator": "sheet Feedback, row b", "market": "EU", "evidence_level": "Interpreted"}]
    assert [(m["market"], m["status"]) for m in review["markets"]] == [
        ("EU", "positive signal"), ("CN", "not assessed"), ("US", "need signal"), ("RoW", "not assessed")]
    assert [a["action"] for a in review["actions"]] == [
        "Collect market-specific evidence", "Validate interpreted evidence", "Define a measurable test"]
    assert "CN, RoW" in review["actions"][0]["reason"]
    assert "not a refutation" in result["scope_note"]


def test_uncited_out_of_scope_failed_and_unlinked_findings_are_not_used():
    steps = [step({"findings": [finding("a", "complaint", "US", "owners.xlsx"),
                                 finding("b", "praise", "US", "owners.xlsx"),
                                 {**finding("c", "praise", "US", "hidden.xlsx"), "out_of_scope_reason": "regulatory"},
                                 {**finding("d", "praise", "US", "missing.xlsx"), "locator": ""}]}),
             step({"findings": [finding("e", "praise", "US", "failed.xlsx")]}, status="rejected"),
             step({"requirements": [{"id": "r", "title": "Seat", "linked_finding_ids": ["a", "c", "d", "e"]}]})]
    review = build_review({"market": "US"}, steps)["requirements"][0]
    assert [f["finding_id"] for f in review["support"]] == ["a"]
    assert review["counter"] == []
    assert len(review["markets"]) == 1 and review["markets"][0]["status"] == "need signal"
    assert [a["action"] for a in review["actions"]] == [
        "Seek an independent source", "Define a measurable test", "Look for counter-evidence"]


def test_no_drafts_means_no_review_and_positive_only_is_not_marked_opposing():
    assert build_review({"market": "ALL"}, [step({"findings": [finding("a", "praise", "US", "s.xlsx")]})]) is None
    result = build_review({"market": "US"}, [
        step({"findings": [finding("a", "praise", "US", "s.xlsx")]}),
        step({"requirements": [{"id": "r", "title": "Protect current comfort", "linked_finding_ids": ["a"]}]})])
    assert [f["finding_id"] for f in result["requirements"][0]["support"]] == ["a"]
    assert result["requirements"][0]["counter"] == []


def test_counter_signal_is_surfaced_from_the_same_cluster_even_if_not_linked_to_the_draft():
    result = build_review({"market": "US"}, [
        step({"findings": [finding("a", "complaint", "US", "owners.xlsx"),
                           finding("b", "praise", "US", "study.xlsx"),
                           finding("c", "praise", "US", "other-topic.xlsx")]}),
        step({"clusters": [{"id": "seat", "member_finding_ids": ["a", "b"]},
                           {"id": "powertrain", "member_finding_ids": ["c"]}]}),
        step({"requirements": [{"id": "r", "title": "Seat comfort", "linked_finding_ids": ["a"],
                                "linked_cluster_ids": ["seat"]}]})])
    review = result["requirements"][0]
    assert [f["finding_id"] for f in review["counter"]] == ["b"]
    assert review["markets"][0]["status"] == "mixed"


def test_a_source_grounded_metric_does_not_trigger_a_measurement_gap():
    result = build_review({"market": "US"}, [
        step({"findings": [finding("a", "complaint", "US", "owners.xlsx")]}),
        step({"requirements": [{"id": "r", "title": "Seat comfort", "linked_finding_ids": ["a"],
                                "metric": {"text": "Time to adjust the seat in a measured user test"}}]})])
    assert "Define a measurable test" not in [a["action"] for a in result["requirements"][0]["actions"]]


def test_review_is_saved_with_the_final_chat_message(monkeypatch):
    from app.orchestration import runner, service

    saved = []
    monkeypatch.setattr(service, "add_message", lambda *args, **kwargs: saved.append(kwargs) or {})
    monkeypatch.setattr(runner, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_register_requirements", lambda *args: 1)

    class Conn:
        def execute(self, *_args):
            return None

    run = {"id": "run", "conversation_id": "conversation", "market": "US", "query_text": "Seat comfort?"}
    steps = [step({"findings": [finding("a", "complaint", "US", "owners.xlsx")]}),
             step({"requirements": [{"id": "r", "title": "Improve seats", "linked_finding_ids": ["a"]}]})]
    for index, item in enumerate(steps):
        item.update({"id": str(index), "agent_name": "Test Agent", "human_readable_summary": "Cited answer."})
    runner._complete(Conn(), run, steps, [])
    assert saved[0]["payload"]["research_review"]["requirements"][0]["title"] == "Improve seats"
    assert saved[0]["payload"]["accepted_step_ids"] == ["0", "1"]
    assert saved[0]["payload"]["requirements"] == 1
