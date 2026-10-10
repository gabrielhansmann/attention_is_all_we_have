import copy
import json
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.prioritization_agent import (
    AGENT_NAME,
    ScoringWeights,
    build_result,
    compose,
    market_weights_from_sales,
    store_result,
    tier_for,
)

FIXTURE = ROOT / "tests/fixtures/prioritization_agent_r2031.json"


class FakeCursor:
    def fetchone(self):
        return ["00000000-0000-0000-0000-000000000001"]


class FakeConn:
    """Records the SQL an agent would run, so storage is checked without a database."""

    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        return FakeCursor()

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def run(payload, **kwargs):
    kwargs.setdefault("themes", payload.get("themes"))
    return build_result("G60", "EU", payload["requirements"], payload["findings"], **kwargs)


class PrioritizationAgentTest(unittest.TestCase):
    def test_formula_and_tiers_follow_the_doc(self):
        values = {"customer_relevance": 0.78, "business_signal": 0.41, "strategic_fit": 0.60, "effort_proxy": 0.05}
        self.assertAlmostEqual(compose(values, ScoringWeights()), 0.40 * 0.78 + 0.25 * 0.41 + 0.15 * 0.60 - 0.20 * 0.05)
        self.assertEqual(tier_for(0.65), "Tier 1 (must-have)")
        self.assertEqual(tier_for(0.49), "Tier 2 (should-have)")
        self.assertEqual(tier_for(0.39), "Tier 3 (watch-list)")

    def test_reproduces_the_r2031_worked_example(self):
        result = run(load())

        self.assertEqual(result.agent_name, AGENT_NAME)
        self.assertEqual(result.weights, {"customer_relevance": 0.40, "business_signal": 0.25, "strategic_fit": 0.15, "effort_proxy": 0.20})
        score = result.scores[0]
        self.assertEqual(score.requirement_code, "R-2031")
        self.assertEqual(score.customer_relevance, 0.78)
        self.assertEqual(score.business_signal, 0.41)
        self.assertEqual(score.strategic_fit, 0.60)
        self.assertEqual(score.effort_level, "low")
        self.assertEqual(score.confidence, 0.65)
        self.assertEqual(round(score.composite, 2), 0.49)
        self.assertEqual(score.proposed_tier, "Tier 2 (should-have)")
        self.assertNotIn("\n", score.rationale)

    def test_breakdown_shows_weight_and_contribution_and_keeps_citations(self):
        score = run(load()).scores[0]

        self.assertEqual([c.name for c in score.breakdown], ["customer_relevance", "business_signal", "strategic_fit", "effort_proxy"])
        for component in score.breakdown:
            self.assertAlmostEqual(abs(component.contribution), component.weight * component.value, places=4)
        self.assertLess(score.breakdown[-1].contribution, 0)
        self.assertAlmostEqual(sum(c.contribution for c in score.breakdown), score.composite, places=4)

        self.assertEqual(score.finding_ids, ["F-101", "F-102", "F-103", "F-104"])
        self.assertEqual([c["finding_id"] for c in score.citations], score.finding_ids)
        self.assertTrue(all(c["locator"] for c in score.citations))
        self.assertEqual(score.breakdown[1].finding_ids, ["F-104", "F-103"])
        for finding_id in {i for c in score.breakdown for i in c.finding_ids}:
            self.assertIn(finding_id, score.finding_ids)

    def test_summary_names_scope_scores_citations_and_gaps(self):
        result = run(load())

        self.assertIn("1 draft requirement(s) and 4 citable finding(s) for G60 / EU", result.summary)
        self.assertIn("R-2031 Fast-response seat ventilation: 0.49, Tier 2 (should-have), confidence 0.65", result.summary)
        self.assertIn("sheet Feedback_Explorer, row 4642 (G60-3695)", result.summary)
        self.assertIn("Confidence and gaps:", result.summary)
        self.assertIn("no previous-generation baseline finding", result.summary)
        self.assertIn("review-estimated, not lab-verified", result.summary)

    def test_pm_can_nudge_a_weight_and_rerun(self):
        payload = load()
        base = run(payload).scores[0]
        nudged_weights = ScoringWeights().with_overrides({"business_signal": 0.35})
        nudged = run(payload, weights=nudged_weights).scores[0]

        self.assertAlmostEqual(nudged.composite - base.composite, 0.10 * 0.41, places=4)
        self.assertEqual(nudged.weights["business_signal"], 0.35)
        self.assertEqual(nudged.weights["customer_relevance"], 0.40)
        self.assertNotEqual(nudged.weight_vector_version, base.weight_vector_version)
        self.assertEqual(nudged.confidence, base.confidence)
        self.assertEqual(ScoringWeights().with_overrides({"business_signal": 0.35}, "v1.4").version, "v1.4")
        with self.assertRaises(ValueError):
            ScoringWeights().with_overrides({"gut_feeling": 0.5})

    def test_missing_inputs_are_stated_and_lower_confidence(self):
        payload = load()
        base = run(payload).scores[0]
        self.assertEqual(len(base.missing), 2)
        self.assertIn("F-101 has no prevalence with a sample size, left out of prevalence", base.missing)

        payload["findings"] = [f for f in payload["findings"] if f["id"] != "F-104"]
        del payload["requirements"][0]["effort_proxy"]
        score = run(payload, themes=[]).scores[0]

        self.assertLess(score.confidence, base.confidence)
        self.assertLess(score.business_signal, base.business_signal)
        self.assertEqual(score.effort_level, "medium")
        stated = " | ".join(score.missing)
        self.assertIn("no option uptake % finding", stated)
        self.assertIn("linked finding F-104 was not passed in", stated)
        self.assertIn("no effort estimate", stated)
        self.assertIn("no program themes stated by the PM", stated)

    def test_reads_the_fields_the_upstream_agents_emit(self):
        payload = load()
        complaint, _, _, uptake = payload["findings"]
        complaint.update(sample_size=30, sample_base=100)            # Customer Feedback Agent: cited of in-scope comments
        del uptake["uptake_pct"]
        uptake["metrics"] = {"metric": "standard_fitment_share", "share_pct": 55.0}   # Sales & Portfolio Agent
        payload["requirements"][0]["description"] = {"text": "Comfort parity on seat cooling.", "finding_ids": ["F-101"]}
        payload["requirements"][0].pop("themes")
        score = run(payload).scores[0]

        prevalence = score.breakdown[0].inputs[0]
        self.assertEqual(prevalence["finding_ids"], ["F-101", "F-102"])
        self.assertEqual(prevalence["value"], round((0.3 * 100 + 0.6 * 340) / 440, 4))
        self.assertEqual(score.business_signal, 0.41)
        self.assertEqual(score.strategic_fit, 0.60)
        self.assertIn("F-104: uptake is the standard-fitment share, a portfolio proxy, not a measured take rate", score.thin)

    def test_uncitable_and_out_of_scope_findings_never_back_a_score(self):
        payload = load()
        payload["findings"][0].pop("locator")
        payload["findings"][2]["out_of_scope_reason"] = "pricing topic"
        result = run(payload)

        self.assertEqual(result.scores[0].finding_ids, ["F-102", "F-104"])
        self.assertEqual(len(result.skipped), 2)

        payload["requirements"][0]["linked_finding_ids"] = ["F-101"]
        result = run(payload)
        self.assertEqual(result.scores, [])
        self.assertIn("no score is proposed", result.skipped[-1]["reason"])

    def test_several_markets_are_weighted_by_cited_sales_volume(self):
        payload = load()
        payload["requirements"][0]["markets"] = ["EU", "US"]
        sales = [
            {"market_code": "EU", "year": 2025, "volume": 60000, "is_forecast": False,
             "citation": {"kind": "sales", "id": "s1", "file": "sales_volumes.xlsx", "locator": "sheet G60_G68, row 3", "quote": "G60 Europe 2025: 60000 units"}},
            {"market_code": "US", "year": 2025, "volume": 40000, "is_forecast": False,
             "citation": {"kind": "sales", "id": "s2", "file": "sales_volumes.xlsx", "locator": "sheet G60_G68, row 4", "quote": "G60 US 2025: 40000 units"}},
            {"market_code": "US", "year": 2030, "volume": 90000, "is_forecast": True,
             "citation": {"kind": "sales", "id": "s3", "file": "sales_volumes.xlsx", "locator": "sheet G60_G68, row 5", "quote": "forecast"}},
        ]
        self.assertEqual(market_weights_from_sales(sales, ["EU", "US"])[0], {"EU": 0.6, "US": 0.4})

        score = run(payload, sales=sales).scores[0]
        self.assertEqual(score.market_scores, {"EU": 0.78, "US": 0.0})
        self.assertEqual(score.customer_relevance, round(0.6 * 0.78, 4))
        self.assertEqual([c["id"] for c in score.evidence_citations], ["s1", "s2"])
        self.assertIn("US: no customer finding (complaint or unmet need) is linked", score.missing)

        unweighted = run(payload).scores[0]
        self.assertEqual(unweighted.customer_relevance, 0.39)
        self.assertIn("no cited sales volume for every market in scope, markets weighted equally", unweighted.missing)

    def test_agent_proposes_only_and_leaves_the_step_in_review(self):
        payload = load()
        before = copy.deepcopy(payload)
        result = run(payload)
        self.assertEqual(payload, before)
        self.assertNotIn("status", asdict(result)["scores"][0])

        conn = FakeConn()
        store_result(conn, result, run_id=None, step_id="step-1")
        sql = " ".join(statement for statement, _ in conn.statements)
        self.assertIn("set status = 'awaiting_review'", sql)
        self.assertIn("insert into public.score", sql)
        self.assertIn("insert into public.audit_event", sql)
        self.assertNotIn("public.requirement", sql)
        self.assertNotIn("'accepted'", sql)

    def test_cli_dry_run_works_without_openai_or_database(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.agents.prioritization_agent",
                "--input-json",
                str(FIXTURE),
                "--vehicle-line",
                "G60",
                "--market",
                "EU",
                "--weight",
                "business_signal=0.35",
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["vehicle_line"], "G60")
        self.assertEqual(payload["weights"]["business_signal"], 0.35)
        self.assertEqual(round(payload["scores"][0]["composite"], 2), 0.54)
        self.assertEqual(payload["scores"][0]["citations"][0]["finding_id"], "F-101")


if __name__ == "__main__":
    unittest.main()
