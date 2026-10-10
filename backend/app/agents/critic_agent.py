"""Critic Agent.

Cross-cutting, not a step of its own: it sits inside `running -> awaiting_review`, between every
agent and the PM (docs/architecture/01-agents.md, decision 0003). It checks that every claim in an
agent's output carries a citation with a well-formed locator, sends unsupported claims back for a
retry, and downgrades `evidence_level` on evidence that is cited but thin.

The checks are deterministic code. An optional model pass ("does the cited snapshot support the
claim") can be injected; it only proposes, code decides what happens (decision 0012). The Critic
never accepts or rejects a step: a passing verdict is what allows `StepAction.FINISH`, nothing more.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

AGENT_NAME = "Critic Agent"
DEFAULT_MAX_RETRIES = 2

# Weakest to strongest (docs/architecture/04-data-model.md, `finding.evidence_level`).
EVIDENCE_ORDER = ("Unverified", "Interpreted", "Verified")
LOW_TRUST_TIERS = {"forum_social"}
KNOWN_TRUST_TIERS = {"oem", "trade_press", "forum_social"}

SYNTHESIS_KEYS = ("clusters", "requirements", "scores", "flags", "dossier")
DOSSIER_LIST_KEYS = ("statements", "claims", "sections", "items")
DOSSIER_TEXT_KEYS = ("markdown", "text", "body", "content")
SUMMARY_LIST_KEYS = ("found", "findings", "bullets")
FINDING_ID_KEYS = ("finding_ids", "member_finding_ids", "linked_finding_ids", "evidence_finding_ids", "source_finding_ids")
LOCATOR_LIST_KEYS = ("locators", "finding_locators", "evidence_locators")
CITATION_LIST_KEYS = ("citations", "evidence", "linked_findings")
FILE_KEYS = ("file", "source_file", "file_name", "filename", "source_uri", "uri", "source", "document")
URL_KEYS = ("source_url", "url")
POSITION_KEYS = ("page", "sheet", "row", "row_no", "cell", "cell_ref", "slide", "section")
TEXT_KEYS = ("text", "statement", "title", "label", "description", "rationale", "name")

URL_RE = re.compile(r"https?://[^\s<>\"'\])]+", re.IGNORECASE)
RETRIEVED_RE = re.compile(r"retriev\w*\s*(?:on|at)?\s*:?\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
FILE_RE = re.compile(r"[\w\-.]+\.(?:xlsx|xlsm|xls|csv|pdf|docx|pptx|txt|md|json)\b", re.IGNORECASE)
POSITION_RE = re.compile(r"\b(?:pages?|sheet|rows?|cell|slide|section|chunk)\s*[:#]?\s*[\w\-]+", re.IGNORECASE)
BULLET_RE = re.compile(r"^(?:[-*•]|\d+[.)])\s+(.*)$")
NOTHING_FOUND_RE = re.compile(r"^(?:no|none|nothing)\b", re.IGNORECASE)
LABEL_RE = re.compile(r"^[A-Za-z][\w /&-]{0,30}:\s+")
NOT_A_CLAIM_RE = re.compile(r"^(?:model\s+)?(?:assumptions?|uncertaint(?:y|ies)|open questions?|gaps?|audit trail)\b\s*:", re.IGNORECASE)
# Summary sections that describe the run rather than state findings; their bullets need no citation.
EXEMPT_HEADER_RE = re.compile(
    r"confiden|gap|thin|missing|scope|looked|source|filter|method|note|assumption|skipped|critic|accepted steps|audit trail",
    re.IGNORECASE,
)

SupportCheck = Callable[[str, str, str], Any]


@dataclass
class CriticIssue:
    item: str                      # e.g. "findings[2]" or "summary line 5"
    code: str                      # missing_locator | malformed_locator | unknown_finding | ...
    message: str
    severity: str                  # "error" forces a retry, "warning" is reported only
    text: str = ""
    item_id: str | None = None
    path: tuple = ()


@dataclass
class Downgrade:
    item: str
    from_level: str
    to_level: str
    reason: str
    text: str = ""
    item_id: str | None = None


@dataclass
class DroppedClaim:
    item: str
    text: str
    reason: str


@dataclass
class CriticVerdict:
    agent_name: str                # the reviewed agent, not the Critic
    passed: bool
    issues: list[CriticIssue]
    downgrades: list[Downgrade]
    output: dict[str, Any]         # adjusted copy: downgrades applied, dropped claims removed
    retry_instruction: str
    dropped: list[DroppedClaim] = field(default_factory=list)
    attempts: int = 1
    retries_exhausted: bool = False
    note: str = ""
    original: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("original")
        return payload


@dataclass
class LocatorCheck:
    kind: str | None               # "web" | "file" | None
    source: str                    # identity of the source, used to tell sources apart
    text: str
    problem: str | None = None


def as_output_dict(output: Any) -> dict[str, Any]:
    """An agent result as a plain dict, always a copy."""
    if is_dataclass(output) and not isinstance(output, type):
        return asdict(output)
    if isinstance(output, Mapping):
        return copy.deepcopy(dict(output))
    if hasattr(output, "model_dump"):
        return dict(output.model_dump())
    raise TypeError("Critic Agent expects a result dataclass or a dict")


def evidence_rank(level: Any) -> int | None:
    canonical = normalize_level(level)
    return EVIDENCE_ORDER.index(canonical) if canonical else None


def normalize_level(level: Any) -> str | None:
    wanted = str(level or "").strip().lower()
    return next((name for name in EVIDENCE_ORDER if name.lower() == wanted), None)


def _squash(value: Any) -> str:
    return " ".join(str(value or "").split())


def _first(item: Mapping[str, Any], keys: Iterable[str]) -> Any:
    return next((item[k] for k in keys if item.get(k) not in (None, "", [])), None)


def _valid_date(value: Any) -> bool:
    try:
        date.fromisoformat(str(value)[:10])
    except ValueError:
        return False
    return True


def check_locator(locator: Any, *, source_url: Any = None, retrieved_at: Any = None, file: Any = None) -> LocatorCheck:
    """Is this a usable locator: file + page/sheet/row, or URL + retrieval date."""
    position = ""
    if isinstance(locator, Mapping):
        source_url = _first(locator, URL_KEYS) or source_url
        retrieved_at = locator.get("retrieved_at") or retrieved_at
        file = _first(locator, FILE_KEYS) or file
        position = ", ".join(f"{k} {locator[k]}" for k in POSITION_KEYS if locator.get(k) not in (None, ""))
        locator = locator.get("locator") or position
    text = _squash(locator)
    if not text:
        return LocatorCheck(None, "", "", "locator is missing")

    url_match = URL_RE.search(text) or URL_RE.search(str(source_url or ""))
    if url_match:
        url = url_match.group(0).rstrip(".,;")
        parsed = urlparse(url)
        source = f"{parsed.netloc.lower().removeprefix('www.')}{parsed.path.rstrip('/')}"
        if "." not in parsed.netloc:
            return LocatorCheck("web", source, text, "URL is not a valid http(s) address")
        in_text = RETRIEVED_RE.search(text)
        retrieved = in_text.group(1) if in_text else retrieved_at
        if not retrieved:
            return LocatorCheck("web", source, text, "web locator has no retrieval date")
        if not _valid_date(retrieved):
            return LocatorCheck("web", source, text, "retrieval date is not a valid date")
        return LocatorCheck("web", source, text)

    file_match = FILE_RE.search(text)
    file_name = _squash(file) or (file_match.group(0) if file_match else "")
    source = Path(file_name).name.lower()
    if not file_name:
        return LocatorCheck("file", source, text, "locator names no source file or URL")
    if not (position or POSITION_RE.search(text)):
        return LocatorCheck("file", source, text, "locator has no page/sheet/row position")
    return LocatorCheck("file", source, text)


def _entry_check(entry: Any, parent: Mapping[str, Any]) -> LocatorCheck:
    """Check one citation entry. A plain string takes its URL, date and file from the parent item."""
    context = entry if isinstance(entry, Mapping) else parent
    return check_locator(
        entry.get("locator") or entry if isinstance(entry, Mapping) else entry,
        source_url=_first(context, URL_KEYS),
        retrieved_at=context.get("retrieved_at"),
        file=_first(context, FILE_KEYS),
    )


def finding_citations(finding: Mapping[str, Any]) -> list[LocatorCheck]:
    """Every citation a finding carries: its own locator plus any listed extra citations."""
    checks = []
    locator = finding.get("locator")
    if isinstance(locator, Mapping):  # a structured locator still inherits the finding's URL, date and file
        inherited = {k: finding[k] for k in (*URL_KEYS, *FILE_KEYS, "retrieved_at") if finding.get(k)}
        checks.append(_entry_check({**inherited, **locator}, finding))
    elif locator not in (None, ""):
        checks.append(_entry_check(locator, finding))
    for key in CITATION_LIST_KEYS:
        for entry in finding.get(key) or []:
            checks.append(_entry_check(entry, finding))
    return checks


def item_references(item: Mapping[str, Any]) -> list[tuple[str | None, Any]]:
    """What a synthesis item says it rests on, as (finding id, locator entry) pairs."""
    refs: list[tuple[str | None, Any]] = []
    for key in FINDING_ID_KEYS:
        refs.extend((str(v), None) for v in item.get(key) or [])
    if item.get("finding_id"):
        refs.append((str(item["finding_id"]), None))
    for key in LOCATOR_LIST_KEYS:
        refs.extend((None, v) for v in item.get(key) or [])
    if item.get("locator"):
        refs.append((None, item["locator"]))
    for key in CITATION_LIST_KEYS:
        for entry in item.get(key) or []:
            if isinstance(entry, Mapping) and (entry.get("finding_id") or (entry.get("id") and not entry.get("locator"))):
                refs.append((str(entry.get("finding_id") or entry["id"]), None))
            else:
                refs.append((None, entry))
    return refs


def _claim_text(item: Mapping[str, Any]) -> str:
    return _squash(_first(item, TEXT_KEYS))


def _item_id(item: Mapping[str, Any]) -> str | None:
    value = item.get("id") or item.get("code")
    return str(value) if value else None


def _label(path: tuple) -> str:
    if len(path) >= 2 and path[-2] == "line":
        return f"{'.'.join(str(p) for p in path[:-2])} line {path[-1] + 1}"
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


class _Known:
    """Findings a synthesis item may rest on: this output's own plus accepted earlier ones."""

    def __init__(self) -> None:
        self.by_id: dict[str, Mapping[str, Any]] = {}
        self.by_locator: dict[str, Mapping[str, Any]] = {}

    def add(self, finding: Mapping[str, Any]) -> None:
        finding_id = finding.get("id") or finding.get("finding_id")
        if finding_id:
            self.by_id[str(finding_id)] = finding
        locator = finding.get("locator")
        if locator and not isinstance(locator, Mapping):
            self.by_locator[_squash(locator)] = finding

    def __bool__(self) -> bool:
        return bool(self.by_id or self.by_locator)


