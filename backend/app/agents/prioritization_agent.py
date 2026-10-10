"""Prioritization Agent (stage 04).

Turns draft requirements and their accepted findings into a proposed `Score`: the composite from
docs/architecture/06-prioritization.md, every component with its weight and contribution, a
separate confidence value and a one-line rationale. All numbers are computed by code, no model is
involved. The agent proposes; it never sets a requirement's status, priority tier or scope.

    score = w_c * customer_relevance + w_b * business_signal + w_s * strategic_fit - w_e * effort_proxy
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

AGENT_NAME = "Prioritization Agent"
STAGE = 4

# Doc 06 fixes the four weights and the formula. It does not fix how each component is derived from
# its inputs, so the constants below are this agent's reading of the "Derived from" table. Like the
# default weights they are a defensible starting point, not tuned to any dataset.
CUSTOMER_PARTS = {"prevalence": 0.4, "severity": 0.3, "corroboration": 0.3}
BUSINESS_PARTS = {"option_uptake": 0.6, "competitor_gap": 0.4}
STRATEGIC_PARTS = {"program_theme": 0.6, "baseline_continuity": 0.4}
CONFIDENCE_PARTS = {"evidence_mix": 0.5, "source_independence": 0.5}

EVIDENCE_WEIGHT = {"Verified": 1.0, "Interpreted": 0.6, "Unverified": 0.3}
EFFORT_LEVELS = {"low": 0.05, "medium": 0.50, "high": 0.95}
EFFORT_ALIASES = {"med": "medium", "mid": "medium"}

CUSTOMER_SIGNALS = {"complaint", "unmet_need"}
NEED_SIGNALS = CUSTOMER_SIGNALS | {"competitor_advantage", "market_trend"}
CORROBORATION_TARGET = 3      # independent sources describing the need for full corroboration
COMPETITOR_GAP_TARGET = 3.0   # evidence-weighted competitor findings for a full coverage gap
CONTINUITY_TARGET = 2.0       # evidence-weighted baseline findings for full continuity
INDEPENDENCE_TARGET = 5       # independent sources for full source independence
MISSING_PENALTY = 0.10        # confidence lost per missing input

TIERS = ((0.65, "Tier 1 (must-have)"), (0.40, "Tier 2 (should-have)"), (float("-inf"), "Tier 3 (watch-list)"))
ANY_MARKET = {"", "ALL", "GLOBAL"}


@dataclass(frozen=True)
class ScoringWeights:
    customer_relevance: float = 0.40
    business_signal: float = 0.25
    strategic_fit: float = 0.15
    effort_proxy: float = 0.20
    version: str = "default"

    def vector(self) -> dict[str, float]:
        return {k: getattr(self, k) for k in ("customer_relevance", "business_signal", "strategic_fit", "effort_proxy")}

    def with_overrides(self, overrides: dict[str, float], version: str | None = None) -> "ScoringWeights":
        """A new weight vector for a PM nudge. Weights are used as given, not renormalized, and an
        unnamed vector gets a version derived from its values so every score names what it used."""
        unknown = set(overrides) - set(self.vector())
        if unknown:
            raise ValueError(f"unknown weight(s): {sorted(unknown)}")
        if any(float(v) < 0 for v in overrides.values()):
            raise ValueError("weights must not be negative")
        nudged = replace(self, **{k: float(v) for k, v in overrides.items()})
        if version is None and nudged.vector() != self.vector():
            digest = hashlib.sha256(json.dumps(nudged.vector(), sort_keys=True).encode("utf-8")).hexdigest()[:8]
            version = f"custom-{digest}"
        return replace(nudged, version=version or self.version)


@dataclass
class ScoreComponent:
    name: str
    value: float
    weight: float
    contribution: float                 # signed: effort_proxy subtracts
    inputs: list[dict[str, Any]]        # each sub-signal with its value, weight and basis
    finding_ids: list[str]


@dataclass
class RequirementScore:
    requirement_id: str
    requirement_code: str | None
    title: str
    customer_relevance: float
    business_signal: float
    strategic_fit: float
    effort_proxy: float
    effort_level: str
    confidence: float
    composite: float
    proposed_tier: str                  # a proposal for the PM, never written to the requirement
    weights: dict[str, float]
    weight_vector_version: str
    breakdown: list[ScoreComponent]
    confidence_inputs: list[dict[str, Any]]
    market_scores: dict[str, float]
    rationale: str
    missing: list[str]
    thin: list[str]
    finding_ids: list[str]
    citations: list[dict[str, Any]]
    evidence_citations: list[dict[str, Any]]   # raw sales/option rows read through knowledge/tools.py
    computed_by: str
    computed_at: str


@dataclass
class PrioritizationResult:
    agent_name: str
    vehicle_line: str
    market: str
    weights: dict[str, float]
    weight_vector_version: str
    themes: list[str]
    computed_at: str
    requirements_read: int
    findings_read: int
    scores: list[RequirementScore]
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


def source_key(finding: dict[str, Any]) -> str:
    cited = citation_of(finding) or {}
    return str(finding.get("source_id") or cited.get("source") or cited.get("locator") or "")


def tier_for(composite: float) -> str:
    return next(label for floor, label in TIERS if composite >= floor)


def compose(components: dict[str, float], weights: ScoringWeights) -> float:
    """The doc 06 formula, nothing else."""
    return (
        weights.customer_relevance * components["customer_relevance"]
        + weights.business_signal * components["business_signal"]
        + weights.strategic_fit * components["strategic_fit"]
        - weights.effort_proxy * components["effort_proxy"]
    )


def weighted(parts: dict[str, float], values: dict[str, float]) -> float:
    return round(sum(parts[name] * values[name] for name in parts), 4)


def evidence_weight(finding: dict[str, Any]) -> float:
    return EVIDENCE_WEIGHT.get(str(finding.get("evidence_level")), EVIDENCE_WEIGHT["Unverified"])


def in_market(finding: dict[str, Any], market: str) -> bool:
    return str(finding.get("market") or "").upper() in ANY_MARKET | {market.upper()}


def market_weights_from_sales(sales: list[dict[str, Any]], markets: list[str]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Share of the latest actual (non-forecast) sales volume per market, with the cited rows used.

    Returns no weights unless every market in scope has a cited row, so a partial picture is never
    passed off as a weighting.
    """
    latest: dict[str, dict[str, Any]] = {}
    for row in sales:
        market = str(row.get("market_code") or row.get("market") or "")
        if market not in markets or row.get("is_forecast") or not row.get("citation") or row.get("volume") is None:
            continue
        if market not in latest or int(row.get("year") or 0) > int(latest[market].get("year") or 0):
            latest[market] = row
    total = sum(float(row["volume"]) for row in latest.values())
    if set(latest) != set(markets) or total <= 0:
        return {}, []
    weights = {m: round(float(latest[m]["volume"]) / total, 4) for m in markets}
    return weights, [dict(latest[m]["citation"]) for m in markets]


