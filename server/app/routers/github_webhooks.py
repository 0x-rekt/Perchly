import json
import logging
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.core.config import GITHUB_WEBHOOK_SECRET
from app.schemas.github import PullRequestWebhookPayload
from app.temporal.client import start_review_workflow
from app.temporal.workflows import ReviewWorkflowInput
from app.services.idempotency import IdempotencyStore
from app.services.github_webhooks import valid_github_signature
from app.services.github_api import GENERATED_FIX_PR_MARKER
from app.services.review_queue import ReviewQueueService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["github"])

SUPPORTED_PULL_REQUEST_ACTIONS = frozenset({"opened", "reopened", "synchronize"})
idempotency_store = IdempotencyStore()
review_queue = ReviewQueueService()


def is_supported_pull_request_action(action: str) -> bool:
    return action in SUPPORTED_PULL_REQUEST_ACTIONS


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def receive_github_events(
    request: Request,
    x_github_event: Annotated[str | None, Header()] = None,
    x_github_delivery: Annotated[str | None, Header()] = None,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Accept authenticated PR events without making GitHub wait for review work."""
    if not GITHUB_WEBHOOK_SECRET:
        logger.error("GITHUB_WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=500, detail="Webhook receiver is not configured")

    raw_body = await request.body()
    if not valid_github_signature(
        raw_body=raw_body,
        signature=x_hub_signature_256,
        webhook_secret=GITHUB_WEBHOOK_SECRET,
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if x_github_event in {
        "pull_request_review",
        "pull_request_review_comment",
        "pull_request_review_thread",
        "issue_comment",
    }:
        try:
            event = json.loads(raw_body)
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=400, detail="Invalid GitHub event payload") from error
        action = event.get("action")
        outcome = {
            "dismissed": "dismissed",
            "resolved": "resolved",
            "deleted": "dismissed",
        }.get(action)
        body = ""
        for key in ("review", "comment"):
            value = event.get(key)
            if isinstance(value, dict) and isinstance(value.get("body"), str):
                body = value["body"]
                break
        pull_request = event.get("pull_request") or {}
        repository = event.get("repository") or {}
        head = pull_request.get("head") or {}
        if x_github_event == "issue_comment" and "<!-- perchly-review:" in body:
            marker = body.split("<!-- perchly-review:", 1)[1].split("-->", 1)[0].strip()
            marker_parts = marker.rsplit(":", 2)
            if len(marker_parts) == 3:
                repository_name, marker_pr, marker_sha = marker_parts
                repository = {"full_name": repository_name}
                pull_request = {"number": int(marker_pr) if marker_pr.isdigit() else None}
                head = {"sha": marker_sha}
        if (
            outcome is None
            or "<!-- perchly-review:" not in body
            or not isinstance(repository.get("full_name"), str)
            or not isinstance(pull_request.get("number"), int)
            or not isinstance(head.get("sha"), str)
        ):
            return {"status": "ignored", "reason": "unsupported outcome event"}
        count = await review_queue.record_external_outcome(
            repository=repository["full_name"],
            pr_number=pull_request["number"],
            head_sha=head["sha"],
            final_outcome=outcome,
        )
        return {"status": "recorded", "outcome": outcome, "examples": str(count)}

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": "unsupported event"}

    if not x_github_delivery:
        raise HTTPException(status_code=400, detail="Missing GitHub delivery ID")

    try:
        payload = PullRequestWebhookPayload.model_validate_json(raw_body)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid pull request payload") from error

    if not is_supported_pull_request_action(payload.action):
        return {"status": "ignored", "reason": "unsupported pull request action"}

    # Fix PRs remain ordinary GitHub PRs for human review, but their own
    # opened/synchronize events must not recursively start another Perchly run.
    try:
        raw_event = json.loads(raw_body)
    except json.JSONDecodeError:
        raw_event = {}
    pull_request_body = (raw_event.get("pull_request") or {}).get("body")
    if isinstance(pull_request_body, str) and GENERATED_FIX_PR_MARKER in pull_request_body:
        logger.info(
            "Ignoring Perchly-generated fix PR repository=%s pr_number=%s",
            payload.repository.full_name,
            payload.pull_request.number,
        )
        return {"status": "ignored", "reason": "perchly-generated fix PR"}

    if not idempotency_store.claim(
        delivery_id=x_github_delivery,
        repository=payload.repository.full_name,
        pr_number=payload.pull_request.number,
        head_sha=payload.pull_request.head.sha,
    ):
        logger.info("Ignoring duplicate review delivery_id=%s", x_github_delivery)
        return {"status": "ignored", "reason": "duplicate delivery or reviewed commit"}

    try:
        await start_review_workflow(
            ReviewWorkflowInput(
                delivery_id=x_github_delivery,
                repository=payload.repository.full_name,
                pr_number=payload.pull_request.number,
                head_sha=payload.pull_request.head.sha,
                installation_id=payload.installation.id,
            )
        )
    except Exception as error:
        logger.exception("Unable to start Temporal review delivery_id=%s", x_github_delivery)
        idempotency_store.release_review(
            repository=payload.repository.full_name,
            pr_number=payload.pull_request.number,
            head_sha=payload.pull_request.head.sha,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Review workflow is unavailable",
        ) from error
    return {"status": "accepted", "delivery_id": x_github_delivery}