def _source_of(finding: Mapping[str, Any]) -> str:
    return next((c.source for c in finding_citations(finding) if not c.problem and c.source), "")


def _synthesis_items(output: Mapping[str, Any]) -> list[tuple[tuple, Any]]:
    """(path, item) for every synthesis item; a text dossier is handled by the bullet check instead."""
    items: list[tuple[tuple, Any]] = []
    for key in SYNTHESIS_KEYS:
        value = output.get(key)
        if isinstance(value, list):
            items.extend(((key, i), entry) for i, entry in enumerate(value))
        elif isinstance(value, Mapping):
            nested = [k for k in DOSSIER_LIST_KEYS if isinstance(value.get(k), list)]
            for sub in nested:
                items.extend(((key, sub, i), entry) for i, entry in enumerate(value[sub]))
            if not nested and not any(isinstance(value.get(k), str) for k in DOSSIER_TEXT_KEYS):
                items.append(((key,), value))
    return items


def _text_blocks(output: Mapping[str, Any]) -> list[tuple[tuple, str]]:
    blocks: list[tuple[tuple, str]] = []
    for key in ("summary", "dossier"):
        value = output.get(key)
        if isinstance(value, str):
            blocks.append(((key,), value))
        elif isinstance(value, Mapping):
            blocks.extend(((key, sub), value[sub]) for sub in DOSSIER_TEXT_KEYS if isinstance(value.get(sub), str))
    return blocks