def plain(value: Any) -> str:
    """Text of a field that may be a string or a cited statement ({"text": ...})."""
    return str(value.get("text") or "") if isinstance(value, dict) else str(value or "")


def prevalence_of(finding: dict[str, Any]) -> tuple[float, int] | None:
    """(share affected, sample it was measured on), or None when the finding carries neither form.

    Either an explicit `prevalence` with its `sample_size`, or the Customer Feedback Agent's
    `sample_size` cited comments out of `sample_base` comments in scope.
    """
    if finding.get("prevalence") is not None and (finding.get("sample_size") or 0) > 0:
        return float(finding["prevalence"]), int(finding["sample_size"])
    if finding.get("sample_size") is not None and (finding.get("sample_base") or 0) > 0:
        return min(finding["sample_size"] / finding["sample_base"], 1.0), int(finding["sample_base"])
    return None


def uptake_of(finding: dict[str, Any]) -> tuple[float, bool] | None:
    """(uptake 0..1, is it only a proxy), or None. A measured `uptake_pct` wins; otherwise the Sales &
    Portfolio Agent's standard-fitment share, which is a portfolio proxy and not a take rate."""
    if finding.get("uptake_pct") is not None:
        return float(finding["uptake_pct"]) / 100, False
    metrics = finding.get("metrics") or {}
    if metrics.get("metric") == "standard_fitment_share" and isinstance(metrics.get("share_pct"), (int, float)):
        return float(metrics["share_pct"]) / 100, True
    return None


