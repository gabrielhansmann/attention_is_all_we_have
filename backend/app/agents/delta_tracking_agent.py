"""Delta / Tracking Agent (ongoing).

Compares a new ingestion batch with the evidence behind tracked requirements and raises
`new_evidence`, `contradicting` and `stale` flags for PM review. "No material change" stays
quiet. The agent only flags: it never changes a requirement's status, evidence links or text.
Matching and classification are plain code, so the same batch always gives the same flags.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - exercised only without installed deps
    psycopg = None

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    def load_dotenv(*_args: Any, **_kwargs: Any) -> None:
        return None

load_dotenv(Path(__file__).resolve().parents[3] / ".env")  # repo-root .env, from any working directory

AGENT_NAME = "Delta / Tracking Agent"
FLAG_TYPES = ("new_evidence", "contradicting", "stale")
ROUTE = "pm_review"
CHECKED_STATUSES = ("tracked",)     # doc 05: only tracked requirements go through the delta check
STALE_AFTER_DAYS = 365
MATCH_THRESHOLD = 0.4
SENTIMENT_THRESHOLD = 0.2

GAP_SIGNALS = {"complaint", "unmet_need", "competitor_advantage"}
STRENGTH_SIGNALS = {"praise"}
DATE_FIELDS = ("observed_at", "retrieved_at", "created_at")
ANY_SCOPE = {"", "ALL", "GLOBAL"}
STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "are", "was", "were", "has", "have", "not", "too", "but",
    "its", "their", "than", "then", "into", "more", "most", "very", "after", "when", "which", "while", "customer",
    "customers", "report", "reports", "review", "notes",
}

Similarity = Callable[[str, str], float]


@dataclass
class DeltaFlag:
    flag_type: str
    requirement_id: str
    requirement_code: str | None
    requirement_status: str             # as read; the agent never writes it
    reason: str
    finding_ids: list[str]              # what the flag rests on: new findings, or the aged evidence for `stale`
    citations: list[dict[str, Any]]
    compared_finding_ids: list[str]     # the existing evidence it was compared with
    compared_citations: list[dict[str, Any]]
    match_score: float | None
    route: str
    detected_at: str


@dataclass
class DeltaTrackingResult:
    agent_name: str
    vehicle_line: str
    market: str
    batch_id: str | None
    as_of: str
    stale_after_days: int
    requirements_checked: int
    new_findings_read: int
    flags: list[DeltaFlag]
    unchanged: list[str]
    skipped: list[dict[str, str]]
    summary: str


def citation_of(finding: dict[str, Any]) -> dict[str, Any] | None:
    """The id and locator a claim is traced by, or None when the finding cannot be cited."""
    finding_id = finding.get("id") or finding.get("finding_id")
    locator = finding.get("locator")
    if not finding_id or not locator:
        return None
    source = finding.get("source") or finding.get("source_file") or finding.get("source_url") or finding.get("file")
    return {
        "finding_id": str(finding_id),
        "source": str(source or ""),
        "locator": str(locator),
        "evidence_level": finding.get("evidence_level"),
    }


def cite_text(citation: dict[str, Any]) -> str:
    """`F-101: file, locator` for a summary bullet; web locators already contain their URL."""
    where = citation["locator"] if citation["source"] in citation["locator"] else f"{citation['source']}, {citation['locator']}"
    return f"{citation['finding_id']}: {where}"


def parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def finding_date(finding: dict[str, Any]) -> datetime | None:
    return next((d for d in (parse_date(finding.get(name)) for name in DATE_FIELDS) if d), None)


def tokens(text: str) -> set[str]:
    """Content words, cut to six letters as a crude stem (ventilation ~ ventilated)."""
    words = re.findall(r"[a-zäöüß0-9]+", text.lower())
    return {w[:6] for w in words if len(w) > 2 and w not in STOPWORDS}


def lexical_similarity(a: str, b: str) -> float:
    """Share of the shorter text's content words found in the other. Deterministic, no embeddings."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def stance(finding: dict[str, Any]) -> str:
    """`gap` (something is missing or worse), `strength` (it works well) or `neutral`."""
    if finding.get("stance") in {"gap", "strength", "neutral"}:
        return finding["stance"]
    if finding.get("signal_type") in GAP_SIGNALS:
        return "gap"
    if finding.get("signal_type") in STRENGTH_SIGNALS:
        return "strength"
    sentiment = finding.get("sentiment")
    if sentiment is not None and float(sentiment) <= -SENTIMENT_THRESHOLD:
        return "gap"
    if sentiment is not None and float(sentiment) >= SENTIMENT_THRESHOLD:
        return "strength"
    return "neutral"


