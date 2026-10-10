import json
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.documentation_agent import (
    AGENT_NAME,
    build_result,
    embed_chunks,
    store_result,
    summary_gaps,
)

FIXTURE = ROOT / "tests/fixtures/documentation_agent_run.json"
QUERY = "What do we need for seat comfort in the EU?"


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    """Records the SQL an agent would run, so storage is checked without a database."""

    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        return FakeCursor(["source-1"] if "returning id" in sql else None)

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def run(payload=None):
    payload = payload or load()
    return build_result("G60", "EU", QUERY, payload["steps"], payload["decisions"], run_id=payload["run_id"])


class DocumentationAgentTest(unittest.TestCase):
    def test_compiles_accepted_steps_only(self):
        result = run()

        self.assertEqual(result.agent_name, AGENT_NAME)
        self.assertEqual((result.steps_read, result.steps_compiled), (4, 3))
        self.assertEqual({s.agent_name for s in result.statements},
                         {"Customer Feedback Agent", "Requirements Drafting Agent", "Prioritization Agent"})
        self.assertEqual([s.section for s in result.statements],
                         ["evidence", "evidence", "out_of_scope", "requirements", "scores"])
        self.assertNotIn("rival sedan", result.dossier)
        self.assertIn("# Research dossier: " + QUERY, result.dossier)
        self.assertIn("**Prioritization Agent**, attempt 2, accepted by pm on 2026-01-14T09:10", result.dossier)

    def test_every_statement_cites_only_accepted_findings(self):
        result = run()
        accepted_ids = {"F-101", "F-102", "F-105"}

        for statement in result.statements:
            self.assertTrue(statement.finding_ids)
            self.assertLessEqual(set(statement.finding_ids), accepted_ids)
            self.assertEqual([c["finding_id"] for c in statement.citations], statement.finding_ids)
            self.assertTrue(all(c["locator"] for c in statement.citations))
        requirement = next(s for s in result.statements if s.section == "requirements")
        self.assertEqual(requirement.finding_ids, ["F-101", "F-102"])
        self.assertIn("Acceptance criteria: noticeable cooling within 75 s.", requirement.text)

        for line in result.dossier.splitlines():
            if line.startswith("- ") and "## " not in line and "[F-" in line:
                self.assertNotIn("[F-103]", line)
        self.assertIn("- [F-101] G60_feedback_hackathon.xlsx, sheet Feedback_Explorer, row 4642 (G60-3695) (Verified)", result.dossier)

    def test_reads_requirements_whose_fields_are_cited_statements(self):
        payload = load()
        requirement = payload["steps"][2]["output"]["requirements"][0]
        requirement["description"] = {"text": "Seat cooling is felt quickly.", "finding_ids": ["F-101"]}
        requirement["acceptance_criteria"] = [{"text": "cooling within 75 s"}, {"text": "in all climate modes"}]
        text = next(s for s in run(payload).statements if s.section == "requirements").text

        self.assertIn("R-2031 Fast-response seat ventilation: Seat cooling is felt quickly.", text)
        self.assertIn("Acceptance criteria: cooling within 75 s; in all climate modes.", text)

    def test_rejected_and_unsupported_output_becomes_coverage_gaps(self):
        gaps = " | ".join(run().coverage_gaps)

        self.assertIn("Competitor Agent was rejected: Only paywalled sources, proceed without competitor evidence", gaps)
        self.assertNotIn("Documentation Agent is running", gaps)
        self.assertIn("Requirement R-2031: citation(s) to F-103 removed", gaps)
        self.assertIn("Requirement R-2032 was left out", gaps)
        self.assertIn("Customer Feedback Agent: 1 finding(s) have no id or locator and were left out", gaps)
        self.assertIn("Customer Feedback Agent: EU only: there is no customer feedback for China.", gaps)
        self.assertIn("## Coverage gaps", run().dossier)
        self.assertNotIn("R-2032", "".join(s.text for s in run().statements))

    def test_audit_trail_lists_agent_and_pm_actions_in_time_order(self):
        result = run()

        timestamps = [row["timestamp"] for row in result.audit_trail]
        self.assertEqual(timestamps, sorted(timestamps))
        actions = [(row["actor"], row["action"]) for row in result.audit_trail]
        self.assertIn(("orchestrator", "plan_created"), actions)
        self.assertIn(("Prioritization Agent", "scored"), actions)
        # step-1's accept is in the audit log already; the other resolutions come from the steps
        self.assertEqual(sum(1 for _, action in actions if "accept" in action), 3)
        self.assertIn(("pm", "reject step Competitor Agent"), actions)
        self.assertIn("| Timestamp | Actor | Action | Rationale |", result.dossier)
        self.assertIn("drop the paywalled ones \\| find a free equivalent", result.dossier)

    def test_summary_names_scope_contents_citations_and_gaps(self):
        result = run()

        self.assertIn("looked at 4 step(s) (3 accepted, 1 rejected) and 8 audit event(s), 6 of them PM decisions", result.summary)
        self.assertIn("- Draft requirements: 1 statement(s) (F-101: G60_feedback_hackathon.xlsx, sheet Feedback_Explorer", result.summary)
        self.assertIn("Confidence and gaps:", result.summary)
        self.assertIn("Competitor Agent was rejected", result.summary)
        self.assertEqual(summary_gaps("Findings:\n- a\n\nConfidence and gaps:\n- thin\n- thinner"), ["thin", "thinner"])

    def test_nothing_accepted_gives_an_empty_but_honest_dossier(self):
        result = build_result("G60", "EU", QUERY, [{"id": "s", "agent_name": "Customer Feedback Agent", "status": "awaiting_review"}])

        self.assertEqual(result.statements, [])
        self.assertIn("No step has been accepted yet.", result.dossier)
        self.assertIn("No finding could be cited.", result.dossier)
        self.assertIn("the audit trail is empty", result.summary)
        self.assertIn("Customer Feedback Agent is awaiting_review, not accepted", result.summary)

    def test_reembeds_sections_with_an_injected_embedder(self):
        result = run()
        calls = []

        def fake_embedder(texts):
            calls.append(texts)
            return [[float(len(text)), 0.5] for text in texts]

        vectors = embed_chunks(result.chunks, fake_embedder)

        headings = [c.heading for c in result.chunks]
        self.assertEqual(headings[0], "Overview")
        self.assertIn("Draft requirements", headings)
        self.assertIn("Audit trail", headings)
        self.assertEqual(len(vectors), len(result.chunks))
        self.assertEqual(len(calls), 1)
        self.assertEqual("\n\n".join(c.content for c in result.chunks) + "\n", result.dossier)
        self.assertEqual(next(c for c in result.chunks if c.heading == "Draft requirements").finding_ids, ["F-101", "F-102"])
        with self.assertRaises(ValueError):
            embed_chunks(result.chunks, lambda texts: [])

    def test_store_leaves_the_step_in_review_and_changes_no_requirement(self):
        result = run()
        conn = FakeConn()

        store_result(conn, result, "run-42", "step-5", embedder=lambda texts: [[0.1, 0.2] for _ in texts])

        sql = " ".join(statement for statement, _ in conn.statements)
        self.assertIn("set status = 'awaiting_review'", sql)
        self.assertIn("'dossier_compiled'", sql)
        self.assertEqual(sum(1 for statement, _ in conn.statements if "insert into public.chunk" in statement), len(result.chunks))
        self.assertNotIn("public.requirement", sql)
        self.assertNotIn("'accepted'", sql)
        self.assertNotIn("status", asdict(result))

    def test_cli_dry_run_works_without_openai_or_database(self):
        command = [
            sys.executable,
            "-m",
            "app.agents.documentation_agent",
            QUERY,
            "--input-json",
            str(FIXTURE),
            "--vehicle-line",
            "G60",
            "--market",
            "EU",
            "--dry-run",
        ]
        completed = subprocess.run(command, check=True, capture_output=True, text=True, cwd=ROOT)

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["run_id"], "run-42")
        self.assertEqual(len(payload["statements"]), 5)
        self.assertEqual(payload["statements"][0]["citations"][0]["locator"], "sheet Feedback_Explorer, row 4642 (G60-3695)")

        markdown = subprocess.run(command + ["--markdown"], check=True, capture_output=True, text=True, cwd=ROOT).stdout
        self.assertTrue(markdown.startswith("# Research dossier: "))


if __name__ == "__main__":
    unittest.main()
