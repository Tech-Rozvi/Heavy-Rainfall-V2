"""
ROZVI scientific API routes (Phase 9).

Requires FastAPI at import time. Core logic lives in src.rozvi.api_handlers
so it can be tested without FastAPI installed.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.rozvi import api_handlers as H

router = APIRouter(prefix="/v1/rozvi", tags=["rozvi"])


class ReturnPeriodRequest(BaseModel):
    annual_maxima_mm: list[float] = Field(..., min_length=5)
    return_periods: list[int] = Field(default=[10, 50, 100])
    n_bootstrap: int = Field(default=80, ge=10, le=500)
    ci_level: float = Field(default=0.9, gt=0.5, lt=1.0)


class EventHydrologyRequest(BaseModel):
    hyetograph_mm: list[float] = Field(..., min_length=1)
    area_km2: float = Field(..., gt=0)
    curve_number: float = Field(default=75.0, ge=30.0, le=98.0)
    dt_h: float = Field(default=1.0, gt=0)
    loss_method: str = Field(default="curve_number")


class ChainStageIn(BaseModel):
    stage: str
    confidence: str
    quantified: bool = False
    estimate: Optional[float] = None
    interval_low: Optional[float] = None
    interval_high: Optional[float] = None
    validation_status: str = "not_validated"


class ChainRequest(BaseModel):
    stages: list[ChainStageIn]


@router.get("/info")
def rozvi_info() -> dict[str, Any]:
    return H.info()


@router.get("/capabilities")
def capabilities_summary() -> dict[str, Any]:
    return H.capabilities()


@router.post("/return-periods")
def return_periods(body: ReturnPeriodRequest) -> dict[str, Any]:
    try:
        return H.compute_return_periods(
            body.annual_maxima_mm,
            return_periods=body.return_periods,
            n_bootstrap=body.n_bootstrap,
            ci_level=body.ci_level,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, detail=str(exc)) from exc


@router.post("/event-hydrology")
def event_hydrology(body: EventHydrologyRequest) -> dict[str, Any]:
    try:
        return H.compute_event_hydrology(
            body.hyetograph_mm,
            area_km2=body.area_km2,
            curve_number=body.curve_number,
            dt_h=body.dt_h,
            loss_method=body.loss_method,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, detail=str(exc)) from exc


@router.post("/chain")
def chain_uncertainty(body: ChainRequest) -> dict[str, Any]:
    try:
        stages = [s.model_dump() if hasattr(s, "model_dump") else s.dict() for s in body.stages]
        return H.compute_chain(stages)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, detail=str(exc)) from exc
