"""Authenticated comparison API. All numbers, cohorts and means are server-owned."""
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.comparisons.research import research, revalidate
from app.knowledge import models
from .deps import get_conn

router=APIRouter(prefix='/models',tags=['model comparisons'])
Conn=Annotated[psycopg.Connection,Depends(get_conn)]
Market=Literal['EU','US','CN','RoW']

class ModelInput(BaseModel):
    name: str=Field(min_length=2,max_length=160)
    variant: str=Field(default='',max_length=120)
    powertrain: Literal['ICE','PHEV','BEV'] | None=None

class ResearchInput(BaseModel):
    variant: str=Field(default='',max_length=120)
    market: Market='EU'
    rival_name: str | None=Field(default=None,min_length=2,max_length=160)
    source_url: str | None=Field(default=None,max_length=2000)
    rival_variant: str=Field(default='',max_length=120)

class ValidationInput(BaseModel):
    variant: str=Field(default='',max_length=120)
    market: Market='EU'
    mode: Literal['reevaluate','recrawl']='reevaluate'
    observation_id: UUID | None=None
    rival_id: UUID | None=None


def error(e):
    if isinstance(e,models.ModelNotFound):return HTTPException(404,str(e))
    if isinstance(e,models.ResearchBusy):return HTTPException(409,str(e))
    if isinstance(e,ValueError):return HTTPException(422,str(e))
    if isinstance(e,psycopg.errors.UniqueViolation):return HTTPException(409,'A request for this model is already running.')
    if isinstance(e,psycopg.Error):return HTTPException(503,'Comparison database unavailable.')
    raise e

@router.get('')
def list_models(conn: Conn):
    try:
        result=models.list_models(conn);conn.commit()
        return jsonable_encoder({'models':result,'default_market':'EU','markets':[{'code':'EU','name':'Germany / Europe'},{'code':'US','name':'United States'},{'code':'CN','name':'China'},{'code':'RoW','name':'Rest of world'}]})
    except Exception as e:
        conn.rollback();raise error(e)

@router.post('',status_code=201)
def add_model(body: ModelInput,conn: Conn):
    try:
        if body.variant and not body.powertrain:raise ValueError('Select a powertrain for the specified variant.')
        row=models.add_model(conn,body.name,body.variant,body.powertrain);conn.commit();return jsonable_encoder(row)
    except Exception as e:
        conn.rollback();raise error(e)

@router.get('/{model_id}/overview')
def model_overview(model_id: UUID,conn: Conn,variant: Annotated[str,Query(max_length=120)]='',market: Market='EU'):
    try:return jsonable_encoder(models.overview(conn,model_id,variant,market))
    except Exception as e:raise error(e)

@router.post('/{model_id}/research')
def research_model(model_id: UUID,body: ResearchInput,conn: Conn):
    # Keep the request alive until the bounded research finishes. No untracked serverless background task.
    try:return jsonable_encoder(research(conn,str(model_id),body.variant,body.market,rival_name=body.rival_name,source_url=body.source_url,rival_variant=body.rival_variant))
    except Exception as e:
        conn.rollback();raise error(e)

@router.patch('/{model_id}/rivals/{rival_id}')
def toggle_rival(model_id: UUID,rival_id: UUID,conn: Conn,variant: str='',market: Market='EU',enabled: bool=True):
    try:
        models.toggle_rival(conn,model_id,rival_id,variant,market,enabled)
        conn.commit();return jsonable_encoder(models.overview(conn,model_id,variant,market))
    except Exception as e:
        conn.rollback();raise error(e)

@router.post('/{model_id}/validate')
def validate_model(model_id: UUID,body: ValidationInput,conn: Conn):
    try:return jsonable_encoder(revalidate(conn,str(model_id),body.variant,body.market,body.mode,
                                          str(body.observation_id) if body.observation_id else None,
                                          rival_id=str(body.rival_id) if body.rival_id else None))
    except Exception as e:
        conn.rollback();raise error(e)