def _bullet_problem(body: str, known_locators: Iterable[str]) -> str | None:
    body = _squash(body)
    if any(locator in body for locator in known_locators):
        return None
    if URL_RE.search(body):
        return None if RETRIEVED_RE.search(body) else "cites a URL without a retrieval date"
    if FILE_RE.search(body) and POSITION_RE.search(body):
        return None
    return "carries no citation (source + locator)"


def _is_header(line: str) -> bool:
    return line.endswith(":") or line.startswith("#") or (line.startswith("**") and line.endswith("**"))


def _review_text(text: str, path: tuple, known_locators: list[str], issues: list[CriticIssue]) -> None:
    """Every bullet that states a finding must carry its citation (docs/architecture/02, StepSummary).

    Not checked: bullets in sections about the run itself (scope, confidence, gaps), bullets that say
    nothing was found, and bullets labelled as an assumption. A heading bullet is covered when a
    bullet nested under it carries a citation.
    """
    exempt = False
    bullets: list[tuple[int, int, str, str | None]] = []  # line number, indent, body, problem
    for number, raw in enumerate(text.splitlines()):
        line = raw.strip()
        bullet = BULLET_RE.match(line)
        if not bullet:
            if line and _is_header(line):
                exempt = bool(EXEMPT_HEADER_RE.search(line))
            continue
        body = bullet.group(1)
        claim = LABEL_RE.sub("", body, count=1)
        skip = exempt or NOT_A_CLAIM_RE.match(body) or NOTHING_FOUND_RE.match(body) or NOTHING_FOUND_RE.match(claim)
        indent = len(raw) - len(raw.lstrip())
        bullets.append((number, indent, body, None if skip else _bullet_problem(body, known_locators)))

    for position, (number, indent, body, problem) in enumerate(bullets):
        if not problem:
            continue
        children = []
        for _, child_indent, _, child_problem in bullets[position + 1:]:
            if child_indent <= indent:
                break
            children.append(child_problem)
        if children and not all(children):
            continue
        line_path = path + ("line", number)
        issues.append(CriticIssue(_label(line_path), "uncited_bullet", f"bullet {problem}", "error", body, None, line_path))