def customer_relevance(findings: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]], list[str], list[str]]:
    """Prevalence normalized by sample size, sentiment severity and cross-source corroboration."""
    customer = [f for f in findings if f.get("signal_type") in CUSTOMER_SIGNALS]
    if not customer:
        return 0.0, [], ["no customer finding (complaint or unmet need) is linked"], []
    missing: list[str] = []

    sized = [(f, *measured) for f in customer if (measured := prevalence_of(f))]
    for f in customer:
        if prevalence_of(f) is None:
            missing.append(f"{f['id']} has no prevalence with a sample size, left out of prevalence")
    total_n = sum(n for _, _, n in sized)
    prevalence = sum(share * n for _, share, n in sized) / total_n if sized else 0.0

    with_sentiment = [f for f in customer if f.get("sentiment") is not None]
    for f in customer:
        if f not in with_sentiment:
            missing.append(f"{f['id']} has no sentiment, left out of severity")
    severity = (
        sum(max(0.0, -float(f["sentiment"])) for f in with_sentiment) / len(with_sentiment) if with_sentiment else 0.0
    )

    need = [f for f in findings if f.get("signal_type") in NEED_SIGNALS]
    sources = {source_key(f) for f in need}
    corroboration = min(len(sources) / CORROBORATION_TARGET, 1.0)

    values = {"prevalence": prevalence, "severity": severity, "corroboration": corroboration}
    inputs = [
        {"name": "prevalence", "value": round(prevalence, 4), "weight": CUSTOMER_PARTS["prevalence"],
         "basis": f"sample-size-weighted share affected, n={total_n}", "finding_ids": [f["id"] for f, _, _ in sized]},
        {"name": "severity", "value": round(severity, 4), "weight": CUSTOMER_PARTS["severity"],
         "basis": "mean negative sentiment of the customer findings", "finding_ids": [f["id"] for f in with_sentiment]},
        {"name": "corroboration", "value": round(corroboration, 4), "weight": CUSTOMER_PARTS["corroboration"],
         "basis": f"{len(sources)} independent source(s) of {CORROBORATION_TARGET}", "finding_ids": [f["id"] for f in need]},
    ]
    return weighted(CUSTOMER_PARTS, values), inputs, missing, [f["id"] for f in need]


def business_signal(
    findings: list[dict[str, Any]], options: list[dict[str, Any]], thin: list[str]
) -> tuple[float, list[dict[str, Any]], list[str], list[str]]:
    """Option uptake plus competitor-coverage gap. A sellability proxy, not a cost model."""
    missing: list[str] = []
    measured = [(f, uptake_of(f)) for f in findings if f.get("signal_type") == "business_signal"]
    uptake_findings = [f for f, value in measured if value]
    uptake = sum(value[0] for _, value in measured if value) / len(uptake_findings) if uptake_findings else 0.0
    thin.extend(f"{f['id']}: uptake is the standard-fitment share, a portfolio proxy, not a measured take rate"
                for f, value in measured if value and value[1])
    if not uptake_findings:
        context = f"; {len(options)} cited option row(s) show availability only, not uptake" if options else ""
        missing.append(f"no option uptake % finding from the Sales & Portfolio Agent{context}")

    competitor = [f for f in findings if f.get("signal_type") == "competitor_advantage"]
    gap = min(sum(evidence_weight(f) for f in competitor) / COMPETITOR_GAP_TARGET, 1.0)
    if not competitor:
        missing.append("no competitor finding, competitor-coverage gap unknown")

    values = {"option_uptake": min(max(uptake, 0.0), 1.0), "competitor_gap": gap}
    inputs = [
        {"name": "option_uptake", "value": round(values["option_uptake"], 4), "weight": BUSINESS_PARTS["option_uptake"],
         "basis": "mean uptake % of the related option", "finding_ids": [f["id"] for f in uptake_findings]},
        {"name": "competitor_gap", "value": round(gap, 4), "weight": BUSINESS_PARTS["competitor_gap"],
         "basis": f"{len(competitor)} competitor finding(s), weighted by evidence level, of {COMPETITOR_GAP_TARGET:g}",
         "finding_ids": [f["id"] for f in competitor]},
    ]
    return weighted(BUSINESS_PARTS, values), inputs, missing, [f["id"] for f in uptake_findings + competitor]


