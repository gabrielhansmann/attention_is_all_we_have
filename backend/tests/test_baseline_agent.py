import json
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.baseline_agent import (
    AGENT_NAME,
    build_result,
    collect_evidence,
    load_draft,
    run_agent,
    store_result,
)
from app.agents.customer_feedback_agent import EvidencePack, load_evidence

EVIDENCE = ROOT / "tests/fixtures/baseline_evidence.json"
DRAFT = ROOT / "tests/fixtures/baseline_draft.json"


def hit(kind, id, file, locator, quote, **meta):
    """Shaped like `app.knowledge.tools.Hit`, without importing the database-backed module."""
    return SimpleNamespace(
        citation=SimpleNamespace(kind=kind, id=id, file=file, locator=locator, quote=quote),
        text=quote,
        meta=meta,
    )


class FakeTools:
    """Stands in for the knowledge tools and records the filters each call received."""

    def __init__(self, empty=False):
        self.calls = []
        self.empty = empty

    def search_feedback(self, query, *, line=None, market=None, domain=None, polarity=None, powertrain=None, k=10):
        self.calls.append(("search_feedback", line, market, polarity))
        if self.empty:
            return []
        return [hit("feedback", "fb-1", "G60_feedback_hackathon.xlsx", "sheet Feedback_Explorer, row 233 (G60-0198)",
                    "The front seats are superb.", vehicle_line="G60", market_code="EU", polarity="positive")]

    def search_docs(self, query, *, line=None, k=8):
        self.calls.append(("search_docs", line, None, None))
        if self.empty:
            return []
        return [hit("pdf_text", "ch-1", "G60_OptionList.PDF", "page 14", "SPORTSITZE", vehicle_line="G60")]

    def get_options(self, *, line=None, variant=None, status=None, text=None, limit=25):
        self.calls.append(("get_options", line, None, status))
        if self.empty:
            return []
        availability = [
            {"variant": "520i", "powertrain": "ICE", "status": "standard", "price_gross": 1234.0, "condition": None},
            {"variant": "530e", "powertrain": "PHEV", "status": "standard", "price_gross": 1234.0, "condition": None},
            {"variant": "M5", "powertrain": "PHEV", "status": "optional", "price_gross": 990.0, "condition": None},
        ]
        return [hit("option", "op-1", "G60_OptionList.PDF", "page 16, SA 481", "Sportsitze", vehicle_line="G60",
                    code="481", section="Sitze", availability=availability)]

    def get_sales(self, *, line=None, market=None, year=None):
        self.calls.append(("get_sales", line, market, None))
        if self.empty:
            return []
        return [
            hit("sales", "sv-1", "sales_volumes.xlsx", "sheet G60_G68, row 4", "G60 Europe 2024: 61000 units",
                vehicle_line="G60", market_code="EU", year=2024, volume=61000, is_forecast=False),
            hit("sales", "sv-2", "sales_volumes.xlsx", "sheet G60_G68, row 5", "G60 Europe 2030: 70000 units (forecast)",
                vehicle_line="G60", market_code="EU", year=2030, volume=70000, is_forecast=True),
        ]

    def feedback_stats(self, group_by, *, line=None, market=None, domain=None, polarity=None, powertrain=None):
        self.calls.append(("feedback_stats", line, market, group_by))
        return [] if self.empty else [{"key": "negative", "n": 20}, {"key": "positive", "n": 15}]


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


