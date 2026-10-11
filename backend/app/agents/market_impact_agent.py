"""Local, cited customer signals for optional equipment. No external model or share prediction."""
from __future__ import annotations

import re
from dataclasses import asdict, replace

from app.knowledge import tools

MARKETS = ("US", "EU", "CN", "RoW")
MAX_CANDIDATES = 12

# Functional synonyms for German catalog labels and English customer comments. These identify a
# topic, not exact variant availability. Never infer that a different named package is equivalent.
ALIASES = (
    (("sitzbelüft", "seat ventilation", "ventilated seat"),
     ("seat ventilation", "ventilated seats", "ventilated seat", "cooled seats", "seat cooling", "seat ventilation system")),
    (("sitzheizung", "heated seat", "seat heating"), ("heated seats", "heated seat", "seat heating")),
    (("lenkradheizung", "heated steering"), ("heated steering wheel", "steering wheel heating")),
    (("panorama", "glasdach", "sunroof", "moonroof"), ("panoramic roof", "panorama roof", "glass roof", "sunroof", "moonroof")),
    (("anhängerkupplung", "towbar", "trailer hitch"), ("towbar", "tow bar", "tow hitch", "trailer hitch", "trailer coupling")),
    (("driving assistant", "driver assistance"), ("driving assistant", "driver assistance", "lane assist", "lane keeping")),
    (("parking assistant", "parking assistance"), ("parking assistant", "parking assistance", "automatic parking", "parking camera")),
    (("head-up", "head up", "headup", "hud"), ("head-up display", "head up display", "headup display", "HUD")),
    (("massage",), ("seat massage", "massage seats", "massage function", "massaging seats")),
    (("komfortsitze", "comfort seat"), ("comfort seats", "comfort seat", "seat comfort")),
    (("soft-close", "soft close", "softclose"), ("soft-close", "soft close", "softclose")),
    (("harman",), ("harman kardon", "harman-kardon")),
    (("bowers",), ("bowers wilkins", "bowers & wilkins")),
    (("klima", "air conditioning", "climate control"), ("air conditioning", "air-conditioning", "climate control", "aircon")),
    (("komfortzugang", "comfort access", "keyless entry"), ("comfort access", "keyless entry", "keyless access")),
    (("wirelesscharging", "wireless charging", "induktiv"), ("wireless charging", "wireless charger", "charging tray")),
    (("leder", "leather"), ("leather seats", "leather upholstery", "leather trim")),
)


def feature_terms(feature: str) -> list[str]:
    lower = feature.casefold()
    terms = [feature.strip()]
    for markers, aliases in ALIASES:
        if any(re.search(r"(?<!\w)"+re.escape(marker)+r"(?!\w)", lower) if len(marker) <= 3 else marker in lower for marker in markers):
            terms.extend(aliases)
    # Unknown names remain exact phrases; generic individual words would match unrelated equipment.
    if "räder" in lower or "wheels" in lower:
        size = re.search(r'(\d{2})(?:["″]|[ -]+inch)', feature)
        if size:
            terms.extend((f'{size[1]} inch', f'{size[1]}-inch', f'{size[1]}"'))
    return list(dict.fromkeys(t.casefold() for t in terms if t.strip()))[:16]



def resolve_feature(line: str, option_id: str | None, feature: str | None):
    catalog = None
    if option_id:
        catalog = next((h for h in tools.get_options(line=line, status="optional", limit=201)
                        if h.citation.id == option_id), None)
        if catalog is None:
            raise LookupError("No optional equipment matches this line and option.")
        feature = catalog.text
    if not feature or not feature.strip():
        raise ValueError("Choose an optional feature.")
    return feature.strip(), catalog


def direction(benefit: int, risk: int) -> str:
    # A minority concern is a trade-off, not something a popularity vote should hide.
    return "mixed" if benefit and risk else "positive" if benefit else "negative" if risk else "insufficient"


