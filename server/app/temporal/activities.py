import asyncio
from typing import Any

from temporalio import activity

from app.core.config import github_app_credentials
from app.services.aggregation import aggregate_specialist_results
from app.services.gemini import MAX_DIFF_CHARACTERS
from app.services.github_api import (
    GitHubAppClient,
    RepositoryFile,
    review_comment_marker,
)
from app.services.retrieval import RetrievalService
from app.services.routing import route_review
from app.services.review_queue import ReviewQueueService
from app.services.tenant_store import workspace_for_installation
from app.services.outcome_retrieval import embed_pending_outcomes
from app.services.outcome_retrieval import find_similar_outcomes
from app.services.specialist_runner import SpecialistRunResult
from app.services.telemetry import ReviewContext, instrument_activity
from app.agents import SPECIALIST_AGENTS
from app.workers.review import format_aggregated_review_comment
from app.schemas.findings import assign_finding_ids


@activity.defn
@instrument_activity(phase="fetch")
async def fetch_review_context(input: dict[str, Any]) -> dict[str, Any]:
    """Fetch GitHub data needed by the deterministic workflow."""
    values = _workflow_input_values(input)
    app_id, private_key_path = github_app_credentials()
    github = GitHubAppClient(app_id=app_id, private_key_path=private_key_path)
    token = await github.installation_token(values["installation_id"])
    diff = await github.pull_request_diff(
        repository=values["repository"],
        pr_number=values["pr_number"],
        installation_token=token,
    )
    repository_files = await github.pull_request_repository_context(
        repository=values["repository"],
        pr_number=values["pr_number"],
        head_sha=values["head_sha"],
        installation_token=token,
    )
    title, description = await github.pull_request_details(
        repository=values["repository"],
        pr_number=values["pr_number"],
        installation_token=token,
    )
    # Installation ownership is the data boundary for the review queue.
    # Older installations may not be linked yet; those reviews remain
    # unassigned until the GitHub installation callback has completed.
    workspace_id = await workspace_for_installation(values["installation_id"])
    if workspace_id is None:
        raise RuntimeError(
            "GitHub App installation is not linked to a workspace; reinstall it "
            "using the authenticated Perchly install link"
        )
    return {
        **values,
        "workspace_id": workspace_id,
        "title": title,
        "description": description,
        "diff": diff,
        "repository_files": [
            {"path": file.path, "content": file.content} for file in repository_files
        ],
    }


@activity.defn
@instrument_activity(phase="retrieval")
async def retrieve_repository_context(
    fetched: dict[str, Any],
) -> dict[str, Any]:
    """Embed and retrieve specialist-specific repository context."""
    repository_files = [
        RepositoryFile(path=file["path"], content=file["content"])
        for file in fetched["repository_files"]
    ]
    ctx = ReviewContext(
        review_run_id=activity.info().workflow_id,
        repository=fetched["repository"],
        pr_number=fetched["pr_number"],
        head_sha=fetched["head_sha"],
        agent="retrieval",
    )
    contexts = await RetrievalService().build_contexts(
        repository=fetched["repository"],
        head_sha=fetched["head_sha"],
        diff=fetched["diff"],
        repository_files=repository_files,
        telemetry_ctx=ctx,
    )
    historical_outcomes: dict[str, list[dict[str, Any]]] = {}
    categories = tuple(contexts)
    results = await asyncio.gather(
        *(
            find_similar_outcomes(
                repository=fetched["repository"],
                category=category,
                finding={
                    "category": category,
                    "message": fetched["diff"][:4000],
                },
                limit=5,
            )
            for category in categories
        ),
        return_exceptions=True,
    )
    for category, result in zip(categories, results, strict=True):
        if isinstance(result, BaseException):
            # Historical examples are optional context; a database/API failure
            # must not prevent the current review from running.
            historical_outcomes[category] = []
        else:
            historical_outcomes[category] = result
    return {**fetched, "contexts": contexts, "historical_outcomes": historical_outcomes}


