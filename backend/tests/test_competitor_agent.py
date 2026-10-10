import json
import subprocess
import sys
import unittest
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.competitor_agent import (
    AGENT_NAME,
    build_result,
    load_competitor_draft,
    parse_band,
    research_with_openai,
    store_result,
)
from app.agents.market_trend_agent import SourceDoc, load_seed_sources

SOURCES = ROOT / "tests/fixtures/competitor_sources.json"
DRAFT = ROOT / "tests/fixtures/competitor_draft.json"
ANCHOR = "BMW 5 Series (G60) i5 eDrive40"
EQE = "Mercedes-Benz EQE 350+"


def fixture_result(**options):
    return build_result("G60", "EU", "seat comfort and range vs rivals", load_seed_sources(SOURCES), load_competitor_draft(DRAFT), **options)


def cell(result, rival, aspect, source_type="spec"):
    return next(c for c in result.comparison if (c.rival, c.aspect, c.source_type) == (rival, aspect, source_type))


class CompetitorAgentTest(unittest.TestCase):
    def test_anchor_identity_comes_from_scope_and_values_are_cited(self):
        result = fixture_result()

        self.assertEqual(result.anchor.label, ANCHOR)
        self.assertTrue(result.anchor.is_anchor)
        self.assertEqual(result.anchor.get("price"), 70200)
        for attribute in result.anchor.attributes:
            self.assertIn("bmw.de", attribute.source_url)
            self.assertIn("retrieved", attribute.locator)
            self.assertEqual(attribute.trust_tier, "oem")

    def test_default_bands_are_derived_from_the_anchor(self):
        criteria = {c.attribute: c for c in fixture_result().segment.criteria}

        self.assertEqual((criteria["price"].min, criteria["price"].max, criteria["price"].kind), (59670, 87750, "hard"))
        self.assertEqual(criteria["body_style"].equals, "saloon/estate")
        self.assertEqual((criteria["seats"].equals, criteria["seats"].kind), (5.0, "hard"))
        self.assertEqual(criteria["powertrain"].kind, "soft")
        self.assertEqual((criteria["range"].min, criteria["range"].max), (464, 696))
        self.assertEqual((criteria["length"].min, criteria["length"].max), (4807, 5313))
        self.assertTrue(all(c.set_by == "default" for c in criteria.values()))

    def test_long_list_filters_dedupes_and_never_passes_a_missing_value_silently(self):
        result = fixture_result()
        by_label = {c.profile.label: c for c in result.long_list}

        self.assertEqual(set(by_label), {EQE, "Audi A6 e-tron Sportback", "Tesla Model S", "NIO ET7"})
        self.assertEqual(by_label[EQE].profile.get("price"), 67000)  # the duplicate entry did not replace it
        self.assertEqual(by_label["Tesla Model S"].status, "excluded")
        self.assertIn("price outside the band", by_label["Tesla Model S"].reasons[0])
        self.assertFalse(by_label["Tesla Model S"].shortlisted)
        self.assertEqual(by_label["NIO ET7"].unknown_attributes, ["price"])
        self.assertTrue(by_label["NIO ET7"].needs_pm_check)
        self.assertTrue(any("Ghost Car: no cited attribute" in s["reason"] for s in result.skipped))
        self.assertGreater(by_label[EQE].similarity, by_label["Audi A6 e-tron Sportback"].similarity)
        self.assertTrue(all(0 <= c.similarity <= 1 for c in result.long_list))

        self.assertEqual(result.competitor_set.selected_by, "similarity")
        self.assertEqual(set(result.competitor_set.rivals), {EQE, "Audi A6 e-tron Sportback", "NIO ET7"})
        # an unchecked hard criterion ranks after verified candidates
        self.assertEqual(fixture_result(max_rivals=2).competitor_set.rivals, [EQE, "Audi A6 e-tron Sportback"])

    def test_pm_can_override_bands_and_pick_rivals(self):
        self.assertEqual(parse_band("price=60000:100000"), ("price", {"min": 60000.0, "max": 100000.0}))
        self.assertEqual(parse_band("powertrain=BEV"), ("powertrain", {"equals": "BEV", "kind": "hard"}))
        with self.assertRaises(ValueError):
            parse_band("price")

        widened = fixture_result(band_overrides=dict([parse_band("price=60000:100000")]))
        price = next(c for c in widened.segment.criteria if c.attribute == "price")
        self.assertEqual((price.min, price.max, price.set_by), (60000.0, 100000.0, "pm"))
        self.assertIn("Tesla Model S", widened.competitor_set.rivals)

        picked = fixture_result(rivals=["Tesla Model S", "Polestar 5"])
        self.assertEqual(picked.competitor_set.selected_by, "pm")
        self.assertEqual(set(picked.competitor_set.rivals), {"Tesla Model S", "Polestar 5"})
        tesla_range = next(f for f in picked.findings if f.rival == "Tesla Model S" and f.aspect == "range")
        self.assertIn("634 vs 580 km WLTP, +9.3%", tesla_range.text)

        hard = fixture_result(hard_powertrain=True)
        self.assertEqual(next(c for c in hard.segment.criteria if c.attribute == "powertrain").kind, "hard")

    def test_spec_comparison_is_computed_in_code_and_like_with_like(self):
        result = fixture_result()

        rng = cell(result, EQE, "range")
        self.assertEqual((rng.anchor_value, rng.rival_value, rng.delta, rng.status), (580, 620, 40.0, "rival_leads"))
        self.assertEqual(rng.evidence_level, "Verified")
        self.assertEqual(cell(result, EQE, "charging_time").status, "anchor_leads")
        self.assertEqual(cell(result, EQE, "rear_axle_steering").status, "rival_leads")
        self.assertEqual(cell(result, EQE, "length").status, "direction_unknown")
        self.assertEqual(cell(result, "NIO ET7", "range").status, "parity")
        consumption = cell(result, "Audi A6 e-tron Sportback", "consumption")
        self.assertEqual(consumption.status, "not_comparable")
        self.assertIn("EPA vs WLTP", consumption.note)

        finding = next(f for f in result.findings if (f.rival, f.aspect) == (EQE, "range"))
        self.assertEqual(finding.text, f"{EQE} is ahead of {ANCHOR} on range: 620 vs 580 km WLTP, +6.9%.")
        self.assertEqual(finding.signal_type, "competitor_advantage")
        self.assertEqual((finding.evidence_level, finding.trust_tier), ("Verified", "oem"))
        self.assertEqual(finding.source_url, "https://www.mercedes-benz.de/example/eqe-350-plus")
        self.assertTrue(finding.locator.startswith("https://www.mercedes-benz.de/example/eqe-350-plus · retrieved "))
        self.assertEqual([c["side"] for c in finding.citations], ["rival", "anchor"])
        # the 900 km claim cited a source that does not exist and never reached a cell
        self.assertFalse(any("900" in f.text for f in result.findings))

    def test_voice_comparison_is_relative_and_thin_evidence_is_not_a_finding(self):
        result = fixture_result()

        seats = cell(result, EQE, "seat_comfort", "expert")
        self.assertEqual((seats.n_anchor, seats.n_rival), (3, 3))
        self.assertEqual(seats.rival_value, {"n": 3, "share_pct": 100.0, "sentiment_balance": 0.7})
        self.assertEqual(seats.anchor_value["sentiment_balance"], 0.1)
        self.assertEqual((seats.delta, seats.status, seats.evidence_level), (0.6, "rival_leads", "Interpreted"))
        finding = next(f for f in result.findings if f.aspect == "seat_comfort")
        self.assertTrue(finding.text.startswith(f"Expert reviews rate {EQE} better than {ANCHOR} on seat comfort"))
        self.assertEqual((finding.trust_tier, finding.sample_size, finding.sentiment), ("trade_press", 3, 0.7))
        self.assertTrue(any("model-extracted" in a for a in finding.assumptions))

        thin = cell(result, EQE, "infotainment_responsiveness", "owner")
        self.assertEqual((thin.status, thin.evidence_level), ("insufficient_data", "Unverified"))
        self.assertFalse(any(f.aspect == "infotainment_responsiveness" for f in result.findings))
        relaxed = fixture_result(min_mentions=1)
        owner = next(f for f in relaxed.findings if f.aspect == "infotainment_responsiveness")
        self.assertEqual((owner.evidence_level, owner.trust_tier), ("Unverified", "forum_social"))

        # a manufacturer's own praise is not a review, a vehicle outside the set is not compared
        reasons = " | ".join(s["reason"] for s in result.skipped)
        self.assertIn("ride_comfort: neither a spec value nor a review or owner judgement", reasons)
        self.assertIn("Tesla Model S is outside the rival set", reasons)
        self.assertIn("invalid source_index", reasons)

    def test_only_rival_leads_becomes_a_finding_and_pricing_goes_to_the_bin(self):
        result = fixture_result()

        self.assertEqual({(f.rival, f.aspect) for f in result.findings},
                         {(c.rival, c.aspect) for c in result.comparison if c.status == "rival_leads"})
        self.assertTrue(all(f.signal_type == "competitor_advantage" for f in result.findings))
        out = [f for f in result.findings if f.out_of_scope_reason]
        self.assertEqual([(f.rival, f.aspect) for f in out], [(EQE, "price")])
        self.assertFalse(any(c.aspect in {"body_style", "seats", "powertrain", "equipment"} for c in result.comparison))

    def test_every_finding_has_a_citation_from_the_source_list(self):
        docs = load_seed_sources(SOURCES)
        urls = {doc.url for doc in docs}
        result = fixture_result()

        self.assertTrue(result.findings)
        for finding in result.findings:
            self.assertIn(finding.source_url, urls)
            self.assertIn(finding.source_url, finding.locator)
            self.assertIn("retrieved", finding.locator)
            self.assertTrue(all(c["url"] in urls for c in finding.citations))

        no_sources = build_result("G60", "EU", "q", [], load_competitor_draft(DRAFT))
        self.assertEqual(no_sources.findings, [])
        self.assertEqual(no_sources.long_list, [])

    def test_scope_all_and_missing_anchor(self):
        docs, draft = load_seed_sources(SOURCES), load_competitor_draft(DRAFT)

        any_market = build_result("G60", None, "q", docs, draft)
        self.assertEqual(any_market.market, "ALL")
        self.assertIn("one global rival list", any_market.summary)
        self.assertTrue(any_market.findings)

        no_anchor = build_result("ALL", "EU", "q", docs, {"candidates": draft["candidates"], "observations": draft["observations"]})
        self.assertEqual((no_anchor.vehicle_line, no_anchor.findings, no_anchor.anchor), ("ALL", [], None))
        self.assertIn("needs one anchor vehicle", no_anchor.summary)

        named = build_result("ALL", "EU", "q", docs, draft, anchor="BMW i5", anchor_variant="eDrive40")
        self.assertEqual(named.anchor.label, "BMW i5 eDrive40")
        self.assertTrue(named.findings)

    def test_summary_and_result_shape(self):
        result = fixture_result()
        summary = result.summary

        self.assertTrue(summary.startswith(f"{AGENT_NAME} looked at 8 web sources (5 oem, 2 trade_press, 1 forum_social) for G60 / EU"))
        for section in ("Anchor:", "Segment bands", "Rival set: 3 of 4", "Findings:", "Out-of-scope bin", "Compared without a finding:",
                        "Confidence and gaps:"):
            self.assertIn(section, summary)
        self.assertIn("- price 59,670 to 87,750 [hard, default]", summary)
        self.assertIn("not carried forward: Tesla Model S (price outside the band (92,990))", summary)
        self.assertIn("NIO ET7 (similarity 0.83; not checked: price)", summary)
        self.assertIn("+6.9%. (Verified; oem; rival: https://www.mercedes-benz.de/example/eqe-350-plus · retrieved", summary)
        self.assertIn("insufficient data: fewer than 3 mentions", summary)
        self.assertIn("waits for PM review", summary)

        payload = asdict(result)
        self.assertEqual(payload["agent_name"], "Competitor Agent")
        json.dumps(payload)
        for finding in payload["findings"]:
            for key in ("text", "signal_type", "evidence_level", "locator", "market", "vehicle_line", "assumptions",
                        "out_of_scope_reason", "trust_tier"):
                self.assertIn(key, finding)
            self.assertEqual((finding["market"], finding["vehicle_line"]), ("EU", "G60"))

    def test_live_path_builds_sources_from_citation_annotations_only(self):
        def search_response(url, title, line):
            text = f"- {line} ([src]({url}?utm_source=openai))"
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text, "annotations": [
                {"type": "url_citation", "url": f"{url}?utm_source=openai", "title": title,
                 "start_index": text.index("(["), "end_index": len(text)}]}]}]}

        searches = [
            search_response("https://www.bmw.de/i5", "BMW i5", "BMW i5: 580 km WLTP, 70,200 EUR; rival Mercedes EQE: 620 km WLTP, 67,000 EUR"),
            search_response("https://www.bmw.de/i5-range", "BMW i5 range", "i5 range 580 km WLTP"),
            search_response("https://www.mercedes-benz.de/eqe", "EQE", "EQE range 620 km WLTP"),
        ]
        profile_draft = {
            "anchor": {"attributes": [{"attribute": "price", "value": 70200, "unit": "EUR", "source_index": 1},
                                      {"attribute": "range", "value": 580, "unit": "km", "standard": "WLTP", "source_index": 1}]},
            "candidates": [{"make": "Mercedes-Benz", "model": "EQE", "attributes": [
                {"attribute": "price", "value": 67000, "unit": "EUR", "source_index": 1},
                {"attribute": "range", "value": 620, "unit": "km", "standard": "WLTP", "source_index": 1}]}],
        }
        observation_draft = {"observations": [
            {"vehicle": "anchor", "aspect": "boot_volume", "source_index": 2, "value": 490, "unit": "l", "text": "490 l"},
            {"vehicle": "Mercedes-Benz EQE", "aspect": "boot_volume", "source_index": 3, "value": 430, "unit": "l", "text": "430 l"},
            {"vehicle": "Mercedes-Benz EQE", "aspect": "range", "source_index": 3, "value": 620, "unit": "km", "standard": "WLTP",
             "text": "620 km, see https://invented.example/not-a-citation"},
        ]}
        extractions = [profile_draft, observation_draft]
        calls = []

        class FakeResponses:
            def create(self, **kwargs):
                calls.append(kwargs)
                if kwargs.get("tools"):
                    return searches.pop(0)
                return SimpleNamespace(output_text=json.dumps(extractions.pop(0)))

        client = SimpleNamespace(responses=FakeResponses())
        docs, draft = research_with_openai(client, "G60", "EU", "range", max_sources=3)
        result = build_result("G60", "EU", "range", docs, draft)

        self.assertEqual([bool(c.get("tools")) for c in calls], [True, False, True, True, False])
        self.assertEqual([d.url for d in docs], ["https://www.bmw.de/i5", "https://www.bmw.de/i5-range", "https://www.mercedes-benz.de/eqe"])
        self.assertEqual(result.competitor_set.rivals, ["Mercedes-Benz EQE"])
        self.assertEqual([(f.aspect, f.source_url) for f in result.findings], [("range", "https://www.bmw.de/i5")])
        self.assertEqual(cell(result, "Mercedes-Benz EQE", "boot_volume").status, "anchor_leads")
        self.assertFalse(any("invented.example" in json.dumps(c) for f in result.findings for c in f.citations))

    def test_store_result_leaves_step_awaiting_review(self):
        statements = []

        class FakeConn:
            def execute(self, sql, params=()):
                statements.append((sql, params))
                row = ("new-id",) if "returning id" in sql else None
                return SimpleNamespace(fetchone=lambda: row)

            @contextmanager
            def transaction(self):
                yield

        class FakeClient:
            embeddings = SimpleNamespace(
                create=lambda model, input: SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in input])
            )

        result = fixture_result()
        store_result(FakeConn(), FakeClient(), result, "run-1", None)

        sql = [s for s, _ in statements]
        self.assertIn("'awaiting_review'", sql[0])
        self.assertIn("position", sql[0])
        self.assertEqual(sum(s.startswith("insert into public.finding (") for s in sql), len(result.findings))
        self.assertTrue(any(s.startswith("insert into public.source") for s in sql))
        refs = json.loads(statements[-1][1][0])
        self.assertEqual({r["type"] for r in refs}, {"finding", "segment_definition", "competitor_set", "comparison_cell"})
        self.assertFalse(any("accepted" in s or "public.requirement" in s or "public.score" in s for s in sql))

    def test_seeded_source_trust_tier_defaults_to_lowest(self):
        docs = [SourceDoc("https://unknown-blog.example/eqe", "Blog", "EQE 620 km"), SourceDoc("https://www.bmw.de/i5", "BMW", "580 km")]
        draft = {
            "anchor": {"attributes": [{"attribute": "range", "value": 580, "unit": "km", "standard": "WLTP", "source_index": 2}]},
            "candidates": [{"make": "Mercedes-Benz", "model": "EQE", "attributes": [
                {"attribute": "range", "value": 620, "unit": "km", "standard": "WLTP", "source_index": 1}]}],
        }
        finding = build_result("G60", "EU", "range", docs, draft).findings[0]

        self.assertEqual((finding.trust_tier, finding.evidence_level), ("forum_social", "Unverified"))
        self.assertTrue(any("non-manufacturer" in a for a in finding.assumptions))

    def test_cli_dry_run_works_without_openai_or_database(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.agents.competitor_agent",
                "seat comfort and range vs rivals",
                "--vehicle-line",
                "G60",
                "--market",
                "EU",
                "--band",
                "price=60000:100000",
                "--seed-sources",
                str(SOURCES),
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
        self.assertEqual(payload["vehicle_line"], "G60")
        self.assertEqual(payload["market"], "EU")
        self.assertIn("Tesla Model S", payload["competitor_set"]["rivals"])
        self.assertTrue(payload["findings"])
        self.assertIn("retrieved", payload["findings"][0]["locator"])


if __name__ == "__main__":
    unittest.main()
