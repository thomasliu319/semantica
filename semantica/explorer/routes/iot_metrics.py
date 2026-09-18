"""Compose additive IoT measures into derived metrics for Analyze."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..iot_metrics import catalog, compose

router = APIRouter(prefix="/api/iot/metrics", tags=["IoT Metrics"])


class DerivedSpec(BaseModel):
    id: str
    op: str
    a: str
    b: Optional[str] = None
    name_zh: Optional[str] = None
    not_label: Optional[str] = Field(default=None, alias="not")
    domain: Optional[str] = None

    model_config = {"populate_by_name": True}


class ComposeRequest(BaseModel):
    grain: str = "type_month"
    bases: Optional[List[str]] = None
    derived: Optional[List[DerivedSpec]] = None
    apply_presets: bool = True
    limit: int = Field(200, ge=1, le=500)


@router.get("/catalog")
async def get_metric_catalog() -> Dict[str, Any]:
    return catalog()


@router.post("/compose")
async def compose_metrics(body: ComposeRequest) -> Dict[str, Any]:
    recipes = []
    for item in body.derived or []:
        payload = item.model_dump(by_alias=True)
        if payload.get("not") is None and item.not_label:
            payload["not"] = item.not_label
        recipes.append(payload)
    try:
        return compose(
            grain=body.grain,
            bases=body.bases,
            derived=recipes or None,
            apply_presets=body.apply_presets,
            limit=body.limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"cleaned parquet not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