def _read_support_reply(reply: Any) -> tuple[bool | None, str]:
    """The model proposes; only a clear yes/no is used, anything else is ignored."""
    if isinstance(reply, bool):
        return reply, ""
    if isinstance(reply, Mapping) and isinstance(reply.get("supported"), bool):
        return reply["supported"], _squash(reply.get("reason"))
    return None, ""


def _apply_caps(item: dict[str, Any], label: str, caps: list[tuple[str, str]], downgrades: list[Downgrade]) -> None:
    current = normalize_level(item.get("evidence_level"))
    if current is None or not caps:
        return
    binding = [(cap, reason) for cap, reason in caps if EVIDENCE_ORDER.index(cap) < EVIDENCE_ORDER.index(current)]
    if not binding:
        return
    target = min((cap for cap, _ in binding), key=EVIDENCE_ORDER.index)
    item["evidence_level"] = target
    reason = "; ".join(reason for _, reason in binding)
    downgrades.append(Downgrade(label, current, target, reason, _claim_text(item), _item_id(item)))


def _corroborated(output: Mapping[str, Any], known: _Known) -> set[int]:
    """Findings grouped by a synthesis item together with a finding from a different source."""
    result: set[int] = set()
    for _, item in _synthesis_items(output):
        if not isinstance(item, Mapping):
            continue
        members = [known.by_id[fid] for fid, _ in item_references(item) if fid in known.by_id]
        if len({_source_of(f) for f in members} - {""}) >= 2:
            result.update(id(f) for f in members)
    return result