def direction_of(evidence: list[dict[str, Any]]) -> str:
    """What the requirement's existing evidence says, by majority; a tie is `neutral`."""
    stances = [stance(f) for f in evidence]
    gap, strength = stances.count("gap"), stances.count("strength")
    return "gap" if gap > strength else "strength" if strength > gap else "neutral"


def in_scope(finding: dict[str, Any], requirement: dict[str, Any]) -> bool:
    line, req_line = str(finding.get("vehicle_line") or "").upper(), str(requirement.get("vehicle_line") or "").upper()
    if line not in ANY_SCOPE and req_line not in ANY_SCOPE and line != req_line:
        return False
    market = str(finding.get("market") or "").upper()
    markets = {str(m).upper() for m in requirement.get("markets") or []} - ANY_SCOPE
    return market in ANY_SCOPE or not markets or market in markets


def match_score(finding: dict[str, Any], requirement: dict[str, Any], evidence: list[dict[str, Any]], similarity: Similarity) -> float:
    """1.0 when ingestion already tied the finding to the requirement, else the best text similarity
    against the requirement's wording and each piece of its evidence."""
    if str(requirement["id"]) in {str(i) for i in finding.get("requirement_ids") or []}:
        return 1.0
    text = str(finding.get("text") or "")
    candidates = [f"{requirement.get('title', '')} {requirement.get('description', '')}"] + [str(f.get("text") or "") for f in evidence]
    return round(max(similarity(text, candidate) for candidate in candidates), 4)