def strategic_fit(requirement: dict[str, Any], findings: list[dict[str, Any]], themes: list[str]) -> tuple[float, list[dict[str, Any]], list[str], list[str]]:
    """PM-stated program themes plus continuity with the previous-generation baseline."""
    missing: list[str] = []
    own = {str(t).strip().lower() for t in requirement.get("themes") or []}
    text = f"{requirement.get('title', '')} {plain(requirement.get('description'))}".lower()
    matched = [t for t in themes if t.strip().lower() in own or t.strip().lower() in text]
    if not themes:
        missing.append("no program themes stated by the PM, theme fit unknown")

    baseline = [f for f in findings if f.get("signal_type") == "strategic_continuity"]
    continuity = min(sum(evidence_weight(f) for f in baseline) / CONTINUITY_TARGET, 1.0)
    if not baseline:
        missing.append("no previous-generation baseline finding, continuity unknown")

    values = {"program_theme": 1.0 if matched else 0.0, "baseline_continuity": continuity}
    inputs = [
        {"name": "program_theme", "value": values["program_theme"], "weight": STRATEGIC_PARTS["program_theme"],
         "basis": "PM input: matches " + ", ".join(f"'{t}'" for t in matched) if matched else "PM input: no stated theme matched",
         "finding_ids": []},
        {"name": "baseline_continuity", "value": round(continuity, 4), "weight": STRATEGIC_PARTS["baseline_continuity"],
         "basis": f"{len(baseline)} baseline finding(s), weighted by evidence level, of {CONTINUITY_TARGET:g}",
         "finding_ids": [f["id"] for f in baseline]},
    ]
    return weighted(STRATEGIC_PARTS, values), inputs, missing, [f["id"] for f in baseline]


def effort_proxy(requirement: dict[str, Any]) -> tuple[float, str, list[dict[str, Any]], list[str]]:
    raw = str(requirement.get("effort_proxy") or "").strip().lower()
    level = EFFORT_ALIASES.get(raw, raw)
    missing: list[str] = []
    if level not in EFFORT_LEVELS:
        level = "medium"
        missing.append("no effort estimate (low/medium/high) on the requirement, medium assumed until the PM sets it")
    basis = str(requirement.get("effort_reason") or "coarse low/medium/high heuristic, PM-editable")
    inputs = [{"name": "effort_level", "value": EFFORT_LEVELS[level], "weight": 1.0, "basis": f"{level}: {basis}", "finding_ids": []}]
    return EFFORT_LEVELS[level], level, inputs, missing


