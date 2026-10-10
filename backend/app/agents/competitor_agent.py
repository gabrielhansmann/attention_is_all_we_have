"""Competitor Agent.

The agent goes from one BMW anchor vehicle to a comparable rival set and turns cited web evidence
into `competitor_advantage` findings, following docs/architecture/10-competitor-benchmarking.md:
anchor profile -> segment bands -> long-list -> shortlist -> evidence -> relative comparison.

The model only extracts cited attributes and observations. Bands, filters, similarity, deltas and
the finding text are computed in code, and every value points at a search citation. The PM review
boundary stays intact: the agent only produces findings and a step summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from app.agents.market_trend_agent import (
    EMBED_MODEL,
    MAX_EMBED_CHARS,
    RESEARCH_MODEL,
    SourceDoc,
    evidence_from_trust,
    infer_trust_tier,
    load_seed_sources,
    require_openai,
    require_psycopg,
    sources_from_web_search_response,
    stable_locator,
    upsert_source,
    vec,
)

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIClient

AGENT_NAME = "Competitor Agent"
ALL = "ALL"

# Presumed series per line (docs/architecture/00-overview.md says to confirm before presenting as fact).
LINE_LABELS = {
    "F70": "1 Series (F70)",
    "G60": "5 Series (G60)",
    "G68": "5 Series long wheelbase (G68)",
    "G70": "7 Series (G70)",
}

# Default bands around the anchor. Placeholders to calibrate; the PM can override any of them.
PRICE_BAND = (-0.15, 0.25)
RANGE_BAND = 0.20
LENGTH_BAND = 0.05
SOFT_WEIGHTS = {"powertrain": 0.3, "range": 0.3, "length": 0.2, "equipment": 0.2}

BODY_CLASSES = {
    "saloon": "saloon/estate", "sedan": "saloon/estate", "limousine": "saloon/estate", "estate": "saloon/estate",
    "touring": "saloon/estate", "wagon": "saloon/estate", "liftback": "saloon/estate", "fastback": "saloon/estate",
    "suv": "suv", "crossover": "suv", "sav": "suv",
    "hatchback": "hatchback", "coupe": "coupe/convertible", "convertible": "coupe/convertible", "mpv": "mpv", "van": "mpv",
}

TRUST_ORDER = {"oem": 0, "trade_press": 1, "forum_social": 2}
VOICE_TYPE_BY_TIER = {"trade_press": "expert", "forum_social": "owner"}
VOICE_LABEL = {"expert": "Expert reviews", "owner": "Owner reports"}
EQUIPMENT_RANK = {"standard": 2, "optional": 1, "available": 1, "not_available": 0, "unavailable": 0, "not available": 0}

HIGHER_IS_BETTER = {
    "range", "boot_volume", "charging_power", "rear_legroom", "headroom", "screen_size", "towing_capacity",
    "battery_capacity", "power", "warranty",
}
LOWER_IS_BETTER = {"price", "consumption", "charging_time", "acceleration", "turning_circle", "noise", "cabin_noise", "weight"}
PROFILE_ONLY = {"price", "body_style", "seats", "powertrain", "equipment"}  # drive the bracket, not a comparison

MIN_MENTIONS = 3          # doc 10 leaves n open; fewer mentions on either side is "insufficient data"
VOICE_DELTA = 0.3         # sentiment-balance gap that counts as a clear delta
SPEC_DELTA_PCT = 2.0      # spec gap that counts as a clear delta

# Narrower than the trend agent's pattern: review text says "fine" and "mandatory" about comfort, not law.
OUT_OF_SCOPE_RE = re.compile(
    r"\b(price|prices|priced|pricing|msrp|discount|lease|leasing|cost|costs|margin|tax credit|emissions?|type approval|"
    r"homologation|regulation|regulatory|compliance|safety standard|crash test|ncap|recall|supplier)\b",
    re.IGNORECASE,
)
OUT_OF_SCOPE_REASON = "pricing/regulatory/engineering-internal topic; route to out-of-scope bin"
VOICE_ASSUMPTION = (
    "Mentions and sentiment are model-extracted observations from cited search summaries, not counts of raw posts or reviews."
)


@dataclass
class ProfileAttribute:
    attribute: str
    value: Any            # None when it could not be sourced; never guessed
    unit: str | None = None
    standard: str | None = None   # measurement standard, e.g. WLTP | EPA | CLTC
    source_url: str | None = None
    locator: str | None = None
    trust_tier: str | None = None


@dataclass
class VehicleProfile:
    label: str
    make: str
    model: str
    generation: str | None
    variant: str | None
    is_anchor: bool
    market: str
    attributes: list[ProfileAttribute] = field(default_factory=list)

    def get(self, attribute: str) -> Any:
        return next((a.value for a in self.attributes if a.attribute == attribute and a.value is not None), None)


@dataclass
class Criterion:
    attribute: str
    kind: str             # hard | soft
    min: float | None = None
    max: float | None = None
    equals: Any = None
    weight: float = 0.0
    set_by: str = "default"   # default | pm


@dataclass
class SegmentDefinition:
    anchor: str
    market: str
    criteria: list[Criterion]


@dataclass
class Candidate:
    profile: VehicleProfile
    status: str                      # in_band | excluded
    reasons: list[str] = field(default_factory=list)
    unknown_attributes: list[str] = field(default_factory=list)   # could not be checked, shown as such
    needs_pm_check: bool = False     # a hard criterion could not be checked
    similarity: float | None = None
    shortlisted: bool = False


@dataclass
class CompetitorSet:
    anchor: str
    market: str
    rivals: list[str]
    similarity_scores: dict[str, float | None]
    selected_by: str                 # similarity | pm


@dataclass
class ComparisonCell:
    rival: str
    aspect: str
    source_type: str                 # spec | expert | owner
    anchor_value: Any
    rival_value: Any
    unit: str | None
    delta: float | None
    n_anchor: int
    n_rival: int
    evidence_level: str
    status: str                      # rival_leads | anchor_leads | parity | insufficient_data | not_comparable | direction_unknown
    note: str = ""
    citations: list[dict[str, str]] = field(default_factory=list)


@dataclass
class CompetitorFinding:
    source_url: str
    title: str
    retrieved_at: str
    locator: str
    text: str
    signal_type: str
    evidence_level: str
    market: str
    vehicle_line: str
    sentiment: float | None
    sample_size: int | None
    trust_tier: str
    snapshot: str
    rival: str
    aspect: str
    source_type: str
    citations: list[dict[str, str]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    out_of_scope_reason: str | None = None


@dataclass
class CompetitorResult:
    agent_name: str
    vehicle_line: str
    market: str
    query: str
    retrieved_at: str
    sources_read: int
    anchor: VehicleProfile | None
    segment: SegmentDefinition | None
    long_list: list[Candidate]
    competitor_set: CompetitorSet | None
    comparison: list[ComparisonCell]
    findings: list[CompetitorFinding]
    skipped: list[dict[str, str]]
    summary: str


def scope_label(value: str | None) -> str:
    """`ALL`, empty or None means no filter."""
    if value is None or not str(value).strip() or str(value).strip().upper() == ALL:
        return ALL
    return str(value).strip()


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _fmt(value: Any) -> str:
    number = _num(value)
    if number is None:
        return str(value).replace("_", " ")
    return f"{number:,.0f}" if number == int(number) else f"{number:,.2f}".rstrip("0").rstrip(".")


def weakest_tier(tiers: list[str]) -> str:
    return max(tiers or ["forum_social"], key=lambda t: TRUST_ORDER.get(t, 2))


def citation(doc: SourceDoc, side: str) -> dict[str, str]:
    return {
        "side": side,
        "url": doc.url,
        "title": doc.title,
        "retrieved_at": doc.retrieved_at,
        "locator": stable_locator(doc),
        "trust_tier": infer_trust_tier(doc),
        "snippet": doc.snippet,
    }


def load_competitor_draft(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Competitor Agent draft JSON must be an object")
    for key in ("candidates", "observations", "skipped"):
        payload.setdefault(key, [])
    return payload


def cited_doc(docs: list[SourceDoc], source_index: Any) -> SourceDoc | None:
    try:
        index = int(source_index)
    except (TypeError, ValueError):
        return None
    return docs[index - 1] if 1 <= index <= len(docs) else None


# ---------------------------------------------------------------- stage 1: anchor

def build_profile(
    item: dict[str, Any], docs: list[SourceDoc], market: str, skipped: list[dict[str, str]], *,
    is_anchor: bool = False, variant: str | None = None,
) -> VehicleProfile:
    """A vehicle profile whose every value is individually cited. An attribute without a valid
    citation is kept as `None`, so it shows as missing instead of passing a filter."""
    make = str(item.get("make") or "").strip()
    model = str(item.get("model") or "").strip()
    variant = variant or item.get("variant")
    label = " ".join(part for part in (make, model, str(variant or "").strip()) if part)
    attributes = []
    for raw in item.get("attributes") or []:
        name = _norm(raw.get("attribute")).replace(" ", "_")
        if not name:
            continue
        doc = cited_doc(docs, raw.get("source_index"))
        if doc is None or raw.get("value") is None:
            if raw.get("value") is not None:
                skipped.append({"source": "unknown", "reason": f"{label}: {name} had no valid citation and is treated as missing"})
            attributes.append(ProfileAttribute(attribute=name, value=None))
            continue
        attributes.append(ProfileAttribute(
            attribute=name,
            value=raw["value"],
            unit=raw.get("unit"),
            standard=raw.get("standard"),
            source_url=doc.url,
            locator=stable_locator(doc),
            trust_tier=infer_trust_tier(doc),
        ))
    return VehicleProfile(
        label=label, make=make, model=model, generation=item.get("generation"), variant=variant,
        is_anchor=is_anchor, market=market, attributes=attributes,
    )


def build_anchor_profile(
    vehicle_line: str, market: str, docs: list[SourceDoc], draft: dict[str, Any], skipped: list[dict[str, str]], *,
    anchor: str | None = None, anchor_variant: str | None = None,
) -> VehicleProfile | None:
    """The anchor's identity comes from the PM scope, not from the model; the draft only adds cited attributes."""
    item = dict(draft.get("anchor") or {})
    line = scope_label(vehicle_line)
    if anchor:
        make, model = "", anchor.strip()
    elif line in LINE_LABELS:
        make, model = "BMW", LINE_LABELS[line]
    elif line != ALL:
        make, model = "BMW", line
    elif item.get("model"):
        make, model = str(item.get("make") or ""), str(item["model"])
    else:
        return None
    item |= {"make": make, "model": model}
    return build_profile(item, docs, market, skipped, is_anchor=True, variant=anchor_variant or item.get("variant"))