class BaselineAgentTest(unittest.TestCase):
    def test_collect_evidence_reads_praise_portfolio_and_sales(self):
        tools = FakeTools()
        pack = collect_evidence(tools, "seat comfort", "G60", "EU")

        self.assertEqual([e.kind for e in pack.hits], ["feedback", "pdf_text", "option", "sales", "sales"])
        self.assertIn(("search_feedback", "G60", "EU", "positive"), tools.calls)
        self.assertIn(("get_options", "G60", None, "standard"), tools.calls)
        self.assertEqual(pack.counts["positive"], 15)
        self.assertTrue(any("forecast" in gap for gap in pack.gaps))
        self.assertTrue(any("carry no market" in gap for gap in pack.gaps))

        # Prices never leave the tool hit: only the variants an option is standard on are kept.
        option = pack.hits[2]
        self.assertEqual(option.meta["standard_on"], ["520i", "530e"])
        self.assertNotIn("price", json.dumps(asdict(option)))

    def test_scope_all_means_no_filter_and_empty_scope_states_gaps(self):
        tools = FakeTools()
        collect_evidence(tools, "seat comfort", "ALL", None)
        self.assertTrue(all(line is None and market is None for _, line, market, _ in tools.calls))

        pack = collect_evidence(FakeTools(empty=True), "seat comfort", "G68", "CN")
        self.assertEqual(pack.hits, [])
        self.assertEqual(len(pack.gaps), 3)
        self.assertIn("No positive customer comments were found for G68 / CN.", pack.gaps)

    def test_build_result_tags_continuity_and_cites_only_retrieved_rows(self):
        pack = load_evidence(EVIDENCE)
        result = build_result("G60", "EU", "seat comfort", pack, load_draft(DRAFT))

        self.assertEqual(result.agent_name, AGENT_NAME)
        self.assertEqual(len(result.findings), 4)
        self.assertIn({"source": "unknown", "reason": "finding cited no retrieved evidence; dropped"}, result.skipped)
        self.assertIn({"source": "G60_OptionList.PDF, page 14", "reason": "catalog page repeats the option row"}, result.skipped)

        known = {(e.file, e.locator, e.quote) for e in pack.hits}
        for finding in result.findings:
            self.assertEqual(finding.signal_type, "strategic_continuity")
            self.assertEqual((finding.market, finding.vehicle_line), ("EU", "G60"))
            self.assertTrue(finding.citations)
            for c in finding.citations:
                self.assertIn((c["file"], c["locator"], c["quote"]), known)
            self.assertTrue(any("predecessor" in a for a in finding.assumptions))

    def test_evidence_level_sample_size_and_forecast_assumption(self):
        result = build_result("G60", "EU", "seat comfort", load_evidence(EVIDENCE), load_draft(DRAFT))
        praise, equipment, sales, _pricing = result.findings

        self.assertEqual((praise.evidence_level, praise.sample_size, praise.sample_base), ("Interpreted", 2, 540))
        self.assertEqual(praise.locator, "sheet Feedback_Explorer, row 233 (G60-0198); sheet Feedback_Explorer, row 977 (G60-0850)")
        # An option row plus catalog text: the free-text page makes it a reading, not a table fact.
        self.assertEqual((equipment.evidence_level, equipment.sample_size), ("Interpreted", None))
        self.assertEqual(equipment.locator, "page 16, SA 481; page 14")
        self.assertEqual((sales.evidence_level, sales.source_file), ("Verified", "sales_volumes.xlsx"))
        self.assertTrue(any("forecast" in a for a in sales.assumptions))
        self.assertFalse(any("forecast" in a for a in praise.assumptions))

    def test_summary_and_out_of_scope_bin(self):
        result = build_result("G60", "EU", "seat comfort", load_evidence(EVIDENCE), load_draft(DRAFT))

        self.assertIn("looked at 6 retrieved rows (2 feedback, 1 option, 1 pdf_text, 2 sales) for G60 / EU: seat comfort", result.summary)
        self.assertIn("Sources: G60_OptionList.PDF, G60_feedback_hackathon.xlsx, sales_volumes.xlsx.", result.summary)
        self.assertIn("(Verified; market EU; no customer comments cited; sales_volumes.xlsx, sheet G60_G68, row 4; "
                      "sales_volumes.xlsx, sheet G60_G68, row 5)", result.summary)
        self.assertIn("forecast", result.summary.split("Confidence and gaps:")[1])

        self.assertEqual([f.out_of_scope_reason is not None for f in result.findings], [False, False, False, True])
        found, bin_section = result.summary.split("Out of scope (routed to the side bin):")
        self.assertIn("list price", bin_section)
        self.assertNotIn("list price", found)
        self.assertFalse({"requirements", "score", "priority", "status"} & set(asdict(result)))

    def test_run_agent_with_injected_tools_and_nothing_retrieved(self):
        tools = FakeTools()
        draft = {"findings": [{"evidence": [3], "text": "Sport seats are standard on the 520i and 530e."}]}
        result = run_agent("seat comfort", "G60", "EU", tools=tools, draft=draft)
        self.assertEqual((result.findings[0].evidence_level, result.findings[0].locator), ("Verified", "page 16, SA 481"))

        # Nothing retrieved: no model call is made and nothing is claimed.
        nothing = run_agent("seat comfort", "G68", "CN", pack=EvidencePack(hits=[], gaps=["No sales volumes were found for G68 / CN."]))
        self.assertEqual(nothing.findings, [])
        self.assertIn("No usable continuity findings", nothing.summary)

    def test_store_result_leaves_the_step_awaiting_review(self):
        result = build_result("G60", "EU", "seat comfort", load_evidence(EVIDENCE), load_draft(DRAFT))
        conn = FakeConn()
        store_result(conn, SimpleNamespace(embeddings=FakeEmbeddings()), result, "run-1", None)

        sql = [s for s, _ in conn.statements]
        self.assertIn("'awaiting_review'", sql[0])
        self.assertEqual(conn.statements[0][1][:2], ("run-1", AGENT_NAME))
        self.assertFalse(any("accepted" in s or "rejected" in s or "public.requirement" in s for s in sql))
        self.assertEqual(sum("insert into public.finding (" in s for s in sql), 4)
        links = [s for s in sql if "insert into public.finding_evidence" in s]
        self.assertEqual(len(links), 7)
        self.assertEqual(sum("sales_volume_id" in s for s in links), 2)
        self.assertEqual(sum("chunk_id" in s for s in links), 1)

    def test_cli_dry_run_works_without_openai_or_database(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.agents.baseline_agent",
                "seat comfort",
                "--vehicle-line",
                "G60",
                "--market",
                "EU",
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
        self.assertEqual(len(payload["findings"]), 4)
        self.assertEqual({f["signal_type"] for f in payload["findings"]}, {"strategic_continuity"})
        self.assertIn("row 233", payload["findings"][0]["locator"])


if __name__ == "__main__":
    unittest.main()