def score_requirement(
    requirement: dict[str, Any],
    findings: list[dict[str, Any]],
    weights: ScoringWeights,
    themes: list[str],
    scope_market: str,
    sales: list[dict[str, Any]],
    options: list[dict[str, Any]],
    computed_at: str,
    unresolved: list[str] | None = None,
) -> RequirementScore:
    """Score one requirement from the citable, in-scope findings linked to it.

    `unresolved` are links that could not be followed; they count as missing inputs like any other.
    """
    missing: list[str] = list(unresolved or [])
    thin: list[str] = []
    evidence_citations: list[dict[str, Any]] = [dict(o["citation"]) for o in options if o.get("citation")]

    markets = [m for m in requirement.get("markets") or [scope_market] if str(m).upper() not in ANY_MARKET]
    market_scores: dict[str, float] = {}
    if len(markets) > 1:
        market_weights, sales_citations = market_weights_from_sales(sales, markets)
        if not market_weights:
            market_weights = {m: round(1 / len(markets), 4) for m in markets}
            missing.append("no cited sales volume for every market in scope, markets weighted equally")
        evidence_citations.extend(sales_citations)
        customer_value, customer_inputs, customer_ids = 0.0, [], []
        for m in markets:
            value, inputs, notes, ids = customer_relevance([f for f in findings if in_market(f, m)])
            market_scores[m] = value
            customer_value += market_weights[m] * value
            customer_inputs.append({"name": f"market {m}", "value": value, "weight": market_weights[m],
                                    "basis": "customer relevance within this market", "finding_ids": ids, "inputs": inputs})
            # finding-level notes name their finding; only the market-level one needs the market
            missing.extend(f"{m}: {n}" if n.startswith("no customer finding") else n for n in notes)
            customer_ids.extend(ids)
        customer_value = round(customer_value, 4)
    else:
        customer_value, customer_inputs, notes, customer_ids = customer_relevance(findings)
        missing.extend(notes)
        if markets:
            thin.append(f"evidence covers {markets[0]} only")

    business_value, business_inputs, notes, business_ids = business_signal(findings, options, thin)
    missing.extend(notes)
    strategic_value, strategic_inputs, notes, strategic_ids = strategic_fit(requirement, findings, themes)
    missing.extend(notes)
    effort_value, effort_level, effort_inputs, notes = effort_proxy(requirement)
    missing.extend(notes)
    missing = list(dict.fromkeys(missing))

    for f in findings:
        if f.get("evidence_level") not in EVIDENCE_WEIGHT:
            missing.append(f"{f['id']} has no evidence level, counted as Unverified")
        elif f.get("evidence_level") != "Verified":
            thin.append(f"{f['id']} is {f['evidence_level']}, treat as an assumption until corroborated")
        thin.extend(f"{f['id']}: {a}" for a in f.get("assumptions") or [])

    values = {"customer_relevance": customer_value, "business_signal": business_value,
              "strategic_fit": strategic_value, "effort_proxy": effort_value}
    vector = weights.vector()
    parts = {"customer_relevance": (customer_inputs, customer_ids), "business_signal": (business_inputs, business_ids),
             "strategic_fit": (strategic_inputs, strategic_ids), "effort_proxy": (effort_inputs, [])}
    breakdown = [
        ScoreComponent(
            name=name,
            value=values[name],
            weight=vector[name],
            contribution=round((-1 if name == "effort_proxy" else 1) * vector[name] * values[name], 4),
            inputs=parts[name][0],
            finding_ids=list(dict.fromkeys(parts[name][1])),
        )
        for name in vector
    ]
    composite = round(compose(values, weights), 4)

    sources = {source_key(f) for f in findings}
    mix = sum(evidence_weight(f) for f in findings) / len(findings)
    independence = min(len(sources) / INDEPENDENCE_TARGET, 1.0)
    penalty = MISSING_PENALTY * len(missing)
    confidence = round(max(0.0, weighted(CONFIDENCE_PARTS, {"evidence_mix": mix, "source_independence": independence}) - penalty), 4)
    confidence_inputs = [
        {"name": "evidence_mix", "value": round(mix, 4), "weight": CONFIDENCE_PARTS["evidence_mix"],
         "basis": "mean evidence level (Verified 1.0, Interpreted 0.6, Unverified 0.3)"},
        {"name": "source_independence", "value": round(independence, 4), "weight": CONFIDENCE_PARTS["source_independence"],
         "basis": f"{len(sources)} independent source(s) of {INDEPENDENCE_TARGET}"},
        {"name": "missing_inputs", "value": round(-penalty, 4), "weight": 1.0,
         "basis": f"{len(missing)} missing input(s) at -{MISSING_PENALTY:.2f} each"},
    ]

    tier = tier_for(composite)
    rationale = (
        f"{len(findings)} cited finding(s) from {len(sources)} independent source(s): customer relevance "
        f"{customer_value:.2f}, business signal {business_value:.2f}, strategic fit {strategic_value:.2f}, "
        f"{effort_level} effort; composite {composite:.2f} proposes {tier} at confidence {confidence:.2f}"
        + (f", {len(missing)} input(s) missing." if missing else ".")
    )
    return RequirementScore(
        requirement_id=str(requirement["id"]),
        requirement_code=requirement.get("code"),
        title=str(requirement.get("title") or ""),
        customer_relevance=customer_value,
        business_signal=business_value,
        strategic_fit=strategic_value,
        effort_proxy=effort_value,
        effort_level=effort_level,
        confidence=confidence,
        composite=composite,
        proposed_tier=tier,
        weights=vector,
        weight_vector_version=weights.version,
        breakdown=breakdown,
        confidence_inputs=confidence_inputs,
        market_scores=market_scores,
        rationale=rationale,
        missing=missing,
        thin=list(dict.fromkeys(thin)),
        finding_ids=[f["id"] for f in findings],
        citations=[citation_of(f) for f in findings],
        evidence_citations=evidence_citations,
        computed_by=AGENT_NAME,
        computed_at=computed_at,
    )


