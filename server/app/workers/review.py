import logging

from app.core.config import github_app_credentials
from app.schemas.findings import Finding, ReviewResult
from app.services.aggregation import AggregatedReview, aggregate_specialist_results
from app.services.gemini import MAX_DIFF_CHARACTERS, review_diff
from app.services.github_api import GitHubAppClient
from app.services.idempotency import IdempotencyStore
from app.services.retrieval import RetrievalService
from app.services.specialist_runner import run_specialists

logger = logging.getLogger(__name__)
idempotency_store = IdempotencyStore()


def _release_failed_review(*, repository: str, pr_number: int, head_sha: str) -> None:
    idempotency_store.release_review(
        repository=repository, pr_number=pr_number, head_sha=head_sha
    )


def format_review_comment(review: ReviewResult, *, was_truncated: bool) -> str:
    """Create one readable Phase 0 PR comment from validated findings."""
    lines = ["## Perchly review", ""]
    if was_truncated:
        lines.append(
            "_Review scope was truncated for this initial version; only the first part of the diff was analyzed._"
        )
        lines.append("")

    if not review.findings:
        lines.append("No actionable findings in this automated review.")
        return "\n".join(lines)

    lines.append(f"Found {len(review.findings)} actionable issue(s):")
    lines.append("")
    for finding in review.findings:
        lines.extend(_format_finding(finding))
    return "\n".join(lines).rstrip()


def format_aggregated_review_comment(
    review: AggregatedReview, *, was_truncated: bool
) -> str:
    """Create the Phase 1 summary comment from aggregated specialist output."""
    lines = ["## Perchly review", ""]
    if was_truncated:
        lines.extend(
            [
                "_Review scope was truncated; only the first part of the diff was analyzed._",
                "",
            ]
        )

    if review.findings:
        category_summary = ", ".join(
            f"{count} {category.replace('_', ' ')}"
            for category, count in sorted(review.category_counts.items())
        )
        lines.append(f"Found {len(review.findings)} actionable issue(s): {category_summary}.")
    else:
        lines.append("No actionable findings from the available specialists.")

    if review.failures:
        unavailable = ", ".join(sorted(category.replace("_", " ") for category in review.failures))
        lines.append(f"Unavailable specialists: {unavailable}.")

    if review.findings:
        lines.append("")
        for finding in review.findings:
            lines.extend(_format_finding(finding))
    return "\n".join(lines).rstrip()


def _format_finding(finding: Finding) -> list[str]:
    location = f"`{finding.file}:{finding.line_start}`"
    if finding.line_end != finding.line_start:
        location = f"`{finding.file}:{finding.line_start}-{finding.line_end}`"

    lines = [
        f"- **{finding.severity.upper()} · {finding.category}** — {location}",
        f"  {finding.message}",
    ]
    if finding.suggested_fix:
        lines.append(f"  Suggested fix: {finding.suggested_fix}")
    return lines


async def review_pull_request(
    *, delivery_id: str, repository: str, pr_number: int, head_sha: str, installation_id: int
) -> None:
    """Fetch PR context, request a Gemini review, and publish one summary comment."""
    logger.info(
        "Starting PR review delivery_id=%s repository=%s pr_number=%s head_sha=%s",
        delivery_id,
        repository,
        pr_number,
        head_sha,
    )

    try:
        app_id, private_key_path = github_app_credentials()
        github = GitHubAppClient(app_id=app_id, private_key_path=private_key_path)
        installation_token = await github.installation_token(installation_id)
        diff = await github.pull_request_diff(
            repository=repository,
            pr_number=pr_number,
            installation_token=installation_token,
        )
        title, description = await github.pull_request_details(
            repository=repository,
            pr_number=pr_number,
            installation_token=installation_token,
        )
    except Exception:
        logger.exception(
            "PR review failed delivery_id=%s repository=%s pr_number=%s",
            delivery_id,
            repository,
            pr_number,
        )
        _release_failed_review(
            repository=repository, pr_number=pr_number, head_sha=head_sha
        )
        return

    logger.info(
        "Fetched PR diff delivery_id=%s repository=%s pr_number=%s head_sha=%s "
        "diff_characters=%s",
        delivery_id,
        repository,
        pr_number,
        head_sha,
        len(diff),
    )

    try:
        contexts = await RetrievalService().build_contexts(
            repository=repository,
            head_sha=head_sha,
            diff=diff,
        )
        logger.info(
            "Retrieved specialist context delivery_id=%s repository=%s pr_number=%s "
            "categories=%s",
            delivery_id,
            repository,
            pr_number,
            ",".join(sorted(contexts)),
        )

        specialist_run = await run_specialists(
            title=title,
            description=description,
            diff=diff,
            contexts=contexts,
        )
        logger.info(
            "Completed parallel specialist review delivery_id=%s repository=%s "
            "pr_number=%s successful=%s failed=%s",
            delivery_id,
            repository,
            pr_number,
            len(specialist_run.results),
            len(specialist_run.failures),
        )

        aggregated_review = aggregate_specialist_results(specialist_run)
        logger.info(
            "Aggregated specialist findings delivery_id=%s repository=%s pr_number=%s "
            "findings=%s",
            delivery_id,
            repository,
            pr_number,
            len(aggregated_review.findings),
        )

        comment = format_aggregated_review_comment(
            aggregated_review, was_truncated=len(diff) > MAX_DIFF_CHARACTERS
        )
        await github.create_pull_request_comment(
            repository=repository,
            pr_number=pr_number,
            body=comment,
            installation_token=installation_token,
        )
    except Exception:
        logger.exception(
            "PR analysis or posting failed delivery_id=%s repository=%s pr_number=%s",
            delivery_id,
            repository,
            pr_number,
        )
        _release_failed_review(
            repository=repository, pr_number=pr_number, head_sha=head_sha
        )
        return

    logger.info(
        "Posted Perchly specialist review delivery_id=%s repository=%s pr_number=%s "
        "findings=%s unavailable_specialists=%s",
        delivery_id,
        repository,
        pr_number,
        len(aggregated_review.findings),
        len(aggregated_review.failures),
    )