def _review_finding(
    finding: Any, path: tuple, corroborated: set[int], support_check: SupportCheck | None,
    issues: list[CriticIssue], downgrades: list[Downgrade],
) -> None:
    label = _label(path)
    if not isinstance(finding, dict):
        issues.append(CriticIssue(label, "malformed_item", "finding is not an object", "error", "", None, path))
        return
    text, item_id = _claim_text(finding), _item_id(finding)

    def error(code: str, message: str) -> None:
        issues.append(CriticIssue(label, code, message, "error", text, item_id, path))

    before = len(issues)
    if not text:
        error("empty_claim", "finding has no text")
    citations = finding_citations(finding)
    if not citations:
        error("missing_locator", "locator is missing")
    for citation in citations:
        if citation.problem:
            error("missing_locator" if citation.problem == "locator is missing" else "malformed_locator", citation.problem)
    if len(issues) > before:
        return

    if "evidence_level" not in finding or normalize_level(finding["evidence_level"]) is None:
        issues.append(CriticIssue(label, "unknown_evidence_level", "evidence_level is missing or not a known level", "warning", text, item_id, path))

    caps: list[tuple[str, str]] = []
    if any(c.kind == "web" for c in citations):
        tier = finding.get("trust_tier")
        if tier in LOW_TRUST_TIERS:
            caps.append(("Unverified", f"low source-trust tier ({tier})"))
        elif tier not in KNOWN_TRUST_TIERS:
            caps.append(("Interpreted", "web source without a known source-trust tier"))
        sample = finding.get("sample_size")
        backed = (
            len({c.source for c in citations}) >= 2
            or bool(finding.get("corroborated_by"))
            or (isinstance(sample, (int, float)) and sample >= 2)
            or id(finding) in corroborated
        )
        if not backed:
            caps.append(("Interpreted", "single web source, no corroboration"))

    snapshot = finding.get("snapshot") or finding.get("quote")
    if support_check and snapshot:
        try:
            supported, reason = _read_support_reply(support_check(text, str(snapshot), citations[0].text))
        except Exception as exc:  # the optional pass must never break the deterministic review
            supported, reason = None, ""
            issues.append(CriticIssue(label, "support_check_failed", f"support check raised {type(exc).__name__}", "warning", text, item_id, path))
        if supported is False:
            message = "support check doubts that the cited snapshot backs this claim" + (f": {reason}" if reason else "")
            issues.append(CriticIssue(label, "support_doubted", message, "warning", text, item_id, path))
            caps.append(("Unverified", message))
    _apply_caps(finding, label, caps, downgrades)


def _review_synthesis_item(item: Any, path: tuple, known: _Known, issues: list[CriticIssue], downgrades: list[Downgrade]) -> None:
    label = _label(path)
    if not isinstance(item, dict):
        issues.append(CriticIssue(label, "malformed_item", "item is not an object", "error", _squash(item), None, path))
        return
    text, item_id = _claim_text(item), _item_id(item)

    def report(code: str, message: str, severity: str = "error") -> None:
        issues.append(CriticIssue(label, code, message, severity, text, item_id, path))

    before = len(issues)
    references = item_references(item)
    if not references:
        report("no_evidence", "item references no finding")
    resolved: list[Mapping[str, Any]] = []
    for finding_id, entry in references:
        if finding_id is not None:
            if finding_id in known.by_id:
                resolved.append(known.by_id[finding_id])
            else:
                report("unknown_finding", f"references unknown finding {finding_id}")
            continue
        raw = entry.get("locator") if isinstance(entry, Mapping) else entry
        if raw and not isinstance(raw, Mapping) and _squash(raw) in known.by_locator:
            resolved.append(known.by_locator[_squash(raw)])  # the finding itself carries the file or URL
            continue
        check = _entry_check(entry, item)
        if check.problem:
            report("missing_locator" if check.problem == "locator is missing" else "malformed_locator", check.problem)
        elif check.text in known.by_locator:
            resolved.append(known.by_locator[check.text])
        elif known:
            report("unknown_locator", f"locator matches no known finding: {check.text}")
        else:
            report("unverified_reference", "no known findings were supplied to resolve this locator against", "warning")
    if any(i.severity == "error" for i in issues[before:]):
        return

    caps: list[tuple[str, str]] = []
    ranks = [r for r in (evidence_rank(f.get("evidence_level")) for f in resolved) if r is not None]
    if ranks:
        best = EVIDENCE_ORDER[max(ranks)]
        caps.append((best, f"no stronger than its strongest linked finding ({best})"))
    if len({id(f) for f in resolved}) == 1:
        sample = resolved[0].get("sample_size")
        if not (isinstance(sample, (int, float)) and sample >= 2):
            caps.append(("Interpreted", "rests on a single finding, no corroboration"))
    _apply_caps(item, label, caps, downgrades)