def build_result(
    vehicle_line: str,
    market: str,
    requirements: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    *,
    weights: ScoringWeights | None = None,
    themes: list[str] | None = None,
    sales: list[dict[str, Any]] | None = None,
    options: list[dict[str, Any]] | None = None,
) -> PrioritizationResult:
    """Score every draft requirement from the findings accepted in earlier steps.

    `findings` are plain dicts (id, locator, source, signal_type, evidence_level, sentiment,
    sample_size, prevalence, uptake_pct, market, assumptions). `sales` and `options` are cited rows
    from `knowledge/tools.py` (see `load_sales` and `load_options`); options carry a `requirement_id`.
    """
    weights = weights or ScoringWeights()
    themes = [t for t in themes or [] if t and t.strip()]
    computed_at = datetime.now(timezone.utc).isoformat()
    skipped: list[dict[str, str]] = []

    by_id: dict[str, dict[str, Any]] = {}
    for finding in findings:
        cited = citation_of(finding)
        if cited is None:
            skipped.append({"item": str(finding.get("id") or finding.get("text") or "finding")[:80],
                            "reason": "finding has no id or locator and cannot be cited"})
            continue
        by_id[cited["finding_id"]] = {**finding, "id": cited["finding_id"]}

    scores: list[RequirementScore] = []
    for requirement in requirements:
        label = str(requirement.get("code") or requirement.get("id"))
        linked: list[dict[str, Any]] = []
        notes: list[str] = []
        for finding_id in dict.fromkeys(str(i) for i in requirement.get("linked_finding_ids") or []):
            finding = by_id.get(finding_id)
            if finding is None:
                notes.append(f"linked finding {finding_id} was not passed in as accepted evidence")
            elif finding.get("out_of_scope_reason"):
                skipped.append({"item": finding_id, "reason": f"out of scope for {label}: {finding['out_of_scope_reason']}"})
            else:
                linked.append(finding)
        if not linked:
            skipped.append({"item": label, "reason": "no citable in-scope finding is linked, so no score is proposed"})
            continue
        score = score_requirement(
            requirement, linked, weights, themes, market, sales or [],
            [o for o in options or [] if str(o.get("requirement_id")) == str(requirement["id"])], computed_at, notes,
        )
        scores.append(score)

    scores.sort(key=lambda s: s.composite, reverse=True)
    summary = summarize(vehicle_line, market, weights, themes, len(requirements), len(by_id), scores, skipped)
    return PrioritizationResult(
        agent_name=AGENT_NAME,
        vehicle_line=vehicle_line,
        market=market,
        weights=weights.vector(),
        weight_vector_version=weights.version,
        themes=themes,
        computed_at=computed_at,
        requirements_read=len(requirements),
        findings_read=len(by_id),
        scores=scores,
        skipped=skipped,
        summary=summary,
    )