# ---------------------------------------------------------------- stage 2: segment definition

def body_class(value: Any) -> str | None:
    text = _norm(value)
    return next((cls for word, cls in BODY_CLASSES.items() if word in text.split()), text or None)


def default_segment(
    anchor: VehicleProfile, market: str, *, band_overrides: dict[str, dict[str, Any]] | None = None,
    hard_powertrain: bool = False,
) -> SegmentDefinition:
    price, rng, length = _num(anchor.get("price")), _num(anchor.get("range")), _num(anchor.get("length"))
    criteria = [
        Criterion("price", "hard", *(None, None) if price is None else (round(price * (1 + PRICE_BAND[0])), round(price * (1 + PRICE_BAND[1])))),
        Criterion("body_style", "hard", equals=body_class(anchor.get("body_style"))),
        Criterion("seats", "hard", equals=_num(anchor.get("seats"))),
        Criterion("powertrain", "hard" if hard_powertrain else "soft", equals=anchor.get("powertrain"), weight=SOFT_WEIGHTS["powertrain"]),
        Criterion("range", "soft", *(None, None) if rng is None else (round(rng * (1 - RANGE_BAND)), round(rng * (1 + RANGE_BAND))),
                  weight=SOFT_WEIGHTS["range"]),
        Criterion("length", "soft", *(None, None) if length is None else (round(length * (1 - LENGTH_BAND)), round(length * (1 + LENGTH_BAND))),
                  weight=SOFT_WEIGHTS["length"]),
        Criterion("equipment", "soft", equals=anchor.get("equipment"), weight=SOFT_WEIGHTS["equipment"]),
    ]
    by_name = {c.attribute: c for c in criteria}
    for name, override in (band_overrides or {}).items():
        criterion = by_name.get(name)
        if criterion is None:
            criterion = Criterion(name, "hard")
            criteria.append(criterion)
        for key in ("min", "max", "equals", "kind", "weight"):
            if key in override:
                setattr(criterion, key, override[key])
        criterion.set_by = "pm"
    return SegmentDefinition(anchor=anchor.label, market=market, criteria=criteria)


def parse_band(text: str) -> tuple[str, dict[str, Any]]:
    """`price=55000:80000`, `range=500:` or `powertrain=BEV` (an exact value makes the criterion hard)."""
    name, _, value = text.partition("=")
    name, value = _norm(name).replace(" ", "_"), value.strip()
    if not name or not value:
        raise ValueError(f"band must look like attribute=min:max or attribute=value, got {text!r}")
    if ":" in value:
        low, _, high = value.partition(":")
        return name, {"min": float(low) if low.strip() else None, "max": float(high) if high.strip() else None}
    return name, {"equals": _num(value) if _num(value) is not None else value, "kind": "hard"}