def _annotate_summary(output: dict[str, Any], downgrades: list[Downgrade], dropped: list[DroppedClaim], attempts: int) -> None:
    """Keep the step card honest: fix the levels it quotes and say what the Critic changed."""
    summary = output.get("summary")
    if not isinstance(summary, str) or not (downgrades or dropped):
        return
    lines = summary.splitlines()
    for downgrade in downgrades:
        for i, line in enumerate(lines):
            if downgrade.text and downgrade.text in _squash(line):
                lines[i] = re.sub(rf"\b{downgrade.from_level}\b", downgrade.to_level, line, count=1)
    lines.extend(["", "Critic review:"])
    for downgrade in downgrades:
        lines.append(f"- Downgraded {downgrade.item} from {downgrade.from_level} to {downgrade.to_level}: {downgrade.reason}.")
    for claim in dropped:
        lines.append(f"- Dropped after {attempts} attempt(s), no usable citation: \"{claim.text[:160]}\" ({claim.reason}).")
    output["summary"] = "\n".join(lines)


def build_retry_instruction(issues: list[CriticIssue]) -> str:
    """Text to append to the agent's task for an automatic retry; empty when nothing blocks."""
    errors = [i for i in issues if i.severity == "error"]
    if not errors:
        return ""
    lines = [
        f"Critic review: {len(errors)} claim(s) cannot go to PM review as written. Same scope, same task. "
        "For each one, find a citation or drop the claim. A citation needs a locator: file plus "
        "page/sheet/row for provided files, URL plus retrieval date for web sources."
    ]
    for issue in errors:
        quoted = f' "{issue.text[:160]}"' if issue.text else ""
        lines.append(f"- {issue.item}{quoted}: {issue.message}")
    return "\n".join(lines)


def review(
    output: Any,
    *,
    known_findings: Iterable[Any] | None = None,
    support_check: SupportCheck | None = None,
) -> CriticVerdict:
    """Review one agent output. The input is never mutated; `verdict.output` is the adjusted copy.

    `known_findings` are findings accepted in earlier steps, which a synthesis item may rest on.
    `support_check(claim, snapshot, locator)` is the optional model pass, off by default.
    """
    return _review(output, known_findings, support_check, [], 1)