def summarize(
    vehicle_line: str,
    market: str,
    weights: ScoringWeights,
    themes: list[str],
    requirements_read: int,
    findings_read: int,
    scores: list[RequirementScore],
    skipped: list[dict[str, str]],
) -> str:
    vector = ", ".join(f"{name} {value:.2f}" for name, value in weights.vector().items())
    lines = [
        f"{AGENT_NAME} looked at {requirements_read} draft requirement(s) and {findings_read} citable finding(s) "
        f"for {vehicle_line} / {market}.",
        f"Weights ({weights.version}): {vector}. Program themes: {', '.join(themes) if themes else 'none stated'}.",
        "Scores are computed by code and are a proposal: status, priority tier and scope stay with the PM.",
        "",
        "Proposed scores:",
    ]
    for score in scores:
        parts = "; ".join(f"{c.name} {c.value:.2f} x {c.weight:.2f} = {c.contribution:+.2f}" for c in score.breakdown)
        cites = "; ".join(cite_text(c) for c in score.citations)
        cites += "".join(f"; {c.get('kind', 'evidence')} row: {c.get('file', '')}, {c.get('locator', '')}" for c in score.evidence_citations)
        lines.append(
            f"- {score.requirement_code or score.requirement_id} {score.title}: {score.composite:.2f}, "
            f"{score.proposed_tier}, confidence {score.confidence:.2f}. {parts}. {score.rationale} ({cites})"
        )
    if not scores:
        lines.append("- No score was proposed.")
    lines.extend(["", "Confidence and gaps:"])
    for score in scores:
        label = score.requirement_code or score.requirement_id
        lines.extend(f"- {label}: missing: {note}" for note in score.missing)
        lines.extend(f"- {label}: thin: {note}" for note in score.thin)
    lines.extend(f"- Skipped {item['item']}: {item['reason']}" for item in skipped)
    if lines[-1] == "Confidence and gaps:":
        lines.append("- No missing inputs.")
    return "\n".join(lines)


# ---------------------------------------------------------------- optional loaders and storage

def _hit_citation(hit: Any) -> dict[str, Any]:
    return asdict(hit.citation)


def load_sales(vehicle_line: str, markets: list[str]) -> list[dict[str, Any]]:
    """Cited sales rows through the knowledge layer, for market weighting. Needs the database."""
    from app.knowledge import tools

    rows = []
    for market in markets:
        rows.extend({**hit.meta, "citation": _hit_citation(hit)} for hit in tools.get_sales(line=vehicle_line, market=market))
    return rows


def load_options(vehicle_line: str, requirement_id: str, text: str, limit: int = 5) -> list[dict[str, Any]]:
    """Cited option rows related to a requirement. Availability only: the data holds no uptake %."""
    from app.knowledge import tools

    return [
        {"requirement_id": requirement_id, "name": hit.text, "availability": hit.meta.get("availability"),
         "citation": _hit_citation(hit)}
        for hit in tools.get_options(line=vehicle_line, text=text, limit=limit)
    ]


def require_psycopg() -> Any:
    if psycopg is None:
        raise RuntimeError("psycopg is not installed. Run `pip install -e backend`.")
    return psycopg


