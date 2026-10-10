import unittest
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.market_trend_agent import (
    SourceDoc,
    build_result,
    evidence_from_trust,
    infer_trust_tier,
    load_market_trend_draft,
    load_seed_sources,
)


class MarketTrendAgentTest(unittest.TestCase):
    def test_infers_trust_tier_and_evidence(self):
        self.assertEqual(infer_trust_tier(SourceDoc("https://www.bmw.com/en/news.html", "BMW", "x")), "oem")
        self.assertEqual(evidence_from_trust("oem"), "Verified")
        self.assertEqual(evidence_from_trust("trade_press"), "Interpreted")
        self.assertEqual(evidence_from_trust("forum_social"), "Unverified")

    def test_build_result_keeps_citations_and_routes_out_of_scope(self):
        docs = [
            SourceDoc(
                url="https://example.com/report",
                title="Market report",
                snippet="Customers increasingly expect faster charging and better route planning.",
                trust_tier="trade_press",
            )
        ]
        draft = {
            "findings": [
                {
                    "source_index": 1,
                    "text": "Customers increasingly expect faster charging and integrated route planning.",
                    "signal_type": "market_trend",
                    "sentiment": 0.2,
                    "assumptions": ["Forward-looking analyst statement."],
                },
                {
                    "source_index": 1,
                    "text": "Price incentives are becoming decisive in the segment.",
                    "signal_type": "market_trend",
                    "sentiment": 0,
                    "assumptions": [],
                },
            ],
            "skipped": [],
        }

        result = build_result("G60", "US", "charging expectations", docs, draft)

        self.assertEqual(result.sources_read, 1)
        self.assertEqual(len(result.findings), 2)
        self.assertIn("retrieved", result.findings[0].locator)
        self.assertEqual(result.findings[0].evidence_level, "Interpreted")
        self.assertIsNone(result.findings[0].out_of_scope_reason)
        self.assertIsNotNone(result.findings[1].out_of_scope_reason)

    def test_loads_fixture_sources_and_draft(self):
        docs = load_seed_sources(ROOT / "tests/fixtures/market_trend_sources.json")
        draft = load_market_trend_draft(ROOT / "tests/fixtures/market_trend_draft.json")

        result = build_result("G60", "US", "comfort trends", docs, draft)

        self.assertEqual(result.sources_read, 2)
        self.assertEqual(len(result.findings), 2)
        self.assertEqual(result.findings[0].trust_tier, "trade_press")
        self.assertEqual(result.findings[1].evidence_level, "Unverified")

    def test_cli_dry_run_works_without_openai_or_database(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "agents/market_trend_agent.py"),
                "comfort trends",
                "--vehicle-line",
                "G60",
                "--market",
                "US",
                "--seed-sources",
                str(ROOT / "tests/fixtures/market_trend_sources.json"),
                "--draft-json",
                str(ROOT / "tests/fixtures/market_trend_draft.json"),
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["vehicle_line"], "G60")
        self.assertEqual(payload["market"], "US")
        self.assertEqual(len(payload["findings"]), 2)
        self.assertIn("retrieved", payload["findings"][0]["locator"])


if __name__ == "__main__":
    unittest.main()
