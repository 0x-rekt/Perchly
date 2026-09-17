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
from app.services.specialist_runner import SpecialistRunResult
from app.agents import SPECIALIST_AGENTS
from app.workers.review import format_aggregated_review_comment


@activity.defn
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
    return {
        **values,
        "title": title,
        "description": description,
        "diff": diff,
        "repository_files": [
            {"path": file.path, "content": file.content} for file in repository_files
        ],
    }


@activity.defn
async def retrieve_repository_context(
    fetched: dict[str, Any],
) -> dict[str, Any]:
    """Embed and retrieve specialist-specific repository context."""
    repository_files = [
        RepositoryFile(path=file["path"], content=file["content"])
        for file in fetched["repository_files"]
    ]
    contexts = await RetrievalService().build_contexts(
        repository=fetched["repository"],
        head_sha=fetched["head_sha"],
        diff=fetched["diff"],
        repository_files=repository_files,
    )
    return {**fetched, "contexts": contexts}


@activity.defn
async def run_specialist(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one independently managed specialist activity."""
    category = payload["category"]
    specialist = next(agent for agent in SPECIALIST_AGENTS if agent.category == category)
    retrieved = payload["retrieved"]
    review = await specialist.review(
        title=retrieved["title"],
        description=retrieved["description"],
        diff=retrieved["diff"],
        retrieved_context=retrieved["contexts"].get(category, ""),
    )
    return {"category": category, "review": review.model_dump()}


@activity.defn
async def release_review_claim(input: dict[str, Any]) -> None:
    """Release a claimed PR head so a failed workflow can be retried."""
    from app.services.idempotency import IdempotencyStore

    IdempotencyStore().release_review(
        repository=input["repository"],
        pr_number=input["pr_number"],
        head_sha=input["head_sha"],
    )


@activity.defn
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
    return {
        "findings": [finding.model_dump() for finding in aggregated.findings],
        "failures": aggregated.failures,
    }


@activity.defn
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


def _aggregated_review(payload: dict[str, Any]):
    from app.services.aggregation import AggregatedReview

    from app.schemas.findings import Finding

    return AggregatedReview(
        findings=tuple(Finding.model_validate(finding) for finding in payload["findings"]),
        failures=payload["failures"],
    )