def ensure_step(conn: Any, run_id: str | None, step_id: str | None, summary: str) -> str | None:
    if step_id:
        conn.execute(
            "update public.step set status = 'awaiting_review', human_readable_summary = %s where id = %s",
            (summary, step_id),
        )
        return step_id
    if not run_id:
        return None
    return conn.execute(
        "insert into public.step (run_id, agent_name, stage, status, human_readable_summary, launched_by, launched_at, position) "
        "values (%s, %s, %s, 'awaiting_review', %s, %s, now(), "
        "(select coalesce(max(position), 0) + 1 from public.step where run_id = %s)) returning id",
        (run_id, AGENT_NAME, STAGE, summary, AGENT_NAME, run_id),
    ).fetchone()[0]


def store_result(conn: Any, result: PrioritizationResult, run_id: str | None, step_id: str | None) -> None:
    """Append one new `score` row per requirement (never an overwrite) and leave the step in review.

    The requirement row itself is not touched. The weight vector and the breakdown go to the audit
    event and the step's output refs, because `score` only has a column for the vector's version.
    """
    with conn.transaction():
        stored_step_id = ensure_step(conn, run_id, step_id, result.summary)
        refs = []
        for score in result.scores:
            score_id = conn.execute(
                "insert into public.score (requirement_id, customer_relevance, business_signal, strategic_fit, effort_proxy, "
                "confidence, composite, weight_vector_version, rationale, computed_by, step_id) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                (
                    score.requirement_id,
                    score.customer_relevance,
                    score.business_signal,
                    score.strategic_fit,
                    score.effort_proxy,
                    score.confidence,
                    score.composite,
                    score.weight_vector_version,
                    score.rationale,
                    AGENT_NAME,
                    stored_step_id,
                ),
            ).fetchone()[0]
            detail = {
                "composite": score.composite,
                "proposed_tier": score.proposed_tier,
                "confidence": score.confidence,
                "weights": score.weights,
                "weight_vector_version": score.weight_vector_version,
                "breakdown": [asdict(c) for c in score.breakdown],
                "finding_ids": score.finding_ids,
            }
            conn.execute(
                "insert into public.audit_event (entity_type, entity_id, actor, action, after, rationale) "
                "values ('score', %s, %s, 'scored', %s::jsonb, %s)",
                (score_id, AGENT_NAME, json.dumps(detail), score.rationale),
            )
            refs.append({"type": "score", "id": str(score_id), "requirement_id": score.requirement_id,
                         "weights": score.weights, "citations": score.citations})
        if stored_step_id:
            conn.execute(
                "update public.step set structured_output_refs = %s::jsonb where id = %s",
                (json.dumps(refs), stored_step_id),
            )


def parse_weight(value: str) -> tuple[str, float]:
    name, _, number = value.partition("=")
    return name.strip(), float(number)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Prioritization Agent")
    parser.add_argument("--input-json", type=Path, required=True,
                        help="accepted output of earlier steps: {requirements, findings, themes?, sales?, options?}")
    parser.add_argument("--vehicle-line", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--weight", action="append", default=[], metavar="NAME=VALUE",
                        help="override one weight, e.g. business_signal=0.30; repeatable")
    parser.add_argument("--weights-version", help="name for the weight vector used")
    parser.add_argument("--theme", action="append", default=[], help="PM-stated program theme; repeatable")
    parser.add_argument("--sales-from-db", action="store_true", help="read sales volumes through the knowledge layer")
    parser.add_argument("--run-id")
    parser.add_argument("--step-id")
    parser.add_argument("--dry-run", action="store_true", help="print JSON result instead of writing scores")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("Prioritization Agent input JSON must be an object")
    requirements = payload.get("requirements", [])
    weights = ScoringWeights().with_overrides(dict(parse_weight(w) for w in args.weight), args.weights_version)

    sales = payload.get("sales", [])
    if args.sales_from_db:
        markets = sorted({m for r in requirements for m in r.get("markets") or [args.market]})
        sales = load_sales(args.vehicle_line, markets)

    result = build_result(
        args.vehicle_line,
        args.market,
        requirements,
        payload.get("findings", []),
        weights=weights,
        themes=args.theme or payload.get("themes", []),
        sales=sales,
        options=payload.get("options", []),
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