def build_result(
    vehicle_line: str,
    market: str,
    requirements: list[dict[str, Any]],
    new_findings: list[dict[str, Any]],
    *,
    existing_findings: list[dict[str, Any]] | None = None,
    batch_id: str | None = None,
    as_of: str | None = None,
    stale_after_days: int = STALE_AFTER_DAYS,
    match_threshold: float = MATCH_THRESHOLD,
    similarity: Similarity | None = None,
) -> DeltaTrackingResult:
    """Flag what moved for each tracked requirement.

    A requirement carries its current evidence as `evidence` (finding dicts) or as
    `linked_finding_ids` resolved against `existing_findings`. `new_findings` is the ingestion
    batch. `similarity` can be swapped for an embedding-based one; the default is lexical.
    """
    similarity = similarity or lexical_similarity
    now = parse_date(as_of) or datetime.now(timezone.utc)
    detected_at = datetime.now(timezone.utc).isoformat()
    existing_by_id = {str(f.get("id")): f for f in existing_findings or [] if f.get("id")}
    skipped: list[dict[str, str]] = []

    batch: list[dict[str, Any]] = []
    for finding in new_findings:
        cited = citation_of(finding)
        if cited is None:
            skipped.append({"item": str(finding.get("id") or finding.get("text") or "finding")[:80],
                            "reason": "new finding has no id or locator and cannot be cited"})
        elif finding.get("out_of_scope_reason"):
            skipped.append({"item": cited["finding_id"], "reason": f"out of scope: {finding['out_of_scope_reason']}"})
        else:
            batch.append({**finding, "id": cited["finding_id"]})

    flags: list[DeltaFlag] = []
    unchanged: list[str] = []
    checked = 0
    for requirement in requirements:
        label = str(requirement.get("code") or requirement.get("id"))
        status = str(requirement.get("status") or "")
        if status not in CHECKED_STATUSES:
            skipped.append({"item": label, "reason": f"status is {status or 'unknown'}, only tracked requirements are checked"})
            continue
        linked = requirement.get("evidence") or [
            existing_by_id[str(i)] for i in requirement.get("linked_finding_ids") or [] if str(i) in existing_by_id
        ]
        evidence = [{**f, "id": c["finding_id"]} for f in linked if (c := citation_of(f))]
        if not evidence:
            skipped.append({"item": label, "reason": "no citable existing evidence to compare against"})
            continue
        checked += 1
        evidence_ids = [f["id"] for f in evidence]
        evidence_citations = [citation_of(f) for f in evidence]
        known = {(str(f.get("source") or ""), f["locator"], str(f.get("text") or "")) for f in evidence}
        direction = direction_of(evidence)

        def flag(flag_type: str, reason: str, findings: list[dict[str, Any]], score: float | None) -> None:
            flags.append(DeltaFlag(
                flag_type=flag_type,
                requirement_id=str(requirement["id"]),
                requirement_code=requirement.get("code"),
                requirement_status=status,
                reason=reason,
                finding_ids=[f["id"] for f in findings],
                citations=[citation_of(f) for f in findings],
                compared_finding_ids=evidence_ids,
                compared_citations=evidence_citations,
                match_score=score,
                route=ROUTE,
                detected_at=detected_at,
            ))

        before = len(flags)
        supported = False
        for finding in batch:
            if finding["id"] in evidence_ids or (str(finding.get("source") or ""), finding["locator"], str(finding.get("text") or "")) in known:
                continue        # already part of the requirement's evidence
            if not in_scope(finding, requirement):
                continue
            score = match_score(finding, requirement, evidence, similarity)
            if score < match_threshold:
                continue
            new_stance = stance(finding)
            if "neutral" not in (new_stance, direction) and new_stance != direction:
                flag("contradicting",
                     f"{finding['id']} reads as a {new_stance} while the existing evidence for {label} reads as a {direction}.",
                     [finding], score)
            else:
                supported = True
                unclear = "" if new_stance == direction else " Its direction is unclear, so it is not counted as a contradiction."
                flag("new_evidence", f"{finding['id']} is new evidence on the topic of {label}.{unclear}", [finding], score)

        dated = [(finding_date(f), f) for f in evidence]
        newest = max((d for d, _ in dated if d), default=None)
        if newest is None:
            skipped.append({"item": label, "reason": "existing evidence carries no date, staleness could not be checked"})
        elif (now - newest).days > stale_after_days and not supported:
            # Fresh support in this batch already re-opens the review, so a stale flag would be noise.
            flag("stale",
                 f"The newest evidence for {label} is from {newest.date().isoformat()}, {(now - newest).days} days old "
                 f"(limit {stale_after_days}).", evidence, None)

        if len(flags) == before:
            unchanged.append(label)

    summary = summarize(vehicle_line, market, batch_id, now, stale_after_days, checked, len(batch), flags, unchanged, skipped)
    return DeltaTrackingResult(
        agent_name=AGENT_NAME,
        vehicle_line=vehicle_line,
        market=market,
        batch_id=batch_id,
        as_of=now.isoformat(),
        stale_after_days=stale_after_days,
        requirements_checked=checked,
        new_findings_read=len(batch),
        flags=flags,
        unchanged=unchanged,
        skipped=skipped,
        summary=summary,
    )


