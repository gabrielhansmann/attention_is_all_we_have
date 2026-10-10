import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.critic_agent import (
    audit_events,
    check_locator,
    drop_unsupported,
    review,
    review_with_retries,
)
from app.agents.market_trend_agent import build_result, load_market_trend_draft, load_seed_sources

WEB_LOCATOR = "https://www.caranddriver.com/example-premium-sedan-trends · retrieved 2026-10-10"
FILE_LOCATOR = "sheet Feedback_Explorer, row 4642 (G60-3695)"


def web_finding(**overrides):
    finding = {
        "text": "Premium sedan buyers increasingly expect charging-aware route planning.",
        "signal_type": "market_trend",
        "evidence_level": "Interpreted",
        "source_url": "https://www.caranddriver.com/example-premium-sedan-trends",
        "retrieved_at": "2026-10-10T08:00:00+00:00",
        "locator": WEB_LOCATOR,
        "trust_tier": "trade_press",
        "assumptions": ["Forward-looking."],
        "out_of_scope_reason": None,
    }
    finding.update(overrides)
    return finding


def file_finding(**overrides):
    finding = {
        "id": "F-1",
        "text": "Customers report that seat ventilation is too weak on long drives.",
        "signal_type": "complaint",
        "evidence_level": "Verified",
        "file": "G60_feedback_hackathon.xlsx",
        "locator": FILE_LOCATOR,
        "sample_size": 37,
        "assumptions": [],
        "out_of_scope_reason": None,
    }
    finding.update(overrides)
    return finding


def output(findings, summary=None, **extra):
    if summary is None:
        bullets = [f"- {f['text']} ({f.get('evidence_level')}; {f.get('locator') or ''})" for f in findings]
        summary = "\n".join(["Agent looked at 2 sources for G60 / US.", "", "Findings:", *bullets, "", "Confidence and gaps:", "- Thin on rear seats."])
    return {"agent_name": "Test Agent", "vehicle_line": "G60", "market": "US", "summary": summary, "findings": findings, **extra}


