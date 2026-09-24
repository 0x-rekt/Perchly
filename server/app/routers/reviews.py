import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.reviews import EditReviewRequest, FixPullRequestRequest, ReviewDecisionRequest
from app.core.config import github_app_credentials
from app.services.fix_pr import FixPatch, FixPrError, PatchFile, build_patch, create_fix_pr
from app.services.github_api import GitHubApiError, GitHubAppClient
from app.services.review_queue import ReviewQueueService
from app.services.auth import get_current_user
from app.temporal.client import (
    review_workflow_id,
    send_signal_by_workflow_id,
)
from app.temporal.workflows import ReviewDecisionInput

router = APIRouter(prefix="/reviews", tags=["reviews"])
queue = ReviewQueueService()
logger = logging.getLogger(__name__)


@router.get("/queue")
async def list_review_queue(user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    return await queue.list_items(workspace_id=_workspace_id(user))


@router.get("/queue/{queue_item_id}")
async def get_review_queue_item(queue_item_id: int, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    item = await _require_item(queue_item_id, _workspace_id(user))
    return _with_workflow_id(item)


@router.post("/queue/{queue_item_id}/approve")
async def approve_review(queue_item_id: int, request: ReviewDecisionRequest, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return await _resolve(queue_item_id, "approve", request.reviewer, request.comment, workspace_id=_workspace_id(user))


@router.post("/queue/{queue_item_id}/reject")
async def reject_review(queue_item_id: int, request: ReviewDecisionRequest, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return await _resolve(queue_item_id, "reject", request.reviewer, request.comment, workspace_id=_workspace_id(user))


@router.post("/queue/{queue_item_id}/edit")
async def edit_review(queue_item_id: int, request: EditReviewRequest, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return await _resolve(
        queue_item_id,
        "edit",
        request.reviewer,
        request.comment,
        request.edited_review.model_dump(), workspace_id=_workspace_id(user),
    )


@router.post("/queue/{queue_item_id}/findings/{finding_id}/fix-pr/preview")
async def preview_fix_pr(
    queue_item_id: int, finding_id: str, request: FixPullRequestRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate and persist a patch without changing GitHub."""
    item = await _require_item(queue_item_id, _workspace_id(user))
    if item["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Review is already resolved")
    review = item.get("review_payload", {}).get("review", {})
    findings = review.get("findings", []) if isinstance(review, dict) else []
    finding = next(
        (value for value in findings if isinstance(value, dict) and value.get("finding_id") == finding_id),
        None,
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found in review")
    try:
        patch = build_patch(
            finding=finding,
            repository_files=item.get("review_payload", {}).get("repository_files", []),
        )
        fix_id = await queue.save_fix_preview(
            queue_item_id=queue_item_id,
            finding_id=finding_id,
            reviewer=request.reviewer,
            patch={
                "files": [
                    {"path": value.path, "before": value.before, "after": value.after, "diff": value.diff}
                    for value in patch.files
                ],
                "diff": patch.diff,
            },
        )
    except FixPrError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "fix_id": fix_id,
        "finding_id": finding_id,
        "diff": patch.diff,
        "files": [value.path for value in patch.files],
    }


@router.post("/fix-pr/{fix_id}/create")
async def create_review_fix_pr(fix_id: int, request: FixPullRequestRequest, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Create the already-previewed patch, idempotently."""
    fix = await queue.get_fix_preview(fix_id)
    if fix is None:
        raise HTTPException(status_code=404, detail="Fix preview not found")
    if fix["status"] == "created" and fix.get("pull_request_url"):
        return {"fix_id": fix_id, "pull_request_url": fix["pull_request_url"], "branch": fix["branch"]}
    item = await _require_item(int(fix["queue_item_id"]), _workspace_id(user))
    installation_id = item.get("review_payload", {}).get("installation_id")
    if not isinstance(installation_id, int):
        raise HTTPException(status_code=409, detail="This review does not have GitHub installation context")
    finding = next(
        (value for value in item.get("review_payload", {}).get("review", {}).get("findings", [])
         if isinstance(value, dict) and value.get("finding_id") == fix["finding_id"]),
        None,
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found in review")
    try:
        files = tuple(PatchFile(**value) for value in fix["patch"]["files"])
        patch = FixPatch(files=files, diff=fix["patch"]["diff"])
        app_id, private_key_path = github_app_credentials()
        github = GitHubAppClient(app_id=app_id, private_key_path=private_key_path)
        token = await github.installation_token(installation_id)
        result = await create_fix_pr(
            github=github, repository=item["repository"], pr_number=item["pr_number"],
            head_sha=item["head_sha"], finding=finding, patch=patch,
            installation_token=token,
        )
        await queue.mark_fix_created(fix_id=fix_id, reviewer=request.reviewer, branch=result.branch, url=result.url)
    except FixPrError as error:
        try:
            await queue.mark_fix_failed(fix_id=fix_id)
        except Exception:
            logger.exception("Unable to mark fix preview failed fix_id=%s", fix_id)
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        try:
            await queue.mark_fix_failed(fix_id=fix_id)
        except Exception:
            logger.exception("Unable to mark fix preview failed fix_id=%s", fix_id)
        if isinstance(error, GitHubApiError):
            logger.error(
                "Fix PR GitHub request failed fix_id=%s repository=%s status=%s response=%s",
                fix_id, item["repository"], error.status_code, error.response_text,
            )
        else:
            logger.exception("Fix PR creation failed fix_id=%s repository=%s", fix_id, item["repository"])
        raise HTTPException(status_code=502, detail="GitHub could not create the fix PR") from error
    return {"fix_id": fix_id, "pull_request_url": result.url, "branch": result.branch}


def _workspace_id(user: dict[str, Any] | None) -> int | None:
    if not isinstance(user, dict):
        return None
    value = user.get("workspace_id")
    if not isinstance(value, int):
        raise HTTPException(status_code=403, detail="User is not assigned to a workspace")
    return value


async def _require_item(queue_item_id: int, workspace_id: int | None = None) -> dict[str, Any]:
    # Keep direct service fakes/backwards-compatible callers working while
    # production requests always pass the authenticated workspace boundary.
    item = (await queue.get_item(queue_item_id)
            if workspace_id is None
            else await queue.get_item(queue_item_id, workspace_id=workspace_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Review queue item not found")
    return item


async def _resolve(
    queue_item_id: int,
    decision: str,
    reviewer: str,
    comment: str | None,
    edited_review: dict[str, Any] | None = None,
    workspace_id: int | None = None,
) -> dict[str, Any]:
    item = await _require_item(queue_item_id, workspace_id)
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
    updated = await _require_item(queue_item_id, workspace_id)
    return {**_with_workflow_id(updated), "decision": decision, "accepted": True}


def review_workflow_id_from_item(item: dict[str, Any]) -> str:
    return review_workflow_id_from_values(item["repository"], item["pr_number"], item["head_sha"])


def review_workflow_id_from_values(repository: str, pr_number: int, head_sha: str) -> str:
    return f"perchly-review-{repository}-{pr_number}-{head_sha}"


def _with_workflow_id(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "workflow_id": review_workflow_id_from_item(item)}
