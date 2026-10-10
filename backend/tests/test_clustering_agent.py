import json
import subprocess
import sys
import unittest
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.clustering_agent import (
    AGENT_NAME,
    DEFAULT_DOMAINS,
    build_clustering_prompt,
    build_result,
    dedupe_findings,
    load_clustering_draft,
    load_findings,
    normalize_findings,
    out_of_scope_reason,
    resolve_domain,
    rules_draft,
    store_result,
)

FINDINGS = ROOT / "tests/fixtures/clustering_agent_findings.json"
DRAFT = ROOT / "tests/fixtures/clustering_agent_draft.json"


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
            return FakeCursor([("comfort_space", "dom-comfort"), ("usability", "dom-usability")])
        return FakeCursor([("step-1",)])


def finding(fid, text, **extra):
    base = {
        "id": fid,
        "text": text,
        "signal_type": "complaint",
        "evidence_level": "Verified",
        "locator": f"sheet Feedback_Explorer, row {fid}",
        "market": "US",
        "vehicle_line": "G60",
        "out_of_scope_reason": None,
    }
    return base | extra


class ClusteringAgentTest(unittest.TestCase):
    def setUp(self):
        self.findings = load_findings(FINDINGS)
        self.result = build_result("G60", "US", self.findings, load_clustering_draft(DRAFT))

    def test_groups_findings_and_validates_the_model_draft(self):
        result = self.result
        self.assertEqual(result.agent_name, AGENT_NAME)
        self.assertEqual(result.findings_read, 9)
        self.assertEqual([c.label for c in result.clusters], ["Seat ventilation and cooling", "Charging-aware route planning", "Climate control usability"])
        self.assertEqual(result.clusters[0].member_finding_ids, ["f1", "f2", "f3"])
        self.assertEqual(result.clusters[1].member_finding_ids, ["f4"])

        reasons = {(d.get("finding_id"), d["reason"]) for d in result.dropped}
        self.assertIn(("f404", "unknown finding id"), reasons)
        self.assertIn(("f6", "finding is a duplicate"), reasons)
        self.assertIn(("f7", "finding is out of scope"), reasons)
        self.assertIn(("f1", "already assigned to cluster 'Seat ventilation and cooling'"), reasons)
        self.assertNotIn("Pricing pressure", [c.label for c in result.clusters])

    def test_each_finding_is_in_at_most_one_cluster(self):
        member_ids = [fid for c in self.result.clusters for fid in c.member_finding_ids]
        self.assertEqual(len(member_ids), len(set(member_ids)))

    def test_maps_clusters_onto_the_taxonomy(self):
        seat, route, climate = self.result.clusters
        self.assertEqual((seat.domain_key, seat.domain_label, seat.domain_source), ("comfort_space", "Comfort & Space", "findings"))
        self.assertEqual((route.domain_key, route.domain_source), ("infotainment", "model"))
        # the model's made-up domain is ignored; the finding's own domain decides
        self.assertEqual((climate.domain_key, climate.domain_source), ("usability", "findings"))
        self.assertEqual(seat.independent_sources, 2)
        self.assertEqual(seat.input_families, ["feedback", "website"])

    def test_unknown_domain_stays_unmapped_and_live_taxonomy_ids_are_kept(self):
        domains = [{"id": "11111111-1111-1111-1111-111111111111", "key": "comfort_space", "label": "Comfort & Space"}]
        findings = [finding("a", "Seat is too hard."), finding("b", "Menu is confusing.")]
        draft = {"clusters": [
            {"label": "Seats", "domain": "Comfort & Space", "finding_ids": ["a"]},
            {"label": "Menus", "domain": "nonsense", "finding_ids": ["b"]},
        ]}
        seats, menus = build_result("G60", "US", findings, draft, domains).clusters
        self.assertEqual(seats.ontology_domain_id, "11111111-1111-1111-1111-111111111111")
        self.assertIsNone(menus.domain_key)
        self.assertEqual(menus.domain_source, "unmapped")

    def test_removes_duplicates_and_keeps_distinct_locators(self):
        self.assertEqual([(d["finding_id"], d["duplicate_of"]) for d in self.result.duplicates], [("f6", "f1")])
        same_text_other_row = [finding("a", "Seat is too hard."), finding("b", "Seat is too hard.")]
        unique, duplicates = dedupe_findings(normalize_findings(same_text_other_row)[0])
        self.assertEqual(len(unique), 2)
        self.assertEqual(duplicates, [])

    def test_out_of_scope_findings_are_excluded_and_listed(self):
        by_id = {item["finding_id"]: item for item in self.result.out_of_scope}
        self.assertEqual(set(by_id), {"f7", "f8"})
        self.assertEqual(by_id["f7"]["flagged_by"], AGENT_NAME)
        self.assertEqual(by_id["f8"]["flagged_by"], "upstream")
        clustered = {fid for c in self.result.clusters for fid in c.member_finding_ids}
        self.assertFalse(clustered & {"f7", "f8"})

    def test_guardrail_does_not_catch_everyday_customer_wording(self):
        ok, _ = normalize_findings([finding("a", "The seats are fine, but for the price I expected ventilation.")])
        self.assertIsNone(out_of_scope_reason(ok[0], DEFAULT_DOMAINS))
        bad, _ = normalize_findings([finding("b", "Type approval rules will change."), finding("c", "Airbag light.", domain="safety")])
        self.assertTrue(all(out_of_scope_reason(f, DEFAULT_DOMAINS) for f in bad))

    def test_cluster_mapped_to_an_out_of_scope_domain_goes_to_the_bin(self):
        draft = {"clusters": [{"label": "Belts", "domain": "Safety", "finding_ids": ["a"]}]}
        result = build_result("G60", "US", [finding("a", "Seat belt is hard to reach.")], draft)
        self.assertEqual(result.clusters, [])
        self.assertEqual([item["finding_id"] for item in result.out_of_scope], ["a"])
        self.assertEqual(result.unassigned, [])

    def test_unassigned_findings_are_reported(self):
        self.assertEqual([item["finding_id"] for item in self.result.unassigned], ["f9"])
        self.assertIn("praise for the design", self.result.unassigned[0]["reason"])
        no_model_output = build_result("G60", "US", self.findings, {})
        self.assertEqual(no_model_output.clusters, [])
        self.assertEqual({item["finding_id"] for item in no_model_output.unassigned}, {"f1", "f2", "f3", "f4", "f5", "f9"})

    def test_uncitable_findings_are_dropped(self):
        result = build_result("G60", "US", [finding("a", "Seat is too hard.", locator=""), finding("b", "")], {"clusters": [{"label": "Seats", "finding_ids": ["a", "b"]}]})
        self.assertEqual(result.clusters, [])
        self.assertIn({"finding_id": "a", "reason": "finding has no locator and cannot be cited"}, result.dropped)

    def test_everything_in_the_result_traces_to_an_input_finding(self):
        payload = asdict(self.result)
        input_ids = {f["id"] for f in self.findings}
        input_locators = {f["locator"] for f in self.findings}
        input_texts = {f["text"] for f in self.findings}
        for cluster in payload["clusters"]:
            self.assertTrue(cluster["member_finding_ids"])
            self.assertEqual([c["finding_id"] for c in cluster["citations"]], cluster["member_finding_ids"])
            for citation in cluster["citations"]:
                self.assertIn(citation["finding_id"], input_ids)
                self.assertIn(citation["locator"], input_locators)
            for member in cluster["members"]:
                self.assertIn(member["text"], input_texts)
        for bin_name in ("unassigned", "out_of_scope", "duplicates"):
            for item in payload[bin_name]:
                self.assertIn(item["finding_id"], input_ids)
                self.assertIn(item["locator"], input_locators)

    def test_summary_has_the_step_summary_sections_with_citations(self):
        summary = self.result.summary
        self.assertTrue(summary.startswith("Clustering Agent looked at 9 accepted finding(s) for G60 / US"))
        for section in ("Clusters:", "Confidence and gaps:", "Out of scope (routed to the side bin, not clustered):"):
            self.assertIn(section, summary)
        for cluster in self.result.clusters:
            for member in cluster.members:
                self.assertIn(member.locator, summary)
        self.assertIn("Only market-trend evidence", summary)
        self.assertIn("Unassigned: Owners praise the exterior design", summary)
        self.assertIn("Price incentives are becoming decisive", summary)

    def test_accepts_another_agents_result_without_finding_ids(self):
        upstream = {"findings": [
            {"source_url": "https://example.com/a", "locator": "https://example.com/a · retrieved 2026-10-10", "text": "Buyers expect voice control.",
             "signal_type": "market_trend", "evidence_level": "Interpreted", "market": "US", "vehicle_line": "G60", "out_of_scope_reason": None},
        ]}
        normalized, _ = normalize_findings(upstream["findings"])
        result = build_result("G60", "US", upstream["findings"], {"clusters": [{"label": "Voice control", "domain": "infotainment", "finding_ids": [normalized[0].id]}]})
        self.assertEqual(result.clusters[0].citations[0]["source"], "https://example.com/a")

    def test_rules_draft_groups_by_the_domain_findings_carry(self):
        result = build_result("G60", "US", self.findings, rules_draft(self.findings))
        self.assertEqual({c.domain_key: c.member_finding_ids for c in result.clusters},
                         {"comfort_space": ["f1", "f2"], "usability": ["f5"], "exterior": ["f9"]})
        self.assertEqual({item["finding_id"] for item in result.unassigned}, {"f3", "f4"})

    def test_prompt_shows_only_given_ids_and_the_taxonomy(self):
        normalized, _ = normalize_findings(self.findings[:2])
        prompt = build_clustering_prompt("G60", "US", normalized, DEFAULT_DOMAINS)
        self.assertIn("[f1]", prompt)
        self.assertIn("- comfort_space: Comfort & Space", prompt)
        self.assertNotIn("[f3]", prompt)

    def test_default_domains_match_the_seeded_ontology(self):
        try:
            from app.ingest.seed_ontology import DOMAINS
        except ModuleNotFoundError:
            self.skipTest("seed_ontology dependencies not installed")
        self.assertEqual({d["key"]: d["label"] for d in DEFAULT_DOMAINS}, DOMAINS)
        self.assertEqual(resolve_domain("Safety", DEFAULT_DOMAINS)["key"], "safety")

    def test_store_result_writes_clusters_and_leaves_the_step_awaiting_review(self):
        conn = FakeConn()
        store_result(conn, self.result, run_id=None, step_id="step-1")
        sql = [call[0] for call in conn.calls]
        self.assertIn("status = 'awaiting_review'", sql[0])
        self.assertEqual(sum("insert into public.cluster (" in s for s in sql), 3)
        self.assertEqual(sum("insert into public.cluster_finding" in s for s in sql), 5)
        cluster_insert = next(call for call in conn.calls if "insert into public.cluster (" in call[0])
        self.assertEqual(cluster_insert[1][2], "dom-comfort")
        flagged = [call[1] for call in conn.calls if "set out_of_scope_reason" in call[0]]
        self.assertEqual([params[1] for params in flagged], ["f7"])
        self.assertFalse(any("accepted" in s or "rejected" in s for s in sql))

    def test_cli_dry_run_works_without_openai_or_database(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.agents.clustering_agent",
                "--vehicle-line",
                "G60",
                "--market",
                "US",
                "--findings-json",
                str(FINDINGS),
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
        self.assertEqual(payload["agent_name"], "Clustering Agent")
        self.assertEqual(payload["vehicle_line"], "G60")
        self.assertEqual(len(payload["clusters"]), 3)
        self.assertEqual(payload["clusters"][0]["citations"][0]["locator"], "sheet Feedback_Explorer, row 4642 (G60-3695)")


if __name__ == "__main__":
    unittest.main()
