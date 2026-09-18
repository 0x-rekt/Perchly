from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.schemas.reviews import EditReviewRequest, ReviewDecisionRequest
from app.services.review_queue import ReviewQueueService
from app.temporal.client import (
    review_workflow_id,
    send_signal_by_workflow_id,
)
from app.temporal.workflows import ReviewDecisionInput

router = APIRouter(prefix="/reviews", tags=["reviews"])
queue = ReviewQueueService()


@router.get("/queue")
async def list_review_queue() -> list[dict[str, Any]]:
    return await queue.list_items()


@router.get("/queue/{queue_item_id}")
async def get_review_queue_item(queue_item_id: int) -> dict[str, Any]:
    item = await _require_item(queue_item_id)
    return _with_workflow_id(item)


@router.post("/queue/{queue_item_id}/approve")
async def approve_review(queue_item_id: int, request: ReviewDecisionRequest) -> dict[str, Any]:
    return await _resolve(queue_item_id, "approve", request.reviewer, request.comment)


@router.post("/queue/{queue_item_id}/reject")
async def reject_review(queue_item_id: int, request: ReviewDecisionRequest) -> dict[str, Any]:
    return await _resolve(queue_item_id, "reject", request.reviewer, request.comment)


@router.post("/queue/{queue_item_id}/edit")
async def edit_review(queue_item_id: int, request: EditReviewRequest) -> dict[str, Any]:
    return await _resolve(
        queue_item_id,
        "edit",
        request.reviewer,
        request.comment,
        request.edited_review.model_dump(),
    )


async def _require_item(queue_item_id: int) -> dict[str, Any]:
    item = await queue.get_item(queue_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review queue item not found")
    return item


async def _resolve(
    queue_item_id: int,
    decision: str,
    reviewer: str,
    comment: str | None,
    edited_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = await _require_item(queue_item_id)
    if item["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Review is already resolved")

    workflow_id = review_workflow_id_from_item(item)
    try:
        # Temporal is the single owner of decision persistence. The signal is
        # durable; the workflow records the decision before posting/rejecting.
        await send_signal_by_workflow_id(
            workflow_id,
            {"approve": "approve_review", "reject": "reject_review", "edit": "edit_review"}[decision],
            ReviewDecisionInput(
                decision=decision,
                reviewer=reviewer,
                edited_review=edited_review,
                comment=comment,
            ),
        )
    except Exception as error:
        raise HTTPException(status_code=503, detail="Review workflow is unavailable") from error

    # The workflow activity may not have run yet, so the item can remain
    # pending briefly after the signal is accepted.
    updated = await _require_item(queue_item_id)
    return {**_with_workflow_id(updated), "decision": decision, "accepted": True}


def review_workflow_id_from_item(item: dict[str, Any]) -> str:
    return review_workflow_id_from_values(item["repository"], item["pr_number"], item["head_sha"])


def review_workflow_id_from_values(repository: str, pr_number: int, head_sha: str) -> str:
    return f"perchly-review-{repository}-{pr_number}-{head_sha}"


def _with_workflow_id(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "workflow_id": review_workflow_id_from_item(item)}