def summarize(
    vehicle_line: str,
    market: str,
    batch_id: str | None,
    as_of: datetime,
    stale_after_days: int,
    requirements_checked: int,
    new_findings_read: int,
    flags: list[DeltaFlag],
    unchanged: list[str],
    skipped: list[dict[str, str]],
) -> str:
    lines = [
        f"{AGENT_NAME} compared {new_findings_read} new finding(s)" + (f" from batch {batch_id}" if batch_id else "")
        + f" with the evidence of {requirements_checked} tracked requirement(s) for {vehicle_line} / {market}, "
        f"as of {as_of.date().isoformat()}. Evidence older than {stale_after_days} days counts as stale.",
        "Flags go to PM review. No requirement was changed.",
        "",
        "Flags:",
    ]
    for item in flags:
        cites = "; ".join(cite_text(c) for c in item.citations)
        lines.append(f"- {item.requirement_code or item.requirement_id} {item.flag_type}: {item.reason} ({cites})")
    if not flags:
        lines.append("- No flags: nothing material changed.")
    lines.extend(["", "Confidence and gaps:"])
    if unchanged:
        lines.append(f"- {len(unchanged)} requirement(s) had no material change and stay quiet: {', '.join(unchanged)}.")
    if flags:
        lines.append("- Matching compares wording, and direction comes from signal type and sentiment: "
                     "a flag is a prompt to look, not a verdict.")
    lines.extend(f"- Skipped {item['item']}: {item['reason']}" for item in skipped)
    if lines[-1] == "Confidence and gaps:":
        lines.append("- Nothing was skipped.")
    return "\n".join(lines)


def require_psycopg() -> Any:
    if psycopg is None:
        raise RuntimeError("psycopg is not installed. Run `pip install -e backend`.")
    return psycopg


def store_result(conn: Any, result: DeltaTrackingResult, run_id: str | None, step_id: str | None) -> None:
    """Log one audit event per flag against its requirement, and leave a given step in review.

    The requirement rows are not written: moving one back to `pm_review` is the PM's decision.
    The agent is not a pipeline stage, so it only updates a step it was handed and never adds one.
    """
    with conn.transaction():
        if step_id:
            refs = [{"type": "delta_flag", "flag_type": f.flag_type, "requirement_id": f.requirement_id,
                     "finding_ids": f.finding_ids, "citations": f.citations} for f in result.flags]
            conn.execute(
                "update public.step set status = 'awaiting_review', human_readable_summary = %s, "
                "structured_output_refs = %s::jsonb where id = %s",
                (result.summary, json.dumps(refs), step_id),
            )
        for item in result.flags:
            after = {**asdict(item), "batch_id": result.batch_id, "run_id": run_id}
            conn.execute(
                "insert into public.audit_event (entity_type, entity_id, actor, action, after, rationale) "
                "values ('requirement', %s, %s, %s, %s::jsonb, %s)",
                (item.requirement_id, AGENT_NAME, f"flagged_{item.flag_type}", json.dumps(after), item.reason),
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Delta / Tracking Agent")
    parser.add_argument("--input-json", type=Path, required=True,
                        help="{requirements, new_findings, existing_findings?, batch_id?}")
    parser.add_argument("--vehicle-line", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--as-of", help="ISO date the check is made for; defaults to now")
    parser.add_argument("--stale-after-days", type=int, default=STALE_AFTER_DAYS)
    parser.add_argument("--match-threshold", type=float, default=MATCH_THRESHOLD)
    parser.add_argument("--run-id")
    parser.add_argument("--step-id")
    parser.add_argument("--dry-run", action="store_true", help="print JSON result instead of writing audit events")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("Delta / Tracking Agent input JSON must be an object")
    result = build_result(
        args.vehicle_line,
        args.market,
        payload.get("requirements", []),
        payload.get("new_findings", []),
        existing_findings=payload.get("existing_findings", []),
        batch_id=payload.get("batch_id"),
        as_of=args.as_of or payload.get("as_of"),
        stale_after_days=args.stale_after_days,
        match_threshold=args.match_threshold,
    )

    if args.dry_run:
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return 0

    conn = require_psycopg().connect(os.environ["SUPABASE_DB_URL"])
    store_result(conn, result, args.run_id, args.step_id)
    conn.close()
    print(result.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
