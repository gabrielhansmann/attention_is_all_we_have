import json
import subprocess
import sys
import unittest
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.clustering_agent import build_result as build_clusters
from app.agents.clustering_agent import load_clustering_draft, load_findings
from app.agents.requirements_drafting_agent import (
    AGENT_NAME,
    NO_METRIC,
    build_drafting_prompt,
    build_result,
    load_clusters,
    load_drafting_draft,
    prepare_clusters,
    store_result,
)

CLUSTERS = ROOT / "tests/fixtures/requirements_drafting_agent_clusters.json"
DRAFT = ROOT / "tests/fixtures/requirements_drafting_agent_draft.json"
SEAT_CLUSTER = "f577bcaf-ea59-536d-94dd-e01f8fd26de1"
ROUTE_CLUSTER = "03c4763f-19cf-5522-9237-44f1919177e6"
CLIMATE_CLUSTER = "e42994c3-2e79-5d39-acd1-5d90550653b4"


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConn:
    """Records SQL instead of running it, so storing can be checked without a database."""

    def __init__(self):
        self.calls = []

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "from public.ontology" in sql:
            return FakeCursor([("comfort_space", "dom-comfort"), ("infotainment", "dom-infotainment")])
        return FakeCursor([("step-1",)])


def finding(fid, text, **extra):
    base = {
        "id": fid,
        "text": text,
        "signal_type": "complaint",
        "evidence_level": "Verified",
        "locator": f"sheet Feedback_Explorer, row {fid}",
        "source": "G60_feedback_hackathon.xlsx",
        "market": "US",
        "vehicle_line": "G60",
        "out_of_scope_reason": None,
    }
    return base | extra


def statement(text, *ids):
    return {"text": text, "finding_ids": list(ids)}