def criterion_active(criterion: Criterion) -> bool:
    return criterion.min is not None or criterion.max is not None or criterion.equals not in (None, [], "")


def check_criterion(criterion: Criterion, profile: VehicleProfile) -> str:
    """`pass`, `fail` or `unknown`. A missing value is `unknown`, never a silent pass."""
    value = profile.get(criterion.attribute)
    if value is None:
        return "unknown"
    if criterion.min is not None or criterion.max is not None:
        number = _num(value)
        if number is None:
            return "unknown"
        return "pass" if (criterion.min is None or number >= criterion.min) and (criterion.max is None or number <= criterion.max) else "fail"
    if criterion.attribute == "body_style":
        return "pass" if body_class(value) == body_class(criterion.equals) else "fail"
    if _num(value) is not None and _num(criterion.equals) is not None:
        return "pass" if _num(value) == _num(criterion.equals) else "fail"
    return "pass" if _norm(value) == _norm(criterion.equals) else "fail"


def criterion_distance(criterion: Criterion, anchor: VehicleProfile, profile: VehicleProfile) -> float | None:
    """Distance in [0, 1] on one soft criterion; None when the candidate's value is missing."""
    value = profile.get(criterion.attribute)
    if value is None:
        return None
    if criterion.attribute == "equipment":
        ours = {_norm(v) for v in criterion.equals or []}
        theirs = {_norm(v) for v in (value if isinstance(value, list) else [value])}
        return 1 - len(ours & theirs) / len(ours | theirs) if ours | theirs else 0.0
    if criterion.min is not None or criterion.max is not None:
        number = _num(value)
        low, high = criterion.min, criterion.max
        centre = _num(anchor.get(criterion.attribute))
        if centre is None:
            centre = ((low if low is not None else high) + (high if high is not None else low)) / 2
        if number is None:
            return None
        span = max(abs(centre - (low if low is not None else centre)), abs((high if high is not None else centre) - centre)) or 1.0
        return min(1.0, abs(number - centre) / span)
    return 0.0 if check_criterion(criterion, profile) == "pass" else 1.0


# ---------------------------------------------------------------- stages 3 + 4: long-list, shortlist

def build_long_list(
    anchor: VehicleProfile, segment: SegmentDefinition, docs: list[SourceDoc], draft: dict[str, Any], market: str,
    skipped: list[dict[str, str]],
) -> list[Candidate]:
    hard = [c for c in segment.criteria if c.kind == "hard" and criterion_active(c)]
    soft = [c for c in segment.criteria if c.kind == "soft" and criterion_active(c) and c.weight > 0]
    candidates: dict[tuple[str, str, str, str], Candidate] = {}
    for item in draft.get("candidates") or []:
        profile = build_profile(item, docs, market, skipped)
        key = (_norm(profile.make), _norm(profile.model), _norm(profile.generation), _norm(profile.variant))
        if not profile.label or key in candidates or matches_name(profile.label, anchor):
            continue  # duplicates, and the anchor itself listed as its own rival
        if not any(a.value is not None for a in profile.attributes):
            skipped.append({"source": "unknown", "reason": f"{profile.label}: no cited attribute, not long-listed"})
            continue
        candidate = Candidate(profile=profile, status="in_band")
        for criterion in hard:
            outcome = check_criterion(criterion, profile)
            if outcome == "fail":
                candidate.status = "excluded"
                candidate.reasons.append(f"{criterion.attribute} outside the band ({_fmt(profile.get(criterion.attribute))})")
            elif outcome == "unknown":
                candidate.unknown_attributes.append(criterion.attribute)
                candidate.needs_pm_check = True
        total = weighted = 0.0
        for criterion in soft:
            distance = criterion_distance(criterion, anchor, profile)
            if distance is None:
                candidate.unknown_attributes.append(criterion.attribute)
                distance = 1.0  # a missing value counts as the largest distance
            total += criterion.weight
            weighted += criterion.weight * distance
        candidate.similarity = round(1 - weighted / total, 3) if total else None
        candidates[key] = candidate
    return sorted(candidates.values(), key=lambda c: (c.status != "in_band", -(c.similarity or 0.0), c.profile.label))


def matches_name(name: str, profile: VehicleProfile) -> bool:
    wanted, label = _norm(name), _norm(profile.label)
    base = _norm(f"{profile.make} {profile.model}")
    return bool(wanted) and (wanted in label or (bool(base) and base in wanted) or (bool(_norm(profile.model)) and wanted == _norm(profile.model)))


def build_competitor_set(
    anchor: VehicleProfile, long_list: list[Candidate], market: str, *, rivals: list[str] | None = None, max_rivals: int = 5,
) -> CompetitorSet:
    """Rank by similarity, or take the PM's picks. Candidates whose hard criteria could not be checked rank
    after the verified ones and stay flagged."""
    if rivals:
        for name in rivals:
            match = next((c for c in long_list if matches_name(name, c.profile)), None)
            if match is None:
                profile = VehicleProfile(label=name.strip(), make="", model=name.strip(), generation=None, variant=None,
                                         is_anchor=False, market=market)
                match = Candidate(profile=profile, status="in_band", reasons=["named by the PM; no cited profile found"])
                long_list.append(match)
            elif match.status == "excluded":
                match.reasons.append("kept because the PM named it")
            match.shortlisted = True
        selected_by = "pm"
    else:
        in_band = [c for c in long_list if c.status == "in_band"]
        in_band.sort(key=lambda c: (c.needs_pm_check, -(c.similarity or 0.0), c.profile.label))
        for candidate in in_band[:max(0, max_rivals)]:
            candidate.shortlisted = True
        selected_by = "similarity"
    chosen = [c for c in long_list if c.shortlisted]
    return CompetitorSet(
        anchor=anchor.label, market=market, rivals=[c.profile.label for c in chosen],
        similarity_scores={c.profile.label: c.similarity for c in chosen}, selected_by=selected_by,
    )


# ---------------------------------------------------------------- stages 5 + 6: evidence, comparison

