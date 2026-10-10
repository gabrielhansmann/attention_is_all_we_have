"""Read-only evidence endpoints. Everything returned carries a citation resolved from the stored row."""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.knowledge import tools

from .schemas import (CitationOut, EvidenceKind, GroupBy, HitOut, Line, Market, Polarity, Powertrain,
                      SearchResponse, StatRow, StatsResponse)

router = APIRouter(prefix="/evidence", tags=["evidence"])


def _unavailable(e: Exception) -> HTTPException:
    """Turn infrastructure errors into a 503 without leaking connection details."""
    return HTTPException(status_code=503, detail=f"evidence store unavailable ({type(e).__name__})")


def _hit(h: tools.Hit) -> HitOut:
    return HitOut(citation=CitationOut(**asdict(h.citation)), text=h.text, meta=h.meta, score=h.score)


@router.get("/search", response_model=SearchResponse)
def search(
    q: Annotated[str, Query(min_length=2, max_length=300)],
    source: Annotated[str, Query(pattern="^(feedback|docs)$")] = "feedback",
    line: Line | None = None,
    market: Market | None = None,
    domain: Annotated[str | None, Query(max_length=60)] = None,
    polarity: Polarity | None = None,
    powertrain: Powertrain | None = None,
    k: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SearchResponse:
    try:
        if source == "docs":
            hits = tools.search_docs(q, line=line, k=k)
        else:
            hits = tools.search_feedback(q, line=line, market=market, domain=domain, polarity=polarity,
                                         powertrain=powertrain, k=k)
    except ValueError as e:  # unknown domain
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise _unavailable(e)
    return SearchResponse(query=q, source=source, hits=[_hit(h) for h in hits])


@router.get("/stats", response_model=StatsResponse)
def stats(
    group_by: GroupBy,
    line: Line | None = None,
    market: Market | None = None,
    domain: Annotated[str | None, Query(max_length=60)] = None,
    polarity: Polarity | None = None,
    powertrain: Powertrain | None = None,
) -> StatsResponse:
    try:
        rows = tools.feedback_stats(group_by, line=line, market=market, domain=domain, polarity=polarity,
                                    powertrain=powertrain)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise _unavailable(e)
    return StatsResponse(group_by=group_by, total=sum(r["n"] for r in rows),
                         rows=[StatRow(key=r["key"], n=r["n"]) for r in rows])


@router.get("/filters")
def filters() -> dict:
    try:
        return tools.filters()
    except Exception as e:
        raise _unavailable(e)


@router.get("/{kind}/{evidence_id}", response_model=CitationOut)
def cite(kind: EvidenceKind, evidence_id: UUID) -> CitationOut:
    try:
        c = tools.cite(kind, str(evidence_id))
    except LookupError:
        raise HTTPException(status_code=404, detail="no such evidence row")
    except Exception as e:
        raise _unavailable(e)
    return CitationOut(**asdict(c))