def _review(
    output: Any,
    known_findings: Iterable[Any] | None,
    support_check: SupportCheck | None,
    dropped: list[DroppedClaim],
    attempts: int,
) -> CriticVerdict:
    original = as_output_dict(output)
    adjusted = copy.deepcopy(original)
    issues: list[CriticIssue] = []
    downgrades: list[Downgrade] = []

    findings = adjusted.get("findings") or []
    known = _Known()
    for finding in known_findings or []:
        known.add(as_output_dict(finding))
    for finding in findings:
        if isinstance(finding, Mapping):
            known.add(finding)

    corroborated = _corroborated(adjusted, known)
    for i, finding in enumerate(findings):
        _review_finding(finding, ("findings", i), corroborated, support_check, issues, downgrades)
    for path, item in _synthesis_items(adjusted):
        _review_synthesis_item(item, path, known, issues, downgrades)

    known_locators = [locator for locator in known.by_locator if len(locator) >= 6]
    known_locators += [f"[{finding_id}]" for finding_id in known.by_id]  # a dossier cites by marker, resolved under Sources
    for path, text in _text_blocks(adjusted):
        _review_text(text, path, known_locators, issues)
    summary = adjusted.get("summary")
    if isinstance(summary, Mapping):
        for key in SUMMARY_LIST_KEYS:
            for i, entry in enumerate(summary.get(key) or []):
                body = f"{_claim_text(entry)} {entry.get('locator') or entry.get('citation') or ''}" if isinstance(entry, Mapping) else str(entry)
                problem = _bullet_problem(body, known_locators)
                if problem:
                    path = ("summary", key, i)
                    issues.append(CriticIssue(_label(path), "uncited_bullet", f"bullet {problem}", "error", _squash(body), None, path))

    _annotate_summary(adjusted, downgrades, dropped, attempts)
    passed = not any(i.severity == "error" for i in issues)
    return CriticVerdict(
        agent_name=str(original.get("agent_name") or "unknown agent"),
        passed=passed,
        issues=issues,
        downgrades=downgrades,
        output=adjusted,
        retry_instruction=build_retry_instruction(issues),
        dropped=list(dropped),
        attempts=attempts,
        note="" if passed else "Unsupported claims found; the step goes back to the same agent before the PM sees it.",
        original=original,
    )


def _delete(root: dict[str, Any], path: tuple) -> None:
    if len(path) >= 2 and path[-2] == "line":
        parent, key = root, path[-3]
        for part in path[:-3]:
            parent = parent[part]
        lines = parent[key].splitlines()
        del lines[path[-1]]
        parent[key] = "\n".join(lines)
        return
    parent = root
    for part in path[:-1]:
        parent = parent[part]
    del parent[path[-1]]


def _prune(output: dict[str, Any], errors: list[CriticIssue]) -> list[DroppedClaim]:
    """Remove every item that has an error, and the references other items hold to dropped findings."""
    dropped: list[DroppedClaim] = []
    gone_ids: set[str] = set()
    gone_locators: set[str] = set()
    gone_texts: set[str] = set()
    paths: dict[tuple, list[CriticIssue]] = {}
    for issue in errors:
        paths.setdefault(issue.path, []).append(issue)

    for path, path_issues in paths.items():
        dropped.append(DroppedClaim(path_issues[0].item, path_issues[0].text, "; ".join(dict.fromkeys(i.message for i in path_issues))))
        if path[0] == "findings":
            finding = output["findings"][path[1]]
            if isinstance(finding, Mapping):
                gone_ids.update(str(v) for v in (finding.get("id"), finding.get("finding_id")) if v)
                gone_locators.update(_squash(v) for v in (finding.get("locator"),) if v and not isinstance(v, Mapping))
                gone_texts.update(v for v in (_claim_text(finding),) if v)
    for path in sorted(paths, key=lambda p: (isinstance(p[-1], int), p[-1] if isinstance(p[-1], int) else 0), reverse=True):
        _delete(output, path)

    for _, item in _synthesis_items(output):
        if not isinstance(item, dict):
            continue
        for key in FINDING_ID_KEYS:
            if isinstance(item.get(key), list):
                item[key] = [v for v in item[key] if str(v) not in gone_ids]
        for key in LOCATOR_LIST_KEYS:
            if isinstance(item.get(key), list):
                item[key] = [v for v in item[key] if _squash(v) not in gone_locators]
        for key in CITATION_LIST_KEYS:
            if isinstance(item.get(key), list):
                item[key] = [
                    v for v in item[key]
                    if not (isinstance(v, Mapping) and (str(v.get("finding_id") or v.get("id")) in gone_ids or _squash(v.get("locator")) in gone_locators))
                    and not (isinstance(v, str) and _squash(v) in gone_locators)
                ]
    for path, text in _text_blocks(output):
        kept = [line for line in text.splitlines() if not (BULLET_RE.match(line.strip()) and any(t in _squash(line) for t in gone_texts))]
        parent = output
        for part in path[:-1]:
            parent = parent[part]
        parent[path[-1]] = "\n".join(kept)
    return dropped