@activity.defn
@instrument_activity(phase="agent")
async def run_specialist(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one independently managed specialist activity."""
    category = payload["category"]
    specialist = next(agent for agent in SPECIALIST_AGENTS if agent.category == category)
    retrieved = payload["retrieved"]
    ctx = ReviewContext(
        review_run_id=activity.info().workflow_id,
        repository=retrieved["repository"],
        pr_number=retrieved["pr_number"],
        head_sha=retrieved["head_sha"],
        agent=category,
    )
    review = await specialist.review(
        title=retrieved["title"],
        description=retrieved["description"],
        diff=retrieved["diff"],
        retrieved_context=retrieved["contexts"].get(category, ""),
        historical_outcomes=retrieved.get("historical_outcomes", {}).get(category, []),
        telemetry_ctx=ctx,
    )
    return {"category": category, "review": review.model_dump()}


@activity.defn
@instrument_activity(phase="cleanup")
async def release_review_claim(input: dict[str, Any]) -> None:
    """Release a claimed PR head so a failed workflow can be retried."""
    from app.services.idempotency import IdempotencyStore

    IdempotencyStore().release_review(
        repository=input["repository"],
        pr_number=input["pr_number"],
        head_sha=input["head_sha"],
    )


@activity.defn
@instrument_activity(phase="aggregation")
async def aggregate_review(
    specialist_payload: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate specialist output into a serializable review payload."""
    result = SpecialistRunResult(
        results={
            category: _review_result(payload)
            for category, payload in specialist_payload["specialist_results"].items()
        },
        failures=specialist_payload["specialist_failures"],
    )
    aggregated = aggregate_specialist_results(result)
    findings = assign_finding_ids(
        aggregated.findings,
        repository=specialist_payload["repository"],
        pr_number=specialist_payload["pr_number"],
        head_sha=specialist_payload["head_sha"],
    )
    return {
        "findings": [finding.model_dump() for finding in findings],
        "failures": aggregated.failures,
    }


@activity.defn
@instrument_activity(phase="routing")
async def route_aggregated_review(review: dict[str, Any]) -> dict[str, Any]:
    """Apply confidence and failure policy before any GitHub post."""
    fetched = review["fetched"]
    aggregated = review["review"]
    decision = route_review(
        findings=[_finding_result(finding) for finding in aggregated["findings"]],
        failures=aggregated["failures"],
        unresolved_errors=aggregated.get("unresolved_errors", []),
    )
    if decision.mode == "needs_approval":
        queue_item_id = await ReviewQueueService().enqueue(
            delivery_id=fetched["delivery_id"],
            repository=fetched["repository"],
            pr_number=fetched["pr_number"],
            head_sha=fetched["head_sha"],
            review_payload={
                "review": aggregated,
                "title": fetched["title"],
                "description": fetched["description"],
                "diff": fetched["diff"],
                # An installation id is not a secret and lets a later
                # reviewer-approved fix PR mint a fresh short-lived token.
                "installation_id": fetched["installation_id"],
                "repository_files": fetched["repository_files"],
                "contexts": fetched.get("contexts", {}),
            },
            specialist_failures=aggregated["failures"],
            reason=decision.reason,
            workspace_id=fetched.get("workspace_id"),
        )
        return {"mode": decision.mode, "reason": decision.reason, "queue_item_id": queue_item_id}
    return {"mode": decision.mode, "reason": decision.reason, "queue_item_id": None}


@activity.defn
@instrument_activity(phase="persistence")
async def persist_automatic_decision(payload: dict[str, Any]) -> int:
    fetched = payload["fetched"]
    result = await ReviewQueueService().record_automatic_decision(
        delivery_id=fetched["delivery_id"],
        repository=fetched["repository"],
        pr_number=fetched["pr_number"],
        head_sha=fetched["head_sha"],
        review_payload=payload["review"],
        reason=payload["reason"],
    )
    await embed_pending_outcomes()
    return result


@activity.defn
@instrument_activity(phase="persistence")
async def persist_reviewer_decision(payload: dict[str, Any]) -> int:
    result = await ReviewQueueService().record_reviewer_decision(
        queue_item_id=payload["queue_item_id"],
        decision=payload["decision"],
    )
    await embed_pending_outcomes()
    return result


@activity.defn
@instrument_activity(phase="validation")
async def validate_edited_review(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate an edited review before it is persisted or posted."""
    review = payload["review"]
    if not isinstance(review, dict) or not isinstance(review.get("findings"), list):
        raise ValueError("edited review must contain a findings list")
    failures = review.get("failures", {})
    if not isinstance(failures, dict):
        raise ValueError("edited review failures must be an object")
    findings = [
        _finding_result(entry) for entry in review["findings"]
    ]
    findings = assign_finding_ids(
        findings,
        repository=payload["repository"],
        pr_number=payload["pr_number"],
        head_sha=payload["head_sha"],
    )
    return {
        "findings": [finding.model_dump() for finding in findings],
        "failures": {str(key): str(value) for key, value in failures.items()},
    }


@activity.defn
@instrument_activity(phase="posting")
async def post_review(payload: dict[str, Any]) -> bool:
    """Render and post the aggregated review through GitHub."""
    review = payload["review"]
    fetched = payload["fetched"] if "fetched" in payload else None
    if fetched is None:
        raise ValueError("post_review requires fetched GitHub context")
    values = _workflow_input_values(fetched)
    app_id, private_key_path = github_app_credentials()
    github = GitHubAppClient(app_id=app_id, private_key_path=private_key_path)
    # Retrieve short-lived credentials inside the activity.  Do not place the
    # installation token in workflow payloads/history.
    token = await github.installation_token(values["installation_id"])
    comment = format_aggregated_review_comment(
        _aggregated_review(review),
        was_truncated=payload["diff_characters"] > MAX_DIFF_CHARACTERS,
    )
    return await github.create_idempotent_pull_request_comment(
        repository=values["repository"],
        pr_number=values["pr_number"],
        body=comment,
        marker=review_comment_marker(
            repository=values["repository"],
            pr_number=values["pr_number"],
            head_sha=values["head_sha"],
        ),
        installation_token=token,
    )


def _workflow_input_values(input: dict[str, Any]) -> dict[str, Any]:
    return {
        "delivery_id": input["delivery_id"],
        "repository": input["repository"],
        "pr_number": input["pr_number"],
        "head_sha": input["head_sha"],
        "installation_id": input["installation_id"],
    }


def _review_result(payload: dict[str, Any]):
    from app.schemas.findings import ReviewResult

    return ReviewResult.model_validate(payload)


def _finding_result(payload: dict[str, Any]):
    from app.schemas.findings import Finding

    return Finding.model_validate(payload)


def _aggregated_review(payload: dict[str, Any]):
    from app.services.aggregation import AggregatedReview

    from app.schemas.findings import Finding

    return AggregatedReview(
        findings=tuple(Finding.model_validate(finding) for finding in payload["findings"]),
        failures=payload["failures"],
    )
