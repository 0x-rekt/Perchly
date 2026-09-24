"""Observability endpoints: overview metrics, trace listing, and trace detail."""

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.auth import get_current_user
from app.services import telemetry

router = APIRouter(prefix="/observability", tags=["observability"])


def _require_workspace(user: dict[str, Any]) -> None:
    """Only expose dashboard data to authenticated workspace members."""
    if not isinstance(user.get("workspace_id"), int):
        raise HTTPException(status_code=403, detail="User is not assigned to a workspace")


@router.get("/overview")
async def overview(
    days: int = Query(default=14, ge=1, le=90),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Aggregate volume, cost, latency-by-phase, HITL queue, and acceptance rate."""
    _require_workspace(user)
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
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List review runs (traces), newest first."""
    _require_workspace(user)
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
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return one trace with its ordered spans."""
    _require_workspace(user)
    item = await asyncio.to_thread(telemetry.get_trace, review_run_id=review_run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return item