def collect_observations(
    anchor: VehicleProfile, rivals: list[VehicleProfile], docs: list[SourceDoc], draft: dict[str, Any],
    skipped: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Cited observations per vehicle. The source type comes from the cited page's trust tier, not from the model."""
    by_url = {doc.url: doc for doc in docs}
    observations: list[dict[str, Any]] = []
    for profile in [anchor] + rivals:  # cited profile values are spec evidence too (price only draws the bracket)
        for attribute in profile.attributes:
            if attribute.value is None or attribute.attribute in PROFILE_ONLY or attribute.source_url not in by_url:
                continue
            observations.append({
                "vehicle": profile.label, "aspect": attribute.attribute, "doc": by_url[attribute.source_url], "source_type": "spec",
                "value": attribute.value, "unit": attribute.unit, "standard": attribute.standard, "sentiment": None,
                "text": f"{attribute.attribute}: {_fmt(attribute.value)} {attribute.unit or ''}".strip(), "higher_is_better": None,
            })
    for item in draft.get("observations") or []:
        doc = cited_doc(docs, item.get("source_index"))
        if doc is None:
            skipped.append({"source": "unknown", "reason": "observation referenced an invalid source_index"})
            continue
        name = str(item.get("vehicle") or "").strip()
        if _norm(name) == "anchor" or matches_name(name, anchor):
            vehicle = anchor.label
        else:
            vehicle = next((r.label for r in rivals if matches_name(name, r)), None)
        aspect = _norm(item.get("aspect")).replace(" ", "_")
        if vehicle is None or not aspect:
            skipped.append({"source": doc.url, "reason": f"observation about {name or 'an unnamed vehicle'} is outside the rival set"})
            continue
        tier = infer_trust_tier(doc)
        sentiment = _num(item.get("sentiment"))
        if item.get("value") is not None:
            source_type = "spec"
        elif sentiment is not None and tier in VOICE_TYPE_BY_TIER:
            source_type, sentiment = VOICE_TYPE_BY_TIER[tier], max(-1.0, min(1.0, sentiment))
        else:
            skipped.append({"source": doc.url, "reason": f"{vehicle} / {aspect}: neither a spec value nor a review or owner judgement"})
            continue
        observations.append({
            "vehicle": vehicle, "aspect": aspect, "doc": doc, "source_type": source_type, "value": item.get("value"),
            "unit": item.get("unit"), "standard": item.get("standard"), "sentiment": sentiment,
            "text": str(item.get("text") or "").strip(), "higher_is_better": item.get("higher_is_better"),
        })
    return observations


def best_spec(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    return min(observations, key=lambda o: TRUST_ORDER.get(infer_trust_tier(o["doc"]), 2)) if observations else None


def spec_cell(anchor: str, rival: str, aspect: str, ours: list[dict[str, Any]], theirs: list[dict[str, Any]]) -> ComparisonCell:
    a, r = best_spec(ours), best_spec(theirs)
    citations = [citation(o["doc"], side) for o, side in ((r, "rival"), (a, "anchor")) if o]
    tiers = [c["trust_tier"] for c in citations]
    level = evidence_from_trust(weakest_tier(tiers))  # hard facts are Verified only when both sides are manufacturer data
    cell = ComparisonCell(
        rival=rival, aspect=aspect, source_type="spec", anchor_value=a["value"] if a else None,
        rival_value=r["value"] if r else None, unit=(r or a or {}).get("unit"), delta=None, n_anchor=len(ours),
        n_rival=len(theirs), evidence_level=level, status="insufficient_data", citations=citations,
    )
    if a is None or r is None:
        cell.note = f"no cited {aspect} value for {anchor if a is None else rival}"
        return cell
    if _norm(a.get("unit")) != _norm(r.get("unit")) or _norm(a.get("standard")) != _norm(r.get("standard")):
        cell.status = "not_comparable"
        cell.note = (f"different unit or measurement standard ({a.get('standard') or a.get('unit') or 'none'} vs "
                     f"{r.get('standard') or r.get('unit') or 'none'})")
        return cell
    if r.get("standard"):
        cell.unit = f"{cell.unit or ''} {r['standard']}".strip()
    ours_n, theirs_n = _num(a["value"]), _num(r["value"])
    if ours_n is not None and theirs_n is not None:
        cell.delta = round(theirs_n - ours_n, 3)
        higher = next((o["higher_is_better"] for o in (r, a) if isinstance(o.get("higher_is_better"), bool)), None)
        if aspect in HIGHER_IS_BETTER:
            higher = True
        elif aspect in LOWER_IS_BETTER:
            higher = False
        gap_pct = abs(cell.delta) / abs(ours_n) * 100 if ours_n else (100.0 if cell.delta else 0.0)
        if gap_pct < SPEC_DELTA_PCT:
            cell.status = "parity"
        elif higher is None:
            cell.status, cell.note = "direction_unknown", "not known whether a higher value is better for the customer"
        else:
            cell.status = "rival_leads" if (cell.delta > 0) == higher else "anchor_leads"
        return cell

    def rank(value: Any) -> int | None:
        return int(value) if isinstance(value, bool) else EQUIPMENT_RANK.get(_norm(value).replace(" ", "_"))

    ours_rank, theirs_rank = rank(a["value"]), rank(r["value"])
    if ours_rank is None or theirs_rank is None:
        cell.status, cell.note = "not_comparable", "values are neither numeric nor an equipment status"
        return cell
    cell.delta = float(theirs_rank - ours_rank)
    cell.status = "parity" if cell.delta == 0 else "rival_leads" if cell.delta > 0 else "anchor_leads"
    return cell


def voice_cell(
    rival: str, aspect: str, source_type: str, ours: list[dict[str, Any]], theirs: list[dict[str, Any]],
    total_ours: int, total_theirs: int, min_mentions: int,
) -> ComparisonCell:
    def side(items: list[dict[str, Any]], total: int) -> dict[str, Any] | None:
        if not items:
            return None
        return {"n": len(items), "share_pct": round(len(items) / total * 100, 1) if total else None,
                "sentiment_balance": round(sum(o["sentiment"] for o in items) / len(items), 2)}

    a, r = side(ours, total_ours), side(theirs, total_theirs)
    seen: set[tuple[str, str]] = set()
    citations = []
    for items, label in ((theirs, "rival"), (ours, "anchor")):
        for o in items:
            if (label, o["doc"].url) not in seen:
                seen.add((label, o["doc"].url))
                citations.append(citation(o["doc"], label))
    cell = ComparisonCell(
        rival=rival, aspect=aspect, source_type=source_type, anchor_value=a, rival_value=r, unit="sentiment balance",
        delta=None, n_anchor=len(ours), n_rival=len(theirs),
        evidence_level=evidence_from_trust(weakest_tier([c["trust_tier"] for c in citations])),
        status="insufficient_data", citations=citations,
    )
    if len(ours) < min_mentions or len(theirs) < min_mentions:
        cell.note = f"fewer than {min_mentions} mentions on at least one side"
        return cell
    cell.delta = round(r["sentiment_balance"] - a["sentiment_balance"], 2)
    cell.status = "parity" if abs(cell.delta) < VOICE_DELTA else "rival_leads" if cell.delta > 0 else "anchor_leads"
    return cell


def compare(
    anchor: VehicleProfile, rivals: list[VehicleProfile], observations: list[dict[str, Any]], *, min_mentions: int = MIN_MENTIONS,
) -> list[tuple[ComparisonCell, list[dict[str, Any]]]]:
    """Per aspect and source type, like with like: spec vs spec, expert vs expert, owner vs owner."""
    def pick(vehicle: str, source_type: str, aspect: str | None = None) -> list[dict[str, Any]]:
        return [o for o in observations if o["vehicle"] == vehicle and o["source_type"] == source_type
                and (aspect is None or o["aspect"] == aspect)]

    cells = []
    for rival in rivals:
        keys = sorted({(o["aspect"], o["source_type"]) for o in observations if o["vehicle"] == rival.label})
        for aspect, source_type in keys:
            ours, theirs = pick(anchor.label, source_type, aspect), pick(rival.label, source_type, aspect)
            if source_type == "spec":
                cell = spec_cell(anchor.label, rival.label, aspect, ours, theirs)
            else:
                cell = voice_cell(rival.label, aspect, source_type, ours, theirs,
                                  len(pick(anchor.label, source_type)), len(pick(rival.label, source_type)), min_mentions)
            cells.append((cell, theirs + ours))
    return cells


def finding_text(anchor: str, cell: ComparisonCell) -> str:
    aspect = cell.aspect.replace("_", " ")
    if cell.source_type != "spec":
        r, a = cell.rival_value, cell.anchor_value
        return (
            f"{VOICE_LABEL[cell.source_type]} rate {cell.rival} better than {anchor} on {aspect}: sentiment balance "
            f"{r['sentiment_balance']:+.2f} over {r['n']} mentions ({r['share_pct']:.0f}% of its {cell.source_type} observations) "
            f"vs {a['sentiment_balance']:+.2f} over {a['n']} ({a['share_pct']:.0f}%)."
        )
    ours, theirs = _num(cell.anchor_value), _num(cell.rival_value)
    if ours is not None and theirs is not None:
        change = f", {(theirs - ours) / abs(ours) * 100:+.1f}%" if ours else ""
        return f"{cell.rival} is ahead of {anchor} on {aspect}: {_fmt(theirs)} vs {_fmt(ours)} {cell.unit or ''}".rstrip() + f"{change}."
    return f"{cell.rival} is ahead of {anchor} on {aspect}: {_fmt(cell.rival_value)} vs {_fmt(cell.anchor_value)}."


def findings_from_cells(
    anchor: VehicleProfile, vehicle_line: str, market: str, cells: list[tuple[ComparisonCell, list[dict[str, Any]]]],
) -> list[CompetitorFinding]:
    """Only a cell where the rival clearly leads becomes a finding. `competitor_weakness` (the anchor leads)
    is a proposed signal type that the schema does not have yet, so those cells stay in the matrix."""
    findings = []
    for cell, observations in cells:
        if cell.status != "rival_leads" or not cell.citations:
            continue
        primary = cell.citations[0]  # the rival-side source
        tier = weakest_tier([c["trust_tier"] for c in cell.citations])
        snapshot = "\n".join(f"{o['vehicle']}: {o['text']}" for o in observations if o["text"])
        assumptions = []
        if cell.source_type != "spec":
            assumptions.append(VOICE_ASSUMPTION)
        if len({c["url"] for c in cell.citations if c["side"] == "rival"}) < 2:
            assumptions.append("Rests on a single rival source; not corroborated.")
        if cell.source_type == "spec" and cell.evidence_level != "Verified":
            assumptions.append("Spec value is reported by a non-manufacturer source, not lab- or manufacturer-verified.")
        haystack = f"{cell.aspect.replace('_', ' ')} {snapshot}"
        out_of_scope = OUT_OF_SCOPE_REASON if OUT_OF_SCOPE_RE.search(haystack) else None
        findings.append(CompetitorFinding(
            source_url=primary["url"],
            title=primary["title"],
            retrieved_at=primary["retrieved_at"],
            locator=primary["locator"],
            text=finding_text(anchor.label, cell),
            signal_type="competitor_advantage",
            evidence_level=cell.evidence_level,
            market=market,
            vehicle_line=vehicle_line,
            sentiment=cell.rival_value["sentiment_balance"] if cell.source_type != "spec" else None,
            sample_size=cell.n_rival if cell.source_type != "spec" else None,
            trust_tier=tier,
            snapshot=snapshot or primary["snippet"],
            rival=cell.rival,
            aspect=cell.aspect,
            source_type=cell.source_type,
            citations=cell.citations,
            assumptions=assumptions,
            out_of_scope_reason=out_of_scope,
        ))
    return findings


# ---------------------------------------------------------------- result + summary

def scope_rivals(
    vehicle_line: str | None, market: str | None, docs: list[SourceDoc], draft: dict[str, Any], skipped: list[dict[str, str]], *,
    anchor: str | None = None, anchor_variant: str | None = None, band_overrides: dict[str, dict[str, Any]] | None = None,
    rivals: list[str] | None = None, hard_powertrain: bool = False, max_rivals: int = 5,
) -> tuple[VehicleProfile | None, SegmentDefinition | None, list[Candidate], CompetitorSet | None]:
    """Stages 1-4: anchor profile, segment bands, long-list, shortlist."""
    market_label = scope_label(market)
    profile = build_anchor_profile(scope_label(vehicle_line), market_label, docs, draft, skipped, anchor=anchor, anchor_variant=anchor_variant)
    if profile is None:
        return None, None, [], None
    segment = default_segment(profile, market_label, band_overrides=band_overrides, hard_powertrain=hard_powertrain)
    long_list = build_long_list(profile, segment, docs, draft, market_label, skipped)
    competitor_set = build_competitor_set(profile, long_list, market_label, rivals=rivals, max_rivals=max_rivals)
    return profile, segment, long_list, competitor_set


def build_result(
    vehicle_line: str | None,
    market: str | None,
    query: str,
    docs: list[SourceDoc],
    draft: dict[str, Any],
    *,
    anchor: str | None = None,
    anchor_variant: str | None = None,
    band_overrides: dict[str, dict[str, Any]] | None = None,
    rivals: list[str] | None = None,
    hard_powertrain: bool = False,
    max_rivals: int = 5,
    min_mentions: int = MIN_MENTIONS,
) -> CompetitorResult:
    line_label, market_label = scope_label(vehicle_line), scope_label(market)
    skipped: list[dict[str, str]] = []
    profile, segment, long_list, competitor_set = scope_rivals(
        vehicle_line, market, docs, draft, skipped, anchor=anchor, anchor_variant=anchor_variant,
        band_overrides=band_overrides, rivals=rivals, hard_powertrain=hard_powertrain, max_rivals=max_rivals,
    )
    cells: list[tuple[ComparisonCell, list[dict[str, Any]]]] = []
    findings: list[CompetitorFinding] = []
    if profile is not None:
        shortlisted = [c.profile for c in long_list if c.shortlisted]
        observations = collect_observations(profile, shortlisted, docs, draft, skipped)
        cells = compare(profile, shortlisted, observations, min_mentions=min_mentions)
        findings = findings_from_cells(profile, line_label, market_label, cells)

    for item in draft.get("skipped", []):
        doc = cited_doc(docs, item.get("source_index"))
        skipped.append({"source": doc.url if doc else "unknown", "reason": str(item.get("reason") or "not usable")})

    comparison = [cell for cell, _ in cells]
    summary = summarize(line_label, market_label, query, docs, profile, segment, long_list, competitor_set, comparison, findings, skipped)
    return CompetitorResult(
        agent_name=AGENT_NAME,
        vehicle_line=line_label,
        market=market_label,
        query=query,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        sources_read=len(docs),
        anchor=profile,
        segment=segment,
        long_list=long_list,
        competitor_set=competitor_set,
        comparison=comparison,
        findings=findings,
        skipped=skipped,
        summary=summary,
    )


def describe_criterion(criterion: Criterion) -> str:
    if criterion.min is not None or criterion.max is not None:
        value = f"{_fmt(criterion.min) if criterion.min is not None else 'any'} to {_fmt(criterion.max) if criterion.max is not None else 'any'}"
    elif isinstance(criterion.equals, list):
        value = f"overlap with {len(criterion.equals)} anchor equipment flag(s)"
    elif criterion.equals not in (None, ""):
        value = f"= {_fmt(criterion.equals)}"
    else:
        value = "not set (anchor value missing)"
    return f"{criterion.attribute} {value} [{criterion.kind}, {criterion.set_by}]"


def summarize(
    vehicle_line: str,
    market: str,
    query: str,
    docs: list[SourceDoc],
    anchor: VehicleProfile | None,
    segment: SegmentDefinition | None,
    long_list: list[Candidate],
    competitor_set: CompetitorSet | None,
    comparison: list[ComparisonCell],
    findings: list[CompetitorFinding],
    skipped: list[dict[str, str]],
) -> str:
    tiers = [infer_trust_tier(doc) for doc in docs]
    tier_mix = ", ".join(f"{tiers.count(t)} {t}" for t in TRUST_ORDER if tiers.count(t)) or "none"
    lines = [f"{AGENT_NAME} looked at {len(docs)} web sources ({tier_mix}) for {vehicle_line} / {market}: {query}", ""]
    if anchor is None or segment is None or competitor_set is None:
        lines.extend([
            "Findings:",
            "- No competitor findings were produced.",
            "",
            "Confidence and gaps:",
            "- Competitor benchmarking needs one anchor vehicle. Name a vehicle line or an anchor model and retry.",
        ])
        return "\n".join(lines)

    lines.append(f"Anchor: {anchor.label}")
    cited = [a for a in anchor.attributes if a.value is not None]
    for attribute in cited:
        value = ", ".join(map(str, attribute.value)) if isinstance(attribute.value, list) else _fmt(attribute.value)
        unit = f"{attribute.unit or ''} {attribute.standard or ''}".strip()
        lines.append(f"- {attribute.attribute}: {value}{' ' + unit if unit else ''} ({attribute.trust_tier}; {attribute.locator})")
    if not cited:
        lines.append("- No cited anchor attributes; default bands could not be derived.")

    lines.extend(["", "Segment bands (override any of them with a steering note before accepting):"])
    lines.extend(f"- {describe_criterion(c)}" for c in segment.criteria)

    shortlisted = sorted((c for c in long_list if c.shortlisted), key=lambda c: (c.needs_pm_check, -(c.similarity or 0.0)))
    lines.extend(["", f"Rival set: {len(shortlisted)} of {len(long_list)} long-listed model(s), selected by {competitor_set.selected_by}:"])
    for candidate in shortlisted:
        note = f"; not checked: {', '.join(candidate.unknown_attributes)}" if candidate.unknown_attributes else ""
        score = f"similarity {candidate.similarity:.2f}" if candidate.similarity is not None else "no similarity score"
        lines.append(f"- {candidate.profile.label} ({score}{note})")
    if not shortlisted:
        lines.append("- No rival passed the bands.")
    for candidate in long_list:
        if not candidate.shortlisted:
            reason = "; ".join(candidate.reasons) or "ranked below the shortlist"
            lines.append(f"- not carried forward: {candidate.profile.label} ({reason})")

    in_scope = [f for f in findings if not f.out_of_scope_reason]
    out_of_scope = [f for f in findings if f.out_of_scope_reason]

    def cites(citations: list[dict[str, str]]) -> str:
        return "; ".join(f"{c['side']}: {c['locator']}" for c in citations)

    lines.extend(["", "Findings:"])
    if in_scope:
        for finding in in_scope:
            lines.append(f"- {finding.text} ({finding.evidence_level}; {finding.trust_tier}; {cites(finding.citations)})")
    else:
        lines.append("- No competitor advantage with a clear, cited delta was found.")
    if out_of_scope:
        lines.extend(["", "Out-of-scope bin (not for requirements):"])
        for finding in out_of_scope:
            lines.append(f"- {finding.text} ({finding.out_of_scope_reason}; {cites(finding.citations)})")

    others = [c for c in comparison if c.status != "rival_leads"]
    if others:
        lines.extend(["", "Compared without a finding:"])
        for cell in others:
            note = f": {cell.note}" if cell.note else ""
            source = f" ({cites(cell.citations)})" if cell.citations else ""
            lines.append(f"- {cell.rival} / {cell.aspect.replace('_', ' ')} / {cell.source_type}: {cell.status.replace('_', ' ')}{note}{source}")

    lines.extend(["", "Confidence and gaps:"])
    lines.append("- Bands, similarity, deltas and percentages are computed in code from cited values; pages are not fetched, "
                 "so each value is the search tool's cited summary of the page.")
    if market == ALL:
        lines.append("- No market was given, so this is one global rival list; rival sets differ by market.")
    if vehicle_line in LINE_LABELS:
        lines.append(f"- {vehicle_line} is presumed to be the BMW {LINE_LABELS[vehicle_line]}; confirm before presenting as fact.")
    missing = [c.attribute for c in segment.criteria if not criterion_active(c)]
    if missing:
        lines.append(f"- No band could be set for: {', '.join(missing)} (anchor value missing).")
    if any(c.unknown_attributes for c in shortlisted):
        lines.append("- Some shortlisted rivals have attributes that could not be sourced; they did not pass a filter, they were not checked.")
    if any(f.evidence_level == "Unverified" for f in findings):
        lines.append("- Some findings rest on low-trust web/social sources and should be corroborated.")
    if any(c.status == "insufficient_data" for c in comparison):
        lines.append("- Aspects with too few mentions or a missing anchor value are reported as insufficient data, not as findings.")
    if any(c.status == "anchor_leads" for c in comparison):
        lines.append("- Aspects where the anchor leads are listed above but not stored as findings.")
    lines.append("- Price is used only to draw the bracket; it is never a requirement input.")
    if skipped:
        lines.append(f"- {len(skipped)} source(s) or statement(s) were skipped (no valid citation, or outside the rival set).")
    if not findings:
        lines.append("- The step needs better sources, other bands or a narrower PM steering note.")
    lines.append("- Nothing was accepted, scored or prioritized; the step waits for PM review.")
    return "\n".join(lines)


# ---------------------------------------------------------------- live path: web search through the LLM

def search_sources(client: "OpenAIClient", task: str, limit: int) -> list[SourceDoc]:
    response = client.responses.create(
        model=RESEARCH_MODEL,
        tools=[{"type": "web_search"}],
        tool_choice="required",
        input=(
            f"{task} "
            f"Answer with up to {limit} lines, one source per line: state what that source reports, with the concrete "
            "facts and figures it gives (name the vehicle, variant, unit and measurement standard), and cite it. "
            "Do not add an introduction, a conclusion, or any statement without a citation."
        ),
    )
    return sources_from_web_search_response(response, limit)


def collect_scoping_sources(client: "OpenAIClient", anchor_label: str, market: str, query: str, limit: int) -> list[SourceDoc]:
    return search_sources(
        client,
        f"Search the web for (a) the official specification of the {anchor_label} sold in market {market}: body style, seats, "
        "powertrain, list price, range, length, standard equipment; and (b) the models buyers cross-shop with it in that "
        f"market, with the same data for each (comparison tests, 'alternatives to' articles, manufacturer pages). PM query: {query}. "
        "Prefer manufacturer pages and trade press over forums.",
        limit,
    )


def collect_evidence_sources(client: "OpenAIClient", vehicle: str, market: str, query: str, limit: int) -> list[SourceDoc]:
    return search_sources(
        client,
        f"Search the web for evidence about the {vehicle} in market {market} that is relevant to this PM query: {query}. "
        "Cover manufacturer spec pages, comparison tests and long-term reviews, and owner reviews or forums.",
        limit,
    )


def source_blocks(docs: list[SourceDoc]) -> str:
    return "\n\n".join(
        f"[{i}] title: {doc.title}\nurl: {doc.url}\ntrust_tier: {infer_trust_tier(doc)}\nsnippet: {doc.snippet[:1800]}"
        for i, doc in enumerate(docs, 1)
    )


def build_profile_prompt(anchor_label: str, market: str, query: str, docs: list[SourceDoc]) -> str:
    return f"""You are the Competitor Agent for a vehicle requirements pipeline. Step: vehicle profiles.

Anchor vehicle: {anchor_label}. Market: {market}. PM query: {query}

Task:
- From the sources, fill a profile for the anchor and for every rival model the sources name.
- Attributes: price (list price, number), body_style, seats, powertrain (ICE|PHEV|BEV), range, length, equipment
  (list of standard-equipment names). Give unit and measurement standard (WLTP, EPA, CLTC) where they apply.
- Every attribute must cite exactly one source index. Leave out what the sources do not state; never estimate.
- Do not judge, rank or select vehicles.

Return strict JSON:
{{
  "anchor": {{"variant": "...", "attributes": [{{"attribute": "range", "value": 580, "unit": "km", "standard": "WLTP", "source_index": 1}}]}},
  "candidates": [{{"make": "...", "model": "...", "generation": "...", "variant": "...", "attributes": [...]}}]
}}

Sources:
{source_blocks(docs)}
"""


def build_observation_prompt(anchor_label: str, rivals: list[str], market: str, query: str, docs: list[SourceDoc]) -> str:
    return f"""You are the Competitor Agent for a vehicle requirements pipeline. Step: evidence per aspect.

Anchor vehicle: {anchor_label}. Rivals: {", ".join(rivals)}. Market: {market}. PM query: {query}

Task:
- Extract observations about the anchor and the rivals, one customer-facing aspect each (snake_case, e.g. range,
  charging_time, rear_legroom, infotainment_responsiveness, seat_comfort). Use the same aspect name for all vehicles.
- A spec observation has a "value" (number, or standard|optional|not_available for equipment), with unit and
  measurement standard. A review or owner judgement has a "sentiment" from -1 to 1 and no value.
- Every observation must cite exactly one source index. Do not compare vehicles, compute differences, or draw conclusions.
- Do not create requirements or priorities.

Return strict JSON:
{{
  "observations": [
    {{"vehicle": "anchor or the rival name", "aspect": "range", "source_index": 1, "value": 620, "unit": "km", "standard": "WLTP",
      "text": "what the source says"}},
    {{"vehicle": "...", "aspect": "seat_comfort", "source_index": 2, "sentiment": 0.6, "text": "what the source says"}}
  ],
  "skipped": [{{"source_index": 1, "reason": "why no usable observation was produced"}}]
}}

Sources:
{source_blocks(docs)}
"""


def extract_json_with_openai(client: "OpenAIClient", prompt: str) -> dict[str, Any]:
    response = client.responses.create(model=RESEARCH_MODEL, input=prompt, text={"format": {"type": "json_object"}})
    return json.loads(response.output_text)


def research_with_openai(
    client: "OpenAIClient", vehicle_line: str | None, market: str | None, query: str, *, max_sources: int = 6, **options: Any,
) -> tuple[list[SourceDoc], dict[str, Any]]:
    """Live run in the order of the doc: search and profile first, shortlist in code, then evidence per rival."""
    line_label, market_label = scope_label(vehicle_line), scope_label(market)
    anchor_label = options.get("anchor") or (f"BMW {LINE_LABELS.get(line_label, line_label)}" if line_label != ALL else None)
    if anchor_label is None:
        return [], {"candidates": [], "observations": [], "skipped": []}
    if options.get("anchor_variant"):
        anchor_label = f"{anchor_label} {options['anchor_variant']}"
    docs = collect_scoping_sources(client, anchor_label, market_label, query, max_sources)
    draft = extract_json_with_openai(client, build_profile_prompt(anchor_label, market_label, query, docs)) if docs else {}
    scope_options = {k: options.get(k) for k in ("anchor", "anchor_variant", "band_overrides", "rivals") if options.get(k)}
    profile, _, long_list, _ = scope_rivals(
        vehicle_line, market, docs, draft, [], hard_powertrain=bool(options.get("hard_powertrain")),
        max_rivals=int(options.get("max_rivals") or 5), **scope_options,
    )
    rivals = [c.profile.label for c in long_list if c.shortlisted]
    if profile is not None and rivals:
        for vehicle in [profile.label] + rivals:  # the anchor's public evidence is collected the same way
            docs = docs + collect_evidence_sources(client, vehicle, market_label, query, max_sources)
        observed = extract_json_with_openai(client, build_observation_prompt(profile.label, rivals, market_label, query, docs))
        draft["observations"] = observed.get("observations") or []
        draft["skipped"] = observed.get("skipped") or []
    return docs, draft


# ---------------------------------------------------------------- storage

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
        "values (%s, %s, 1, 'awaiting_review', %s, %s, now(), "
        "(select coalesce(max(position), 0) + 1 from public.step where run_id = %s)) returning id",
        (run_id, AGENT_NAME, summary, AGENT_NAME, run_id),
    ).fetchone()[0]


def store_result(conn: Any, client: "OpenAIClient", result: CompetitorResult, run_id: str | None, step_id: str | None) -> None:
    """Write sources and findings and leave the step in `awaiting_review`. The bands, the rival set and the
    comparison cells have no tables yet (doc 10 proposes them), so they are kept on the step."""
    with conn.transaction():
        stored_step_id = ensure_step(conn, run_id, step_id, result.summary)
        embeddings = client.embeddings.create(
            model=EMBED_MODEL,
            input=[finding.text[:MAX_EMBED_CHARS] for finding in result.findings] or ["empty"],
        ).data
        for finding, embedding in zip(result.findings, embeddings):
            source_id = None
            for cited in finding.citations:  # the rival-side source is first and owns the finding
                doc = SourceDoc(url=cited["url"], title=cited["title"], snippet=cited["snippet"],
                                retrieved_at=cited["retrieved_at"], trust_tier=cited["trust_tier"])
                stored = upsert_source(conn, doc, result.vehicle_line, result.market, 1)
                source_id = source_id or stored
            dedupe = hashlib.sha256(f"{source_id}|{finding.locator}|{finding.text}".encode("utf-8")).hexdigest()
            exists = conn.execute(
                "select id from public.finding where source_id = %s and locator = %s and text = %s",
                (source_id, finding.locator, finding.text),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                "insert into public.finding (source_id, locator, text, signal_type, evidence_level, sentiment, sample_size, "
                "market, vehicle_line, out_of_scope_reason, extracted_by, step_id, embedding, source_snapshot, assumptions, "
                "dedupe_key) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::extensions.vector,%s,%s,%s)",
                (
                    source_id,
                    finding.locator,
                    finding.text,
                    finding.signal_type,
                    finding.evidence_level,
                    finding.sentiment,
                    finding.sample_size,
                    finding.market,
                    finding.vehicle_line,
                    finding.out_of_scope_reason,
                    AGENT_NAME,
                    stored_step_id,
                    vec(embedding.embedding),
                    finding.snapshot,
                    finding.assumptions,
                    dedupe,
                ),
            )
        if stored_step_id:
            refs: list[dict[str, Any]] = [
                {"type": "finding", "locator": f.locator, "source": f.source_url, "rival": f.rival, "aspect": f.aspect}
                for f in result.findings
            ]
            if result.segment:
                refs.append({"type": "segment_definition", **asdict(result.segment)})
            if result.competitor_set:
                refs.append({"type": "competitor_set", **asdict(result.competitor_set)})
            refs.extend({"type": "comparison_cell", **asdict(cell)} for cell in result.comparison)
            conn.execute(
                "update public.step set structured_output_refs = %s::jsonb where id = %s",
                (json.dumps(refs), stored_step_id),
            )


# ---------------------------------------------------------------- entry point

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Competitor Agent")
    parser.add_argument("query", help="PM research question or steering note")
    parser.add_argument("--vehicle-line", default=ALL, help="F70|G60|G68|G70; the anchor line")
    parser.add_argument("--market", default=ALL, help="EU|CN|US|RoW, or ALL for one global rival list")
    parser.add_argument("--anchor", help="anchor model name, if not a known vehicle line")
    parser.add_argument("--anchor-variant", help="anchor variant, e.g. 'i5 eDrive40'")
    parser.add_argument("--band", action="append", default=[], help="PM band override: price=55000:80000 or powertrain=BEV; repeatable")
    parser.add_argument("--hard-powertrain", action="store_true", help="same powertrain only")
    parser.add_argument("--rival", action="append", default=[], help="PM-picked rival; repeatable, replaces the ranked shortlist")
    parser.add_argument("--max-rivals", type=int, default=5)
    parser.add_argument("--min-mentions", type=int, default=MIN_MENTIONS)
    parser.add_argument("--run-id")
    parser.add_argument("--step-id")
    parser.add_argument("--seed-sources", type=Path, help="JSON list of source snippets; avoids live web search")
    parser.add_argument("--draft-json", type=Path, help="JSON draft output; avoids OpenAI extraction for tests/demos")
    parser.add_argument("--max-sources", type=int, default=6, help="sources per search (scoping, then each vehicle)")
    parser.add_argument("--dry-run", action="store_true", help="print JSON result instead of writing findings")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    options: dict[str, Any] = {
        "anchor": args.anchor,
        "anchor_variant": args.anchor_variant,
        "band_overrides": dict(parse_band(band) for band in args.band),
        "rivals": args.rival,
        "hard_powertrain": args.hard_powertrain,
        "max_rivals": args.max_rivals,
    }
    if bool(args.seed_sources) != bool(args.draft_json):
        raise SystemExit("--seed-sources and --draft-json go together: a draft cites the seeded sources by index.")
    if args.seed_sources:
        docs, draft = load_seed_sources(args.seed_sources), load_competitor_draft(args.draft_json)
    else:
        docs, draft = research_with_openai(require_openai()(), args.vehicle_line, args.market, args.query,
                                           max_sources=args.max_sources, **options)
    result = build_result(args.vehicle_line, args.market, args.query, docs, draft, min_mentions=args.min_mentions, **options)

    if args.dry_run:
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return 0

    client = require_openai()()
    conn = require_psycopg().connect(os.environ["SUPABASE_DB_URL"])
    store_result(conn, client, result, args.run_id, args.step_id)
    conn.close()
    print(result.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