def drop_unsupported(
    verdict: CriticVerdict,
    *,
    known_findings: Iterable[Any] | None = None,
    support_check: SupportCheck | None = None,
) -> CriticVerdict:
    """Drop the claims that still fail and report them, instead of letting them through.

    Dropping a finding can leave a synthesis item without evidence, so the review repeats until
    nothing fails. The dropped claims are listed in `verdict.dropped` and in the summary.
    """
    known_findings = list(known_findings or [])
    raw = copy.deepcopy(verdict.original)
    dropped: list[DroppedClaim] = []
    final = verdict
    for _ in range(20):
        errors = [i for i in final.issues if i.severity == "error"]
        if not errors:
            break
        dropped.extend(_prune(raw, errors))
        final = _review(raw, known_findings, support_check, dropped, verdict.attempts)
    final.retries_exhausted = True
    final.note = (
        f"Retry budget exhausted after {verdict.attempts} attempt(s). {len(dropped)} unsupported claim(s) were "
        "dropped and are reported here; they were not passed through to PM review."
    )
    return final


def review_with_retries(
    run_agent: Callable[[str | None], Any],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    known_findings: Iterable[Any] | None = None,
    support_check: SupportCheck | None = None,
) -> CriticVerdict:
    """Run an agent, review it, and re-run it with the retry instruction while it fails.

    `run_agent(retry_instruction)` gets `None` on the first call and the Critic's instruction on each
    retry (append it to the agent's task; same agent, same scope). When the budget is used up the
    unsupported claims are dropped and reported. The step status is the caller's to change.
    """
    known_findings = list(known_findings or [])
    instruction: str | None = None
    verdict: CriticVerdict | None = None
    for attempt in range(1, max(0, max_retries) + 2):
        verdict = review(run_agent(instruction), known_findings=known_findings, support_check=support_check)
        verdict.attempts = attempt
        if verdict.passed:
            if attempt > 1:
                verdict.note = f"Passed on attempt {attempt} after an automatic Critic retry."
            return verdict
        instruction = verdict.retry_instruction
    assert verdict is not None
    return drop_unsupported(verdict, known_findings=known_findings, support_check=support_check)


def audit_events(verdict: CriticVerdict) -> list[dict[str, Any]]:
    """The verdict as `AuditEvent`-shaped dicts (docs/architecture/07); the caller stores them."""
    events = [
        {
            "entity_type": "finding" if d.item.startswith("findings") else d.item.split("[")[0].rstrip("s"),
            "entity_id": d.item_id or d.item,
            "actor": AGENT_NAME,
            "action": "evidence_level_downgraded",
            "before": {"evidence_level": d.from_level},
            "after": {"evidence_level": d.to_level},
            "rationale": d.reason,
        }
        for d in verdict.downgrades
    ]
    events.extend(
        {
            "entity_type": "step",
            "entity_id": c.item,
            "actor": AGENT_NAME,
            "action": "claim_dropped",
            "before": {"text": c.text},
            "after": None,
            "rationale": c.reason,
        }
        for c in verdict.dropped
    )
    return events


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review one agent result (JSON) with the Critic Agent")
    parser.add_argument("result_json", type=Path, help="an agent result, e.g. the --dry-run output of an agent")
    parser.add_argument("--known-findings", type=Path, help="JSON list of findings accepted in earlier steps")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    known = json.loads(args.known_findings.read_text(encoding="utf-8")) if args.known_findings else None
    verdict = review(json.loads(args.result_json.read_text(encoding="utf-8")), known_findings=known)
    print(json.dumps(verdict.to_dict(), indent=2, ensure_ascii=False))
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
