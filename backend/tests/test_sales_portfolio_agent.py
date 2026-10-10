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

from app.agents.sales_portfolio_agent import (
    AGENT_NAME,
    build_result,
    collect_evidence,
    combined_locator,
    evidence_ref,
    load_sales_portfolio_draft,
    load_seed_evidence,
    option_terms_from_draft,
    run,
    scope_filter,
    scope_seed_evidence,
    store_result,
    variant_statuses,
)

EVIDENCE = ROOT / "tests/fixtures/sales_portfolio_evidence.json"
DRAFT = ROOT / "tests/fixtures/sales_portfolio_draft.json"


class FakeTools:
    """Stands in for app.knowledge.tools: same two lookups, answered from the fixture."""

    def __init__(self):
        self.evidence = load_seed_evidence(EVIDENCE)
        self.calls = []

    def get_sales(self, *, line=None, market=None, year=None):
        self.calls.append(("get_sales", line, market, year))
        return scope_seed_evidence(self.evidence, line, market)["sales"]

    def get_options(self, *, line=None, variant=None, status=None, text=None, limit=25):
        self.calls.append(("get_options", line, variant, status, text, limit))
        return scope_seed_evidence(self.evidence, line, None, [text] if text else None)["options"][:limit]


def by_metric(result, metric):
    return [f for f in result.findings if f.metrics.get("metric") == metric]


