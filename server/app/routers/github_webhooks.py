import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

from app.core.config import GITHUB_WEBHOOK_SECRET
from app.schemas.github import PullRequestWebhookPayload
from app.services.github_webhooks import valid_github_signature
from app.workers.review import review_pull_request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["github"])

SUPPORTED_PULL_REQUEST_ACTIONS = frozenset({"opened", "reopened", "synchronize"})


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def receive_github_events(
    request: Request,
    background_tasks: BackgroundTasks,
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

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": "unsupported event"}

    if not x_github_delivery:
        raise HTTPException(status_code=400, detail="Missing GitHub delivery ID")

    try:
        payload = PullRequestWebhookPayload.model_validate_json(raw_body)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid pull request payload") from error

    if payload.action not in SUPPORTED_PULL_REQUEST_ACTIONS:
        return {"status": "ignored", "reason": "unsupported pull request action"}

    background_tasks.add_task(
        review_pull_request,
        delivery_id=x_github_delivery,
        repository=payload.repository.full_name,
        pr_number=payload.pull_request.number,
        head_sha=payload.pull_request.head.sha,
        installation_id=payload.installation.id,
    )
    return {"status": "accepted", "delivery_id": x_github_delivery}
