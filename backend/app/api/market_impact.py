"""Cited optional equipment and automatic directional assessment. No share forecast is inferred."""
from fastapi import APIRouter, HTTPException

from app.knowledge import tools
from app.agents import market_impact_agent, market_impact_web

from .evidence import _hit
from .schemas import Line, MarketOptionsOut, MarketAssessmentIn, MarketAssessmentOut, MarketWebOut

router = APIRouter(prefix="/market-impact", tags=["market impact"])


@router.get("/options", response_model=MarketOptionsOut)
def options(line: Line) -> MarketOptionsOut:
    try:
        hits = tools.get_options(line=line, status="optional", limit=201)
    except Exception:
        raise HTTPException(status_code=503, detail="Optional equipment catalog is unavailable.")
    return MarketOptionsOut(line=line, options=[_hit(h) for h in hits[:200]], truncated=len(hits) > 200)


@router.post("/assessment", response_model=MarketAssessmentOut)
def assessment(body: MarketAssessmentIn) -> dict:
    try:
        return market_impact_agent.assess(body.line, option_id=str(body.option_id) if body.option_id else None,
                                         feature=body.feature)
    except LookupError:
        raise HTTPException(status_code=404, detail="Optional equipment was not found for this vehicle line.")
    except Exception:
        raise HTTPException(status_code=503, detail="Market assessment is unavailable. Try again.")


@router.post("/web-assessment", response_model=MarketWebOut)
def web_assessment(body: MarketAssessmentIn) -> dict:
    try:
        return market_impact_web.assess(body.line, option_id=str(body.option_id) if body.option_id else None,
                                       feature=body.feature)
    except LookupError:
        raise HTTPException(status_code=404, detail="Optional equipment was not found for this vehicle line.")
    except Exception:
        raise HTTPException(status_code=503, detail="Public web research is unavailable. Internal feedback remains available. Try again.")
