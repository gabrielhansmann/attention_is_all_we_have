import json
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.customer_feedback_agent import (
    AGENT_NAME,
    EvidencePack,
    build_result,
    collect_evidence,
    evidence_from_hit,
    load_draft,
    load_evidence,
    run_agent,
    scope_filter,
    store_result,
)

EVIDENCE = ROOT / "tests/fixtures/customer_feedback_evidence.json"
DRAFT = ROOT / "tests/fixtures/customer_feedback_draft.json"


def hit(kind, id, file, locator, quote, **meta):
    """Shaped like `app.knowledge.tools.Hit`, without importing the database-backed module."""
    return SimpleNamespace(
        citation=SimpleNamespace(kind=kind, id=id, file=file, locator=locator, quote=quote),
        text=meta.pop("text", quote),
        meta=meta,
    )


class FakeTools:
    """Stands in for the knowledge tools and records the filters each call received."""

    def __init__(self, comments=True):
        self.calls = []
        self.comments = comments

    def search_feedback(self, query, *, line=None, market=None, domain=None, polarity=None, powertrain=None, k=10):
        self.calls.append(("search_feedback", line, market, polarity))
        if not self.comments:
            return []
        return [
            hit("feedback", f"fb-{polarity}", "G60_feedback_hackathon.xlsx", f"sheet Feedback_Explorer, row 1 ({polarity})",
                f"a {polarity} comment about seats", vehicle_line="G60", market_code="US", polarity=polarity)
        ]

    def get_study(self, *, line=None, market=None, question=None, limit=60):
        self.calls.append(("get_study", line, market, None))
        return [
            hit("study", "st-1", "studies.xlsx", "sheet US, cell D14", "Satisfaction with seat comfort | G60 | share = 0.410",
                text="Satisfaction with seat comfort", vehicle_line="G60", market_code="US"),
            hit("study", "st-2", "studies.xlsx", "sheet US, cell D30", "Likelihood to recommend | G60 | share = 0.700",
                text="Likelihood to recommend", vehicle_line="G60", market_code="US"),
        ]

    def feedback_stats(self, group_by, *, line=None, market=None, domain=None, polarity=None, powertrain=None):
        self.calls.append(("feedback_stats", line, market, group_by))
        if not self.comments:
            return []
        if group_by == "market_code":
            return [{"key": "US", "n": 30}, {"key": "EU", "n": 12}]
        return [{"key": "negative", "n": 20}, {"key": "positive", "n": 15}, {"key": "request", "n": 7}]


class FakeConn:
    """Records SQL instead of running it; every `returning id` yields a new id."""

    def __init__(self):
        self.statements = []

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        row = None
        if "from public.source" in sql or "returning id" in sql:
            row = (f"id-{len(self.statements)}",)
        return SimpleNamespace(fetchone=lambda: row)


class FakeEmbeddings:
    def create(self, model, input):
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0, 1.0]) for _ in input])


