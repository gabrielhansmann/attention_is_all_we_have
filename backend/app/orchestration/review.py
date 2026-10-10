"""Research checks over the accepted findings behind draft requirements in a run.

This is a review of *retrieved* evidence, not a survey of the whole population. It
never writes portfolio entities or treats missing citations as proof of absence.
"""
from __future__ import annotations

from typing import Any

MARKETS = ("EU", "CN", "US", "RoW")
NEEDS = {"complaint", "unmet_need", "competitor_advantage"}


def build_review(run: dict, steps: list[dict]) -> dict[str, Any] | None:
    """Attach a cited challenge, market check and next-action list to each draft."""
    from .runner import _output_of

    accepted = [_output_of(s) or {} for s in steps if s["status"] == "accepted"]
    drafts = [r for output in accepted for r in output.get("requirements") or [] if isinstance(r, dict)]
    if not drafts:
        return None

    findings = {}
    clusters = {}
    for output in accepted:
        for cluster in output.get("clusters") or []:
            if isinstance(cluster, dict) and cluster.get("id"):
                clusters[str(cluster["id"])] = cluster
        for finding in output.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            source = finding.get("source_file") or finding.get("source") or finding.get("source_url") or finding.get("file")
            if finding.get("id") and source and finding.get("locator") and not finding.get("out_of_scope_reason"):
                findings[str(finding["id"])] = finding

    reviewed = []
    for requirement in drafts:
        linked = [findings[str(i)] for i in dict.fromkeys(requirement.get("linked_finding_ids") or [])
                  if str(i) in findings]
        cluster_ids = requirement.get("linked_cluster_ids") or [requirement.get("cluster_id")]
        related_ids = dict.fromkeys(str(i) for cluster_id in cluster_ids if cluster_id is not None
                                    for i in (clusters.get(str(cluster_id), {}).get("member_finding_ids") or []))
        related = list({str(f["id"]): f for f in [*linked, *(findings[i] for i in related_ids if i in findings)]}.values())
        needs = any(f.get("signal_type") in NEEDS for f in linked)
        support = [f for f in linked if not needs or f.get("signal_type") != "praise"]
        counter = [f for f in related if needs and f.get("signal_type") == "praise"]

        def cited(f: dict) -> dict:
            return {"finding_id": str(f["id"]), "text": str(f.get("text") or ""),
                    "source": str(f.get("source_file") or f.get("source") or f.get("source_url") or f.get("file")),
                    "locator": str(f["locator"]), "market": str(f.get("market") or ""),
                    "evidence_level": str(f.get("evidence_level") or "Unverified")}

        scope = run.get("market")
        markets = MARKETS if scope in (None, "ALL") else (scope,)
        market_rows = []
        for market in markets:
            local = [f for f in related if f.get("market") == market]
            positives = sum(f.get("signal_type") == "praise" for f in local)
            negatives = sum(f.get("signal_type") in NEEDS for f in local)
            status = ("not assessed" if not local else "mixed" if positives and negatives else
                      "need signal" if negatives else "positive signal" if positives else "other evidence")
            market_rows.append({"market": market, "status": status,
                                "finding_ids": [str(f["id"]) for f in local]})

        sources = {str(f.get("source_file") or f.get("source") or f.get("source_url") or f.get("file")) for f in linked}
        actions = []
        if len(sources) < 2:
            actions.append({"priority": "high", "action": "Seek an independent source",
                            "reason": f"Only {len(sources)} distinct cited source(s) support this draft in this run."})
        missing = [row["market"] for row in market_rows if row["status"] == "not assessed"]
        if missing:
            actions.append({"priority": "high" if len(missing) == len(market_rows) else "medium",
                            "action": "Collect market-specific evidence",
                            "reason": f"No related finding from this run is assigned to {', '.join(missing)}."})
        if any(f.get("evidence_level") != "Verified" for f in linked):
            actions.append({"priority": "medium", "action": "Validate interpreted evidence",
                            "reason": "At least one linked finding is not Verified; check its original source and method."})
        metric = requirement.get("metric")
        metric_text = str(metric.get("text") or "") if isinstance(metric, dict) else ""
        if not metric_text or metric_text.startswith("No defensible metric"):
            actions.append({"priority": "medium", "action": "Define a measurable test",
                            "reason": "No source-grounded metric is available; choose an outcome and protocol before setting a target."})
        if not counter and needs:
            actions.append({"priority": "medium", "action": "Look for counter-evidence",
                            "reason": "No related positive customer signal challenges this need in this run."})

        reviewed.append({"requirement_id": str(requirement.get("id") or ""),
                         "title": str(requirement.get("title") or "Untitled requirement"),
                         "support": [cited(f) for f in support], "counter": [cited(f) for f in counter],
                         "markets": market_rows, "actions": actions})

    return {"requirements": reviewed,
            "scope_note": "Only accepted, citable findings linked to this draft or its clusters are assessed. "
                          "A positive signal is a challenge to investigate, not a refutation. "
                          "Missing coverage does not mean no evidence exists."}
