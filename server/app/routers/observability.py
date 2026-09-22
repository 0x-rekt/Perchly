"""Observability endpoints: overview metrics, trace listing, and trace detail."""

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.config import OBSERVABILITY_API_KEY
from app.services import telemetry

router = APIRouter(prefix="/observability", tags=["observability"])


def _require_observability_key(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    """Require the configured dashboard key; fail closed when configured."""
    if not OBSERVABILITY_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Observability API is not configured",
        )
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else None
    if x_api_key != OBSERVABILITY_API_KEY and bearer != OBSERVABILITY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid observability credentials")


@router.get("/overview")
async def overview(
    days: int = Query(default=14, ge=1, le=90),
    _: None = Depends(_require_observability_key),
) -> dict[str, Any]:
    """Aggregate volume, cost, latency-by-phase, HITL queue, and acceptance rate."""
    return await asyncio.to_thread(telemetry.overview_metrics, days)


@router.get("/traces")
async def traces(
    repository: str | None = None,
    agent: str | None = None,
    pr_number: int | None = Query(default=None, ge=1),
    head_sha: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    _: None = Depends(_require_observability_key),
) -> dict[str, Any]:
    """List review runs (traces), newest first."""
    if since and until and since >= until:
        raise HTTPException(status_code=422, detail="since must be before until")
    items = await asyncio.to_thread(
        telemetry.list_traces,
        repository=repository,
        agent=agent,
        pr_number=pr_number,
        head_sha=head_sha,
        since=since,
        until=until,
        limit=limit,
    )
    return {"count": len(items), "items": items}


@router.get("/traces/{review_run_id:path}")
async def trace_detail(
    review_run_id: str,
    _: None = Depends(_require_observability_key),
) -> dict[str, Any]:
    """Return one trace with its ordered spans."""
    item = await asyncio.to_thread(telemetry.get_trace, review_run_id=review_run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return item