def comment_signal(text: str, terms: list[str]) -> tuple[str, str, str]:
    """Conservative feature-clause rules. Source row polarity describes the whole comment.

    These are interpreted sample signals, not an exhaustive semantic classification or causal forecast.
    Ambiguous clauses are retained as unclear, rather than filled from the row's overall sentiment.
    """
    topic = re.compile("|".join(r"(?<!\w)" + re.escape(t) + r"(?!\w)" for t in terms), re.I)
    benefit = risk = False
    excerpts = []
    meaningful = []
    for clause in re.split(r"[.!?;\n]+|\b(?:but|however|and)\b", text, flags=re.I):
        matches = list(topic.finditer(clause))
        if not matches:
            continue
        excerpts.append(clause.strip())
        for match in matches:
            context = clause[max(0, match.start()-80):match.end()+80].casefold()
            # Double negation and negated problem words are ambiguous without semantic parsing.
            if re.search(r"\b(?:do not hate|don't hate|not (?:weak|unreliable|broken|poor)|no problems)\b", context):
                continue
            rejection = re.search(r"\b(?:not worth|do not want|don't want|do not need|don't need|do not like|don't like|do not love|don't love|do not prefer|don't prefer|does not prefer|doesn't prefer|unnecessary|unwanted|never use|too expensive|overpriced|not (?:needed|necessary|required|good|useful|comfortable|great|nice|excellent|terrific|better|happy))\b", context)
            problem = re.search(r"\b(?:uncomfortable|weak|unreliable|broken|fails|failure|not working|does not work|doesn't work|poor|annoying|difficult|too noisy|too hot|too cold|dislike|hate|worse)\b", context)
            desire = re.search(r"\b(?:wish|would like|would rather|prefers|prefer|want|need|should have|missing|not available|does not have|doesn't have|without|not having)\b", context)
            # A request for better execution is a risk, not praise. A topic such as "seat
            # comfort" contains the noun comfort itself, which must never become a vote.
            improvement = re.search(r"\b(?:could|should|must|needs? to) (?:be|work) better\b", context)
            praise = re.search(r"\b(?:terrific|love|nice|comfortable|excellent|great|useful|better|smoother|improve|happy)\b", context)
            risk |= bool(rejection or problem or improvement)
            benefit |= bool((desire or praise) and not rejection and not problem and not improvement)
            if rejection or problem or improvement or desire or praise:
                meaningful.append(clause.strip())
    stance = "mixed" if benefit and risk else "supports" if benefit else "risk" if risk else "unclear"
    reason = {"supports": "The feature-specific passage expresses praise, preference, or unmet demand.",
              "risk": "The feature-specific passage describes a usability, quality, cost, or acceptance risk.",
              "mixed": "The feature-specific passages contain both a benefit and a concern.",
              "unclear": "This comment mentions the feature, but its effect is ambiguous; row polarity is not used as a feature verdict."}[stance]
    # Keep a verbatim feature passage, not an unrelated opening sentence from a long comment.
    passages = meaningful or excerpts
    excerpt = next((e for e in passages if len(e) <= 300), passages[0][:300] if passages else text[:300])
    if stance == "mixed" and meaningful:
        # Show both signals as one verbatim span when they fit. A lone positive clause must
        # not appear to be the entire justification for a mixed verdict.
        start = min(text.index(p) for p in meaningful)
        end = max(text.index(p) + len(p) for p in meaningful)
        if end - start <= 300:
            excerpt = text[start:end]
        else:
            reason += " This excerpt shows one passage; open the source to review both."
    return stance, reason, excerpt


def assess(line: str, *, option_id: str | None = None, feature: str | None = None) -> dict:
    feature, catalog = resolve_feature(line, option_id, feature)
    terms = feature_terms(feature)
    coverage = {row["key"]: row["n"] for row in tools.feedback_stats("market_code", line=line)}
    matched: dict[str, list[dict]] = {market: [] for market in MARKETS}
    counts = {market: {"positive": 0, "request": 0, "negative": 0} for market in MARKETS}
    seen = set()
    for hit in tools.feature_feedback(terms, line=line, limit_per_market=MAX_CANDIDATES):
        market = hit.meta.get("market_code")
        fingerprint = (market, " ".join(hit.text.casefold().split()))
        if (hit.citation.kind != "feedback" or market not in MARKETS or hit.meta.get("vehicle_line") != line
                or fingerprint in seen):
            continue
        seen.add(fingerprint)
        polarity = hit.meta.get("polarity")
        if polarity in counts[market]:
            counts[market][polarity] = int(hit.meta["polarity_count"])
        stance, reason, excerpt = comment_signal(hit.text, terms)
        matched[market].append({"citation": asdict(replace(hit.citation, quote=excerpt)), "stance": stance, "reason": reason})
    markets = []
    for market in MARKETS:
        evidence = matched[market]
        support = sum(e["stance"] in ("supports", "mixed") for e in evidence)
        risk = sum(e["stance"] in ("risk", "mixed") for e in evidence)
        unclear = sum(e["stance"] == "unclear" for e in evidence)
        if not coverage.get(market):
            explanation = f"No customer feedback is loaded for {line} in this market."
        elif not evidence:
            explanation = "No feedback matched this feature's name or known functional synonyms."
        else:
            explanation = f"In {len(evidence)} distinct sample comments: {support} benefit or demand signals, {risk} risks, {unclear} unclear. These are feature-specific interpretations, not share calculations."
        markets.append({"market": market, "direction": direction(support, risk), "explanation": explanation,
                        "total_feedback": coverage.get(market, 0), "matched_total": sum(counts[market].values()),
                        "counts": counts[market], "reviewed": len(evidence),
                        "signal_counts": {"benefit": support, "risk": risk, "unclear": unclear}, "evidence": evidence})
    return {"line": line, "feature": feature, "catalog_citation": asdict(catalog.citation) if catalog else None,
            "basis": "Local, deduplicated feature-passage interpretations with sampled citations; whole-comment polarity counts do not determine direction or market share.",
            "query_terms": terms, "markets": markets}