class CriticAgentTest(unittest.TestCase):
    def test_clean_output_passes_and_input_is_not_mutated(self):
        result = output([web_finding(), file_finding()])
        before = copy.deepcopy(result)

        verdict = review(result)

        self.assertTrue(verdict.passed)
        self.assertEqual(verdict.issues, [])
        self.assertEqual(verdict.downgrades, [])
        self.assertEqual(verdict.retry_instruction, "")
        self.assertEqual(verdict.output, before)
        self.assertEqual(result, before)
        self.assertEqual(verdict.agent_name, "Test Agent")

    def test_locator_shapes(self):
        self.assertIsNone(check_locator(WEB_LOCATOR).problem)
        self.assertIsNone(check_locator("https://example.com/a", retrieved_at="2026-10-10T08:00:00+00:00").problem)
        self.assertIsNone(check_locator("page 14", file="G60_catalog.pdf").problem)
        self.assertIsNone(check_locator("G60_catalog.pdf, page 14").problem)
        self.assertIsNone(check_locator({"file": "sales_volumes.xlsx", "sheet": "Sales", "row": 7}).problem)
        self.assertEqual(check_locator("page 14").problem, "locator names no source file or URL")
        self.assertEqual(check_locator("G60_catalog.pdf").problem, "locator has no page/sheet/row position")
        self.assertEqual(check_locator("https://example.com/2026-01-02/a").problem, "web locator has no retrieval date")
        self.assertEqual(check_locator("https://example.com/a · retrieved 2026-13-40").problem, "retrieval date is not a valid date")
        self.assertEqual(check_locator("  ").problem, "locator is missing")

    def test_missing_locator_fails_with_retry_instruction(self):
        verdict = review(output([web_finding(), file_finding(locator="", text="Rear legroom is the top complaint.")]))

        self.assertFalse(verdict.passed)
        codes = {(i.item, i.code) for i in verdict.issues if i.severity == "error"}
        self.assertIn(("findings[1]", "missing_locator"), codes)
        self.assertIn("find a citation or drop the claim", verdict.retry_instruction)
        self.assertIn("Rear legroom is the top complaint.", verdict.retry_instruction)
        self.assertIn("findings[1]", verdict.retry_instruction)
        self.assertNotIn("findings[0]", verdict.retry_instruction)

    def test_web_locator_without_retrieval_date_fails(self):
        finding = web_finding(locator="https://www.caranddriver.com/example-premium-sedan-trends", retrieved_at=None)

        verdict = review(output([finding], summary="Findings:\n- none"))

        self.assertFalse(verdict.passed)
        self.assertEqual([(i.code, i.message) for i in verdict.issues], [("malformed_locator", "web locator has no retrieval date")])

    def test_thin_evidence_is_downgraded_not_failed(self):
        forum = web_finding(text="Owners complain about climate menus.", trust_tier="forum_social", evidence_level="Interpreted",
                            source_url="https://forum.example/t/1", locator="https://forum.example/t/1 · retrieved 2026-10-10")
        single = web_finding(text="The brand says voice control is now the default.", trust_tier="oem", evidence_level="Verified")
        corroborated = web_finding(text="Two sources agree on route planning.", trust_tier="oem", evidence_level="Verified",
                                   corroborated_by=["https://example.org/b · retrieved 2026-10-09"])
        result = output([forum, single, corroborated, file_finding()])

        verdict = review(result)

        self.assertTrue(verdict.passed)
        self.assertEqual(
            [(d.item, d.from_level, d.to_level) for d in verdict.downgrades],
            [("findings[0]", "Interpreted", "Unverified"), ("findings[1]", "Verified", "Interpreted")],
        )
        self.assertIn("forum_social", verdict.downgrades[0].reason)
        self.assertIn("single web source", verdict.downgrades[1].reason)
        self.assertEqual([f["evidence_level"] for f in verdict.output["findings"]], ["Unverified", "Interpreted", "Verified", "Verified"])
        self.assertEqual(result["findings"][0]["evidence_level"], "Interpreted")
        self.assertIn("(Unverified; https://forum.example/t/1", verdict.output["summary"])
        self.assertIn("Critic review:", verdict.output["summary"])
        self.assertEqual([e["action"] for e in audit_events(verdict)], ["evidence_level_downgraded"] * 2)
        # Reviewing the adjusted output again changes nothing.
        again = review(verdict.output)
        self.assertTrue(again.passed)
        self.assertEqual(again.downgrades, [])

    def test_summary_bullet_without_citation_fails(self):
        summary = "Findings:\n- Buyers want bigger screens.\n- Voice control is spreading (see https://example.com/a)\n\nConfidence and gaps:\n- Small sample."

        verdict = review(output([web_finding()], summary=summary))

        self.assertFalse(verdict.passed)
        self.assertEqual(
            [(i.item, i.message) for i in verdict.issues],
            [("summary line 2", "bullet carries no citation (source + locator)"), ("summary line 3", "bullet cites a URL without a retrieval date")],
        )

    def test_nested_summary_bullets_are_covered_by_their_cited_children(self):
        summary = "\n".join([
            "Draft requirements:",
            "- Stronger seat ventilation [Comfort & Space]",
            f"  - Description: Seat ventilation is too weak. (F-1: G60_feedback_hackathon.xlsx, {FILE_LOCATOR})",
            "  - Assumption: Survey ratings are a fair proxy for cooling performance.",
            "  - Metric: No defensible metric could be tied to the cited findings.",
            "- Quieter cabin [Comfort & Space]",
            "  - Description: Owners want less wind noise.",
        ])

        verdict = review(output([file_finding()], summary=summary))

        self.assertEqual([i.item for i in verdict.issues], ["summary line 6", "summary line 7"])

    def test_synthesis_fixture_passes_and_is_capped_by_its_evidence(self):
        fixture = json.loads((ROOT / "tests/fixtures/critic_clustering_output.json").read_text(encoding="utf-8"))

        verdict = review(fixture["output"], known_findings=fixture["known_findings"])

        self.assertTrue(verdict.passed, verdict.issues)
        self.assertEqual(verdict.downgrades, [])
        # Without the accepted findings the same references cannot be resolved.
        self.assertFalse(review(fixture["output"]).passed)

        weak = copy.deepcopy(fixture)
        weak["output"]["clusters"][0].update(member_finding_ids=["F-102"], locators=[])
        verdict = review(weak["output"], known_findings=weak["known_findings"])
        self.assertTrue(verdict.passed)
        self.assertEqual([(d.item, d.from_level, d.to_level) for d in verdict.downgrades], [("clusters[0]", "Verified", "Interpreted")])

    def test_synthesis_item_citing_unknown_finding_fails(self):
        requirements = [
            {"id": "R-1", "title": "Stronger seat ventilation", "evidence_level": "Verified", "linked_finding_ids": ["F-1", "F-999"]},
            {"id": "R-2", "title": "Quieter cabin", "linked_finding_ids": []},
        ]

        verdict = review(output([file_finding()], requirements=requirements))

        self.assertFalse(verdict.passed)
        self.assertEqual(
            [(i.item, i.code, i.item_id) for i in verdict.issues],
            [("requirements[0]", "unknown_finding", "R-1"), ("requirements[1]", "no_evidence", "R-2")],
        )
        self.assertIn("F-999", verdict.retry_instruction)

    def test_retry_runner_succeeds_on_second_attempt(self):
        calls = []

        def run_agent(instruction):
            calls.append(instruction)
            if instruction is None:
                return output([file_finding(locator=None)])
            return output([file_finding()])

        verdict = review_with_retries(run_agent, max_retries=2)

        self.assertTrue(verdict.passed)
        self.assertEqual(verdict.attempts, 2)
        self.assertFalse(verdict.retries_exhausted)
        self.assertEqual(verdict.dropped, [])
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0])
        self.assertIn("find a citation or drop the claim", calls[1])

    def test_retry_budget_exhausted_drops_the_claim(self):
        calls = []
        bad = file_finding(id="F-2", text="Rear legroom is the top complaint.", locator=None)
        clusters = [
            {"id": "C-1", "label": "Seat ventilation", "member_finding_ids": ["F-1", "F-2"]},
            {"id": "C-2", "label": "Rear legroom", "member_finding_ids": ["F-2"]},
        ]

        def run_agent(instruction):
            calls.append(instruction)
            return output([file_finding(), bad], clusters=clusters)

        verdict = review_with_retries(run_agent, max_retries=1)

        self.assertEqual(len(calls), 2)
        self.assertEqual(verdict.attempts, 2)
        self.assertTrue(verdict.retries_exhausted)
        self.assertTrue(verdict.passed)
        self.assertIn("dropped", verdict.note)
        self.assertEqual([f["id"] for f in verdict.output["findings"]], ["F-1"])
        # The cluster that only rested on the dropped finding goes too; the other keeps its good member.
        self.assertEqual([(c["id"], c["member_finding_ids"]) for c in verdict.output["clusters"]], [("C-1", ["F-1"])])
        self.assertEqual([c.text for c in verdict.dropped], ["Rear legroom is the top complaint.", "Rear legroom is the top complaint. (Verified; )", "Rear legroom"])
        self.assertNotIn("- Rear legroom is the top complaint. (", verdict.output["summary"])
        self.assertIn("Dropped after 2 attempt(s)", verdict.output["summary"])
        self.assertIn("claim_dropped", [e["action"] for e in audit_events(verdict)])
        self.assertTrue(review(verdict.output).passed)

    def test_drop_unsupported_leaves_the_failed_verdict_untouched(self):
        failed = review(output([file_finding(locator=None)]))

        final = drop_unsupported(failed)

        self.assertFalse(failed.passed)
        self.assertEqual(len(failed.original["findings"]), 1)
        self.assertTrue(final.passed)
        self.assertEqual(final.output["findings"], [])

    def test_optional_support_check_only_downgrades(self):
        finding = web_finding(evidence_level="Interpreted", snapshot="Buyers expect route planning with charging stops.")
        seen = []

        def doubts(claim, snapshot, locator):
            seen.append((claim, snapshot, locator))
            return {"supported": False, "reason": "snapshot does not mention this"}

        def broken(claim, snapshot, locator):
            raise RuntimeError("model unavailable")

        self.assertEqual(review(output([finding])).downgrades, [])

        verdict = review(output([finding]), support_check=doubts)
        self.assertTrue(verdict.passed)
        self.assertEqual(seen, [(finding["text"], finding["snapshot"], WEB_LOCATOR)])
        self.assertEqual(verdict.output["findings"][0]["evidence_level"], "Unverified")
        self.assertEqual([i.code for i in verdict.issues], ["support_doubted"])

        for check in (broken, lambda *_: "probably fine", lambda *_: True):
            verdict = review(output([finding]), support_check=check)
            self.assertTrue(verdict.passed)
            self.assertEqual(verdict.downgrades, [])

    def test_market_trend_result_passes_the_critic(self):
        docs = load_seed_sources(ROOT / "tests/fixtures/market_trend_sources.json")
        draft = load_market_trend_draft(ROOT / "tests/fixtures/market_trend_draft.json")
        result = build_result("G60", "US", "comfort trends", docs, draft)

        verdict = review(result)

        self.assertTrue(verdict.passed, verdict.issues)
        self.assertEqual(verdict.agent_name, "Market & Trend Agent")
        self.assertEqual(verdict.downgrades, [])
        self.assertEqual([f["evidence_level"] for f in verdict.output["findings"]], ["Interpreted", "Unverified"])
        self.assertEqual(verdict.output["summary"], result.summary)
        json.dumps(verdict.to_dict())


if __name__ == "__main__":
    unittest.main()