class SalesPortfolioAgentTest(unittest.TestCase):
    def test_scope_all_means_no_filter(self):
        self.assertIsNone(scope_filter("ALL"))
        self.assertIsNone(scope_filter("all"))
        self.assertIsNone(scope_filter(None))
        self.assertEqual(scope_filter("G60"), "G60")

        tools = FakeTools()
        result = run("ALL", None, "everything", tools=tools)

        self.assertEqual(tools.calls[0], ("get_sales", None, None, None))
        self.assertEqual(tools.calls[1][:2], ("get_options", None))
        self.assertEqual(result.vehicle_line, "ALL")
        self.assertEqual(result.market, "ALL")
        self.assertEqual({f.vehicle_line for f in result.findings}, {"G60", "G68", "F70"})

    def test_reads_through_knowledge_tools_with_scope_and_terms(self):
        tools = FakeTools()
        evidence = collect_evidence("G60", "EU", option_terms=["Sitzbelüftung", "Glasdach"], option_limit=5, tools=tools)

        self.assertEqual(tools.calls[0], ("get_sales", "G60", "EU", None))
        self.assertEqual([c[4] for c in tools.calls[1:]], ["Sitzbelüftung", "Glasdach"])
        self.assertEqual(len(evidence["sales"]), 3)
        self.assertEqual(len(evidence["options"]), 2)

    def test_sales_numbers_are_computed_from_cited_rows(self):
        result = run("G60", "ALL", "sales by market", tools=FakeTools())

        eu = next(f for f in by_metric(result, "sales_volume") if f.market == "EU")
        self.assertEqual(eu.text, "G60 EU: 50,000 units sold in 2025, +25.0% vs 2023 (40,000 units).")
        self.assertEqual(eu.locator, "sales_volumes.xlsx, sheet G60_G68, rows 2, 3")
        self.assertEqual(eu.evidence_level, "Verified")
        self.assertEqual(eu.signal_type, "business_signal")
        self.assertEqual([c.kind for c in eu.citations], ["sales", "sales"])

        forecast = by_metric(result, "sales_forecast")[0]
        self.assertEqual(forecast.text, "G60 EU: 60,000 units forecast for 2030, +20.0% vs 2025 actual (50,000 units).")
        self.assertEqual(forecast.evidence_level, "Interpreted")
        self.assertTrue(any("forecast" in a for a in forecast.assumptions))

        mix = by_metric(result, "market_share_of_line_volume")[0]
        self.assertEqual(mix.metrics["share_pct"], {"EU": 62.5, "US": 37.5})
        self.assertEqual(mix.metrics["total_volume"], 80000)
        self.assertEqual(len(mix.citations), 2)

    def test_option_availability_and_out_of_scope_bin(self):
        result = run("G60", "US", "seat ventilation", tools=FakeTools())
        options = {f.metrics["option_code"]: f for f in by_metric(result, "standard_fitment_share")}

        seat = options["0453"]
        self.assertEqual(seat.metrics["standard"], 1)
        self.assertEqual(seat.metrics["optional"], 2)
        self.assertEqual(seat.metrics["conditional"], 1)
        self.assertEqual(seat.metrics["share_pct"], 25.0)
        self.assertEqual(seat.metrics["by_powertrain"]["BEV"], {"standard": 1, "optional": 0, "conditional": 1})
        self.assertIn("standard on 1 of 4 catalog variants (25.0%)", seat.text)
        self.assertIn("Standard on: i5 M60 xDrive.", seat.text)
        self.assertEqual(seat.locator, "G60_OptionList.PDF, page 14, SA 0453")
        self.assertEqual(seat.market, "EU")
        self.assertTrue(any("take rates are not in the provided data" in a for a in seat.assumptions))
        self.assertTrue(any("No US option list" in a for a in seat.assumptions))
        self.assertIsNone(seat.out_of_scope_reason)

        self.assertEqual(options["0402"].metrics["share_pct"], 0.0)
        self.assertIsNotNone(options["0261"].out_of_scope_reason)
        # prices are in the tool result but never reach a finding
        self.assertFalse(any("890" in f.text or "1600" in f.text or "price" in json.dumps(f.metrics) for f in result.findings))

    def test_no_citation_means_no_finding(self):
        result = run("G60", "ALL", "all options", tools=FakeTools())

        self.assertNotIn("0999", [f.metrics.get("option_code") for f in result.findings])
        self.assertTrue(any("without a citation" in s["reason"] for s in result.skipped))
        self.assertIsNone(evidence_ref({"citation": {"kind": "sales", "id": "", "file": "x", "locator": "y", "quote": ""}}))
        for finding in result.findings:
            self.assertTrue(finding.locator)
            self.assertTrue(finding.citations)
            self.assertTrue(all(c.id and c.file and c.locator for c in finding.citations))

        broken = {"sales": [{"citation": {"kind": "sales", "id": "1", "file": "f.xlsx", "locator": "sheet A, row 2", "quote": "q"}, "meta": {"year": 2025}}]}
        self.assertEqual(build_result("G60", "EU", "q", broken).findings, [])

    def test_accepts_hit_objects_from_the_real_tools(self):
        hit = SimpleNamespace(
            citation=SimpleNamespace(kind="sales", id="abc", file="sales_volumes.xlsx", locator="sheet G70, row 5", quote="G70 US 2025: 9000 units"),
            text="9000",
            meta={"vehicle_line": "G70", "market_code": "US", "year": 2025, "volume": 9000, "is_forecast": False},
        )
        result = build_result("G70", "US", "volumes", {"sales": [hit], "options": []})

        self.assertEqual(result.findings[0].text, "G70 US: 9,000 units sold in 2025.")
        self.assertEqual(result.findings[0].locator, "sales_volumes.xlsx, sheet G70, row 5")

    def test_helpers(self):
        statuses = variant_statuses([
            {"variant": "a", "status": "standard", "condition": None},
            {"variant": "b", "status": "standard", "condition": "In Verbindung mit X"},
            {"variant": "c", "status": "optional"},
            {"variant": "c", "status": "standard"},
        ])
        self.assertEqual({k: v["status"] for k, v in statuses.items()}, {"a": "standard", "b": "conditional", "c": "conditional"})
        self.assertEqual(option_terms_from_draft(load_sales_portfolio_draft(DRAFT)), ["Sitzbelüftung", "Airbag"])
        refs = [evidence_ref(h) for h in load_seed_evidence(EVIDENCE)["sales"][:2]]
        self.assertEqual(combined_locator(refs), "sales_volumes.xlsx, sheet G60_G68, rows 2, 3")

    def test_summary_and_result_shape(self):
        result = run("G60", "EU", "seat ventilation uptake", option_terms=["Sitzbelüftung", "Airbag"], tools=FakeTools())
        summary = result.summary

        self.assertTrue(summary.startswith(f"{AGENT_NAME} looked at 3 sales row(s) and 2 option row(s) for G60 / EU"))
        self.assertIn("Filters: vehicle_line=G60, market=EU, option_terms=Sitzbelüftung, Airbag", summary)
        self.assertIn("Sources: G60_OptionList.PDF, sales_volumes.xlsx", summary)
        self.assertIn("(Verified; sales_volumes.xlsx, sheet G60_G68, rows 2, 3)", summary)
        self.assertIn("Out-of-scope bin", summary)
        self.assertIn("Confidence and gaps:", summary)
        self.assertIn("take rates are not in the provided data", summary)
        self.assertIn("waits for PM review", summary)

        payload = asdict(result)
        self.assertEqual(payload["agent_name"], "Sales & Portfolio Agent")
        for finding in payload["findings"]:
            for key in ("text", "signal_type", "evidence_level", "locator", "market", "vehicle_line", "assumptions",
                        "out_of_scope_reason", "trust_tier"):
                self.assertIn(key, finding)
            self.assertEqual(finding["signal_type"], "business_signal")

        empty = build_result("F70", "CN", "nothing", {"sales": [], "options": []})
        self.assertEqual(empty.findings, [])
        self.assertIn("No usable sales or portfolio findings", empty.summary)
        self.assertIn("No sales rows matched", empty.summary)

    def test_store_result_leaves_step_awaiting_review(self):
        statements = []

        class FakeConn:
            def execute(self, sql, params=()):
                statements.append((sql, params))
                row = None
                if sql.startswith("select id from public.source"):
                    row = ("source-1",)
                elif "returning id" in sql:
                    row = ("new-id",)
                return SimpleNamespace(fetchone=lambda: row)

            @contextmanager
            def transaction(self):
                yield

        class FakeClient:
            embeddings = SimpleNamespace(
                create=lambda model, input: SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in input])
            )

        result = run("G60", "EU", "seat ventilation", option_terms=["Sitzbelüftung"], tools=FakeTools())
        store_result(FakeConn(), FakeClient(), result, "run-1", None)

        sql = [s for s, _ in statements]
        self.assertIn("'awaiting_review'", sql[0])
        self.assertIn("position", sql[0])
        self.assertEqual(sum(s.startswith("insert into public.finding (") for s in sql), len(result.findings))
        self.assertEqual(sum("finding_evidence" in s for s in sql), sum(len(f.citations) for f in result.findings))
        self.assertTrue(any("sales_volume_id" in s for s in sql))
        self.assertTrue(any("option_id" in s for s in sql))
        self.assertFalse(any("accepted" in s or "requirement" in s or "score" in s for s in sql))

    def test_cli_dry_run_works_without_openai_or_database(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.agents.sales_portfolio_agent",
                "seat ventilation uptake",
                "--vehicle-line",
                "G60",
                "--market",
                "EU",
                "--seed-evidence",
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
        self.assertEqual(payload["vehicle_line"], "G60")
        self.assertEqual(payload["market"], "EU")
        codes = [f["metrics"].get("option_code") for f in payload["findings"] if f["metrics"]["metric"] == "standard_fitment_share"]
        self.assertEqual(codes, ["0453", "0261"])
        self.assertEqual(len(payload["findings"]), 4)
        self.assertIn("sheet G60_G68", payload["findings"][0]["locator"])


if __name__ == "__main__":
    unittest.main()