class RequirementsDraftingAgentTest(unittest.TestCase):
    def setUp(self):
        self.clusters = load_clusters(CLUSTERS)
        self.result = build_result("G60", "US", self.clusters, load_drafting_draft(DRAFT))

    def test_drafts_one_requirement_per_supported_cluster(self):
        result = self.result
        self.assertEqual(result.agent_name, AGENT_NAME)
        self.assertEqual((result.clusters_read, result.findings_read), (3, 5))
        self.assertEqual([r.cluster_id for r in result.requirements], [SEAT_CLUSTER, ROUTE_CLUSTER])

        seat = result.requirements[0]
        self.assertEqual(seat.title, "Stronger seat ventilation and cooling")
        self.assertEqual(seat.description.finding_ids, ["f1", "f2"])
        self.assertEqual(seat.metric.finding_ids, ["f1"])
        self.assertEqual([c.finding_ids for c in seat.acceptance_criteria], [["f3"]])
        self.assertEqual(seat.linked_finding_ids, ["f1", "f2", "f3"])
        self.assertEqual(seat.linked_cluster_ids, [SEAT_CLUSTER])
        self.assertEqual((seat.domain_key, seat.markets, seat.vehicle_line), ("comfort_space", ["US"], "G60"))

    def test_every_requirement_is_a_draft_and_carries_no_priority_or_score(self):
        for requirement in asdict(self.result)["requirements"]:
            self.assertEqual(requirement["status"], "Draft")
            self.assertFalse({"priority", "tier", "score", "composite"} & set(requirement))

    def test_statements_without_a_cluster_finding_are_dropped(self):
        dropped = self.result.dropped
        self.assertIn({"cluster_id": "not-a-cluster", "part": "requirement", "reason": "draft referenced an unknown cluster id"}, dropped)
        self.assertIn(
            {"cluster_id": SEAT_CLUSTER, "part": "metric", "finding_id": "f999", "reason": "cited finding is not an in-scope member of the cluster"},
            dropped,
        )
        self.assertTrue(any(d.get("text") == "The cooling function wins an independent comfort award." for d in dropped))
        # f1 belongs to another cluster, so the climate description has no support and no requirement is drafted
        self.assertEqual(
            self.result.skipped,
            [{"cluster_id": CLIMATE_CLUSTER, "cluster": "Climate control usability", "reason": "description cites no finding of the cluster"}],
        )

    def test_cluster_without_supporting_findings_yields_no_requirement(self):
        clusters = [
            {"id": "c-empty", "label": "Empty", "member_finding_ids": []},
            {"id": "c-missing", "label": "Missing", "member_finding_ids": ["ghost"]},
            {"id": "c-oos", "label": "Out of scope", "members": [finding("x", "Airbag light.", out_of_scope_reason="safety topic")]},
        ]
        draft = {"requirements": [
            {"cluster_id": cid, "title": "T", "description": statement("Customers need something.", "ghost", "x")}
            for cid in ("c-empty", "c-missing", "c-oos")
        ]}
        result = build_result("G60", "US", clusters, draft)
        self.assertEqual(result.requirements, [])
        self.assertEqual({s["cluster_id"] for s in result.skipped}, {"c-empty", "c-missing", "c-oos"})
        self.assertTrue(all(s["reason"] == "cluster has no supporting in-scope findings" for s in result.skipped))
        self.assertEqual([item["finding_id"] for item in result.out_of_scope], ["x"])
        self.assertIn("safety topic", result.summary)

    def test_cluster_without_a_proposed_draft_is_reported(self):
        result = build_result("G60", "US", self.clusters, {"requirements": []})
        self.assertEqual(result.requirements, [])
        self.assertEqual({s["reason"] for s in result.skipped}, {"no draft was proposed for this cluster"})

    def test_assumptions_name_trend_thin_and_model_proposed_evidence(self):
        seat, route = self.result.requirements
        self.assertTrue(any("Target value(s) 80 are proposed by the drafting model" in a for a in seat.assumptions))
        self.assertIn("Model assumption: Survey ratings are a fair proxy for perceived cooling performance.", seat.assumptions)
        self.assertEqual(seat.evidence_level, "Interpreted")  # weakest linked finding (f3)

        self.assertTrue(any(a.startswith("Rests only on market-trend research") and "f4" in a for a in route.assumptions))
        self.assertIn("Thin evidence: a single supporting finding (f4).", route.assumptions)
        self.assertIn("Forward-looking market trend inferred from trade press. (carried over from finding f4)", route.assumptions)

    def test_missing_metric_is_stated_instead_of_invented(self):
        route = self.result.requirements[1]
        self.assertIsNone(route.metric)
        self.assertIn(NO_METRIC, route.uncertainties)
        self.assertIn(f"Metric: {NO_METRIC}", self.result.summary)

    def test_single_source_unverified_and_unused_findings_are_flagged(self):
        cluster = {"id": "c1", "label": "Seats", "members": [
            finding("a", "Seat is too hard.", evidence_level="Unverified"),
            finding("b", "Seat cushion is too short."),
            finding("c", "Headrest rattles."),
        ]}
        draft = {"requirements": [{"cluster_id": "c1", "title": "Seat comfort", "description": statement("Customers need softer, longer seats.", "a", "b"),
                                   "metric": statement("No defensible number in the evidence.", "a")}]}
        requirement = build_result("G60", "US", [cluster], draft).requirements[0]
        self.assertIn("Single source: all 2 supporting findings come from G60_feedback_hackathon.xlsx.", requirement.assumptions)
        self.assertIn("Includes unverified evidence that needs corroboration (a).", requirement.assumptions)
        self.assertEqual(requirement.evidence_level, "Unverified")
        self.assertIn("1 cluster finding(s) are not used by any statement (c).", requirement.uncertainties)
        self.assertFalse(any("Target value" in a for a in requirement.assumptions))

    def test_everything_in_the_result_traces_to_a_cluster_finding(self):
        members = {c["id"]: {m["id"]: m for m in c["members"]} for c in self.clusters}
        for requirement in asdict(self.result)["requirements"]:
            allowed = members[requirement["cluster_id"]]
            statements = [requirement["description"], *requirement["acceptance_criteria"]]
            if requirement["metric"]:
                statements.append(requirement["metric"])
            for item in statements:
                self.assertTrue(item["finding_ids"])
                self.assertEqual([c["finding_id"] for c in item["citations"]], item["finding_ids"])
                for citation in item["citations"]:
                    self.assertEqual(citation["locator"], allowed[citation["finding_id"]]["locator"])
            self.assertTrue(set(requirement["linked_finding_ids"]) <= set(allowed))
            self.assertEqual([c["finding_id"] for c in requirement["citations"]], requirement["linked_finding_ids"])

    def test_summary_has_the_step_summary_sections_with_citations(self):
        summary = self.result.summary
        self.assertTrue(summary.startswith("Requirements Drafting Agent looked at 3 accepted cluster(s) with 5 linked finding(s) for G60 / US"))
        for section in ("Draft requirements:", "Confidence and gaps:", "Out of scope (routed to the side bin, not drafted):"):
            self.assertIn(section, summary)
        self.assertIn("each at status Draft", summary)
        self.assertIn("f3: https://www.caranddriver.com/example-rival-review · retrieved 2026-10-10", summary)
        self.assertIn("f1: G60_feedback_hackathon.xlsx, sheet Feedback_Explorer, row 4642 (G60-3695)", summary)
        self.assertIn("No requirement for cluster 'Climate control usability'", summary)

    def test_chains_from_the_clustering_agent_result(self):
        clustering = build_clusters(
            "G60", "US",
            load_findings(ROOT / "tests/fixtures/clustering_agent_findings.json"),
            load_clustering_draft(ROOT / "tests/fixtures/clustering_agent_draft.json"),
        )
        result = build_result("G60", "US", clustering.clusters, load_drafting_draft(DRAFT))
        self.assertEqual(asdict(result)["requirements"], asdict(self.result)["requirements"])

    def test_resolves_cluster_members_from_a_separate_findings_list(self):
        clusters = [{"id": "c1", "label": "Seats", "domain": "Comfort & Space", "member_finding_ids": ["a", "ghost"]}]
        draft = {"requirements": [{"cluster_id": "c1", "description": statement("Customers need softer seats.", "a")}]}
        requirement = build_result("G60", "US", clusters, draft, findings=[finding("a", "Seat is too hard.")]).requirements[0]
        self.assertEqual(requirement.title, "Seats")  # falls back to the cluster label
        self.assertEqual(requirement.domain_key, "comfort_space")
        self.assertIn("Cluster member(s) without an accepted finding were ignored (ghost).", requirement.uncertainties)

    def test_prompt_lists_clusters_with_their_finding_ids(self):
        prompt = build_drafting_prompt("G60", "US", prepare_clusters(self.clusters[:1]))
        self.assertIn(f"Cluster {SEAT_CLUSTER}", prompt)
        self.assertIn("[f1]", prompt)
        self.assertNotIn("[f4]", prompt)

    def test_store_result_writes_drafts_and_leaves_the_step_awaiting_review(self):
        conn = FakeConn()
        store_result(conn, self.result, run_id="run-1", step_id="step-1")
        sql = [call[0] for call in conn.calls]
        self.assertIn("status = 'awaiting_review'", sql[0])
        inserts = [call for call in conn.calls if "insert into public.requirement (" in call[0]]
        self.assertEqual(len(inserts), 2)
        self.assertEqual(inserts[0][1][11:14], ("draft", "pm_query", "run-1"))
        self.assertEqual(inserts[0][1][3], "dom-comfort")
        self.assertIsNone(inserts[1][1][6])  # no metric stored when none is supported
        self.assertEqual(sum("insert into public.requirement_finding" in s for s in sql), 4)
        self.assertEqual(sum("insert into public.requirement_cluster" in s for s in sql), 2)

    def test_cli_dry_run_works_without_openai_or_database(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.agents.requirements_drafting_agent",
                "--vehicle-line",
                "G60",
                "--market",
                "US",
                "--clusters-json",
                str(CLUSTERS),
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
        self.assertEqual(payload["agent_name"], "Requirements Drafting Agent")
        self.assertEqual(payload["market"], "US")
        self.assertEqual(len(payload["requirements"]), 2)
        self.assertEqual(payload["requirements"][0]["status"], "Draft")
        self.assertEqual(payload["requirements"][0]["cluster_id"], SEAT_CLUSTER)


if __name__ == "__main__":
    unittest.main()