class CustomerFeedbackAgentTest(unittest.TestCase):
    def test_scope_all_means_no_filter(self):
        for value in (None, "", "ALL", "all", " All "):
            self.assertIsNone(scope_filter(value))
        self.assertEqual(scope_filter("G60"), "G60")

        tools = FakeTools()
        collect_evidence(tools, "seat comfort", "ALL", None)
        self.assertTrue(all(line is None and market is None for _, line, market, _ in tools.calls))

        tools = FakeTools()
        collect_evidence(tools, "seat comfort", "G60", "US")
        self.assertTrue(all(line == "G60" for _, line, _, _ in tools.calls))
        self.assertEqual({p for name, _, _, p in tools.calls if name == "search_feedback"}, {"negative", "request", "positive"})

    def test_collect_evidence_reads_through_the_tools_and_states_gaps(self):
        pack = collect_evidence(FakeTools(), "seat comfort", "G60", None)

        self.assertEqual([e.kind for e in pack.hits], ["feedback", "feedback", "feedback", "study"])
        self.assertEqual(pack.hits[-1].id, "st-1")  # only the study question that shares words with the query
        self.assertEqual(pack.counts, {"negative": 20, "positive": 15, "request": 7})
        self.assertTrue(any("CN, RoW" in gap for gap in pack.gaps))
        self.assertTrue(any("no respondent counts" in gap for gap in pack.gaps))

        empty = collect_evidence(FakeTools(comments=False), "seat comfort", "G60", "CN")
        self.assertTrue(any("No customer comments exist for G60 / CN" in gap for gap in empty.gaps))

    def test_hit_without_locator_is_not_evidence(self):
        self.assertIsNone(evidence_from_hit(hit("feedback", "x", "file.xlsx", "", "quote")))
        self.assertIsNone(evidence_from_hit({"citation": {"kind": "feedback", "id": "x", "locator": "row 1"}}))

    def test_build_result_cites_only_retrieved_rows(self):
        pack = load_evidence(EVIDENCE)
        result = build_result("G60", "US", "seat comfort", pack, load_draft(DRAFT))

        self.assertEqual(result.agent_name, AGENT_NAME)
        self.assertEqual(result.evidence_read, 6)
        self.assertEqual(len(result.findings), 5)
        # The two drafted items without a retrieved row behind them are dropped, not kept uncited.
        self.assertEqual(sum("cited no retrieved evidence" in s["reason"] for s in result.skipped), 2)

        known = {(e.file, e.locator, e.quote) for e in pack.hits}
        for finding in result.findings:
            self.assertTrue(finding.citations)
            for c in finding.citations:
                self.assertIn((c["file"], c["locator"], c["quote"]), known)
            self.assertIn(finding.citations[0]["locator"], finding.locator)
            self.assertIn(finding.signal_type, {"complaint", "unmet_need", "praise"})
            self.assertEqual((finding.market, finding.vehicle_line), ("US", "G60"))

    def test_signal_type_sample_size_and_evidence_level(self):
        result = build_result("ALL", None, "seat comfort", load_evidence(EVIDENCE), load_draft(DRAFT))
        complaint, unmet, praise, study, _pricing = result.findings

        self.assertEqual((result.vehicle_line, result.market), ("ALL", "ALL"))
        self.assertEqual((complaint.market, complaint.vehicle_line), ("US", "G60"))  # taken from the cited rows
        self.assertEqual((complaint.signal_type, complaint.sample_size, complaint.sample_base), ("complaint", 2, 2140))
        self.assertEqual(complaint.evidence_level, "Interpreted")
        self.assertEqual((unmet.signal_type, unmet.sample_size, unmet.sample_base), ("unmet_need", 1, 615))
        self.assertTrue(any("single customer comment" in a for a in unmet.assumptions))
        # Drafted as a complaint, but the cited comment is positive: the evidence decides.
        self.assertEqual((praise.signal_type, praise.polarity), ("praise", "positive"))
        self.assertTrue(any("Draft labelled this complaint" in a for a in praise.assumptions))
        # Study cells are structured rows without respondent counts.
        self.assertEqual((study.evidence_level, study.sample_size, study.sample_base), ("Verified", None, None))
        self.assertIn("cell D14", study.locator)

    def test_pricing_goes_to_the_out_of_scope_bin(self):
        result = build_result("G60", "US", "seat comfort", load_evidence(EVIDENCE), load_draft(DRAFT))

        self.assertEqual([f.out_of_scope_reason is not None for f in result.findings], [False, False, False, False, True])
        _, bin_section = result.summary.split("Out of scope (routed to the side bin):")
        self.assertIn("too expensive", bin_section)
        self.assertNotIn("too expensive", result.summary.split("Confidence and gaps:")[0])

    def test_summary_says_what_was_read_found_and_missing(self):
        result = build_result("G60", "US", "seat comfort", load_evidence(EVIDENCE), load_draft(DRAFT))

        self.assertIn("looked at 6 retrieved rows (5 feedback, 1 study) for G60 / US: seat comfort", result.summary)
        self.assertIn("G60_feedback_hackathon.xlsx", result.summary)
        self.assertIn(
            "n=2 cited of 2140 negative comments in scope; G60_feedback_hackathon.xlsx, sheet Feedback_Explorer, row 4642 (G60-3695)",
            result.summary,
        )
        self.assertIn("no respondent counts", result.summary)
        self.assertIn("rest on a single comment", result.summary)
        # The agent reports evidence only: no requirement, score or priority fields on the result.
        payload = asdict(result)
        self.assertEqual(payload["summary"], result.summary)
        self.assertFalse({"requirements", "score", "priority", "status"} & set(payload) | {"score", "priority"} & set(payload["findings"][0]))

    def test_run_agent_uses_injected_tools_and_draft_only(self):
        def draft_for(pack):
            return {"findings": [{"evidence": [1], "text": "Owners complain about seats.", "signal_type": "praise"}]}

        tools = FakeTools()
        pack = collect_evidence(tools, "seat comfort", "G60", "US")
        result = run_agent("seat comfort", "G60", "US", tools=tools, draft=draft_for(pack))
        self.assertEqual(result.findings[0].signal_type, "complaint")
        self.assertEqual(result.findings[0].sample_base, 20)

        # Nothing retrieved: no model call is made and nothing is claimed.
        nothing = run_agent("seat comfort", "G60", "CN", pack=EvidencePack(hits=[], gaps=["No customer comments exist for G60 / CN."]))
        self.assertEqual(nothing.findings, [])
        self.assertIn("No usable customer-feedback findings", nothing.summary)
        self.assertIn("No customer comments exist for G60 / CN.", nothing.summary)

    def test_store_result_leaves_the_step_awaiting_review(self):
        result = build_result("G60", "US", "seat comfort", load_evidence(EVIDENCE), load_draft(DRAFT))
        conn = FakeConn()
        store_result(conn, SimpleNamespace(embeddings=FakeEmbeddings()), result, None, "step-1")

        sql = [s for s, _ in conn.statements]
        self.assertIn("status = 'awaiting_review'", sql[0])
        self.assertFalse(any("accepted" in s or "rejected" in s or "public.requirement" in s for s in sql))
        self.assertEqual(sum("insert into public.finding (" in s for s in sql), 5)
        evidence_links = [s for s in sql if "insert into public.finding_evidence" in s]
        self.assertEqual(len(evidence_links), 6)
        self.assertEqual(sum("study_response_id" in s for s in evidence_links), 1)
        self.assertIn("structured_output_refs", sql[-1])

    def test_cli_dry_run_works_without_openai_or_database(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.agents.customer_feedback_agent",
                "seat comfort",
                "--vehicle-line",
                "G60",
                "--market",
                "US",
                "--evidence-json",
                str(EVIDENCE),
                "--draft-json",
                str(DRAFT),
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["agent_name"], AGENT_NAME)
        self.assertEqual((payload["vehicle_line"], payload["market"]), ("G60", "US"))
        self.assertEqual(len(payload["findings"]), 5)
        self.assertIn("row 4642", payload["findings"][0]["locator"])
        self.assertEqual(payload["findings"][0]["sample_size"], 2)


if __name__ == "__main__":
    unittest.main()
