import asyncio

import pytest
from fastapi import HTTPException

import app.routers.reviews as reviews
from app.schemas.reviews import ReviewDecisionRequest
from app.services.review_queue import _queue_item


class FakeQueue:
    def __init__(self) -> None:
        self.items = {
            12: {
                "id": 12,
                "delivery_id": "delivery-1",
                "repository": "0x-rekt/Test-Perchly",
                "pr_number": 8,
                "head_sha": "sha123",
                "status": "pending",
            }
        }

    async def get_item(self, queue_item_id: int):
        return self.items.get(queue_item_id)

    async def list_items(self, *, status: str = "pending"):
        return [item for item in self.items.values() if item["status"] == status]


def test_approve_returns_updated_status_and_signals_workflow(monkeypatch) -> None:
    queue = FakeQueue()
    signals = []

    async def fake_signal(workflow_id, signal_name, decision):
        signals.append((workflow_id, signal_name, decision))

    monkeypatch.setattr(reviews, "queue", queue)
    monkeypatch.setattr(reviews, "send_signal_by_workflow_id", fake_signal)

    response = asyncio.run(
        reviews.approve_review(
            12, ReviewDecisionRequest(reviewer="reviewer@example.com")
        )
    )

    assert response["id"] == 12
    assert response["status"] == "pending"
    assert response["workflow_id"] == "perchly-review-0x-rekt/Test-Perchly-8-sha123"
    assert response["decision"] == "approve"
    assert response["accepted"] is True
    assert signals[0][1] == "approve_review"


def test_resolved_item_is_rejected(monkeypatch) -> None:
    queue = FakeQueue()
    queue.items[12]["status"] = "approved"
    monkeypatch.setattr(reviews, "queue", queue)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            reviews.reject_review(
                12, ReviewDecisionRequest(reviewer="reviewer@example.com")
            )
        )

    assert error.value.status_code == 409


def test_queue_item_accepts_rows_from_older_schema() -> None:
    item = _queue_item([1, "delivery", "owner/repo", 3, "sha", {}, {}, "pending", "review"])

    assert item["id"] == 1
    assert item["status"] == "pending"
    assert item["resolved_at"] is None
    assert item["resolved_by"] is None
