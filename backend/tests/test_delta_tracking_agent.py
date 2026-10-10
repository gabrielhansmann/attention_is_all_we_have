import copy
import json
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.delta_tracking_agent import (
    AGENT_NAME,
    build_result,
    direction_of,
    lexical_similarity,
    stance,
    store_result,
)

FIXTURE = ROOT / "tests/fixtures/delta_tracking_agent_batch.json"


class FakeConn:
    """Records the SQL an agent would run, so storage is checked without a database."""

    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def run(payload=None, **kwargs):
    payload = payload or load()
    kwargs.setdefault("as_of", payload["as_of"])
    return build_result(
        "G60", "EU", payload["requirements"], payload["new_findings"],
        existing_findings=payload["existing_findings"], batch_id=payload["batch_id"], **kwargs,
    )


class DeltaTrackingAgentTest(unittest.TestCase):
    def test_flags_new_contradicting_and_stale_evidence(self):
        result = run()

        self.assertEqual(result.agent_name, AGENT_NAME)
        self.assertEqual((result.requirements_checked, result.new_findings_read), (3, 5))
        self.assertEqual(
            [(f.flag_type, f.requirement_code, f.finding_ids) for f in result.flags],
            [("new_evidence", "R-2031", ["F-517"]), ("contradicting", "R-2031", ["F-518"]), ("stale", "R-2040", ["F-201"])],
        )
        self.assertIn("396 days old (limit 365)", result.flags[2].reason)

    def test_every_flag_keeps_ids_and_citations_and_goes_to_pm_review(self):
        for flag in run().flags:
            self.assertEqual(flag.route, "pm_review")
            self.assertEqual(flag.requirement_status, "tracked")
            self.assertEqual([c["finding_id"] for c in flag.citations], flag.finding_ids)
            self.assertTrue(all(c["locator"] for c in flag.citations + flag.compared_citations))
            self.assertTrue(flag.compared_finding_ids)
        new = run().flags[0]
        self.assertEqual(new.compared_finding_ids, ["F-101", "F-102"])
        self.assertEqual(new.citations[0]["locator"], "https://www.autocar.co.uk/reviews/rival-sedan-launch · retrieved 2026-04-01")

    def test_no_material_change_stays_quiet(self):
        result = run()

        self.assertEqual(result.unchanged, ["R-2050"])
        self.assertNotIn("R-2050", [f.requirement_code for f in result.flags])
        flagged = {i for f in result.flags for i in f.finding_ids}
        # unrelated, other-market and already-linked findings raise nothing
        self.assertFalse(flagged & {"F-519", "F-522", "F-101"})

        payload = load()
        payload["new_findings"] = []
        quiet = run(payload, as_of="2026-02-21")
        self.assertEqual(quiet.flags, [])
        self.assertEqual(quiet.unchanged, ["R-2031", "R-2040", "R-2050"])
        self.assertIn("No flags: nothing material changed.", quiet.summary)

    def test_untraceable_out_of_scope_and_untracked_inputs_are_skipped_and_stated(self):
        skipped = {item["item"]: item["reason"] for item in run().skipped}

        self.assertIn("cannot be cited", skipped["F-521"])
        self.assertIn("out of scope", skipped["F-520"])
        self.assertIn("only tracked requirements are checked", skipped["R-2060"])

        payload = load()
        for finding in payload["existing_findings"]:
            finding.pop("created_at")
        undated = run(payload)
        self.assertNotIn("stale", [f.flag_type for f in undated.flags])
        self.assertIn("staleness could not be checked", {i["item"]: i["reason"] for i in undated.skipped}["R-2040"])

    def test_stale_threshold_is_configurable_and_fresh_support_suppresses_it(self):
        strict = run(stale_after_days=60)
        stale = [f.requirement_code for f in strict.flags if f.flag_type == "stale"]
        self.assertEqual(stale, ["R-2040"])            # R-2031 is 80 days old but got new evidence in this batch
        relaxed = run(stale_after_days=500)
        self.assertNotIn("stale", [f.flag_type for f in relaxed.flags])

    def test_explicit_link_and_injected_similarity(self):
        payload = load()
        payload["new_findings"] = [{
            "id": "F-600", "source": "G60_feedback_hackathon_2026Q1.xlsx", "locator": "sheet Feedback_Explorer, row 300 (G60-9300)",
            "text": "Sitzbelüftung reagiert langsam.", "signal_type": "complaint", "market": "EU", "vehicle_line": "G60",
        }]
        self.assertNotIn("F-600", [i for f in run(payload).flags for i in f.finding_ids])

        linked = copy.deepcopy(payload)
        linked["new_findings"][0]["requirement_ids"] = ["req-2031"]
        flag = run(linked).flags[0]
        self.assertEqual((flag.flag_type, flag.finding_ids, flag.match_score), ("new_evidence", ["F-600"], 1.0))

        by_meaning = run(payload, similarity=lambda a, b: 0.9 if "Sitzbelüftung" in a and "ventilation" in b else 0.0)
        self.assertEqual([(f.requirement_code, f.finding_ids) for f in by_meaning.flags if f.flag_type == "new_evidence"],
                         [("R-2031", ["F-600"])])

    def test_stance_and_similarity_helpers(self):
        self.assertEqual(stance({"signal_type": "complaint"}), "gap")
        self.assertEqual(stance({"signal_type": "praise"}), "strength")
        self.assertEqual(stance({"signal_type": "market_trend", "sentiment": 0.6}), "strength")
        self.assertEqual(stance({"signal_type": "market_trend"}), "neutral")
        self.assertEqual(direction_of([{"signal_type": "complaint"}, {"signal_type": "praise"}]), "neutral")
        self.assertEqual(lexical_similarity("Cup holders are too small", "Seat ventilation takes too long"), 0.0)
        self.assertEqual(lexical_similarity("ventilated seats cool slowly", "seat ventilation is slow to cool"), 0.5)

    def test_summary_names_scope_flags_citations_and_gaps(self):
        summary = run().summary

        self.assertIn("compared 5 new finding(s) from batch ingest-2026-Q2 with the evidence of 3 tracked requirement(s) "
                      "for G60 / EU, as of 2026-04-02", summary)
        self.assertIn("- R-2031 contradicting: F-518 reads as a strength", summary)
        self.assertIn("(F-518: G60_feedback_hackathon_2026Q1.xlsx, sheet Feedback_Explorer, row 88 (G60-9012))", summary)
        self.assertIn("Confidence and gaps:", summary)
        self.assertIn("1 requirement(s) had no material change and stay quiet: R-2050.", summary)

    def test_agent_only_flags_and_never_changes_a_requirement(self):
        payload = load()
        before = copy.deepcopy(payload)
        result = run(payload)
        self.assertEqual(payload, before)

        conn = FakeConn()
        store_result(conn, result, run_id=None, step_id="step-9")
        sql = " ".join(statement for statement, _ in conn.statements)
        self.assertIn("set status = 'awaiting_review'", sql)
        self.assertEqual(sum(1 for statement, _ in conn.statements if "insert into public.audit_event" in statement), 3)
        self.assertEqual([params[2] for statement, params in conn.statements if "audit_event" in statement],
                         ["flagged_new_evidence", "flagged_contradicting", "flagged_stale"])
        self.assertNotIn("public.requirement", sql)
        self.assertNotIn("'pm_review'", sql)
        self.assertEqual({f["requirement_status"] for f in asdict(result)["flags"]}, {"tracked"})

    def test_cli_dry_run_works_without_openai_or_database(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.agents.delta_tracking_agent",
                "--input-json",
                str(FIXTURE),
                "--vehicle-line",
                "G60",
                "--market",
                "EU",
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["batch_id"], "ingest-2026-Q2")
        self.assertEqual([f["flag_type"] for f in payload["flags"]], ["new_evidence", "contradicting", "stale"])
        self.assertEqual(payload["flags"][0]["citations"][0]["finding_id"], "F-517")


if __name__ == "__main__":
    unittest.main()
