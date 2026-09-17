import asyncio
from dataclasses import asdict, dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        aggregate_review,
        fetch_review_context,
        post_review,
        release_review_claim,
        retrieve_repository_context,
        run_specialist,
    )


@dataclass(frozen=True)
class ReviewWorkflowInput:
    delivery_id: str
    repository: str
    pr_number: int
    head_sha: str
    installation_id: int


@dataclass(frozen=True)
class ReviewWorkflowResult:
    delivery_id: str
    repository: str
    pr_number: int
    findings_count: int
    posted: bool


_RETRY_POLICY = RetryPolicy(maximum_attempts=3)
_SPECIALIST_RETRY_POLICY = RetryPolicy(maximum_attempts=2)
_ACTIVITY_TIMEOUT = timedelta(minutes=3)
_SPECIALIST_TIMEOUT = timedelta(minutes=2)
_SPECIALIST_CATEGORIES = ("security", "quality", "test_coverage", "docs")


@workflow.defn
class ReviewWorkflow:
    """Durable orchestration for one GitHub pull-request review."""

    @workflow.run
    async def run(self, input: ReviewWorkflowInput) -> ReviewWorkflowResult:
        try:
            fetched = await workflow.execute_activity(
                fetch_review_context,
                asdict(input),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            retrieved = await workflow.execute_activity(
                retrieve_repository_context,
                fetched,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            specialist_runs = await asyncio.gather(
                *(
                    workflow.execute_activity(
                        run_specialist,
                        {"retrieved": retrieved, "category": category},
                        start_to_close_timeout=_SPECIALIST_TIMEOUT,
                        retry_policy=_SPECIALIST_RETRY_POLICY,
                    )
                    for category in _SPECIALIST_CATEGORIES
                ),
                return_exceptions=True,
            )
            specialist_results: dict[str, object] = {}
            specialist_failures: dict[str, str] = {}
            for category, result in zip(
                _SPECIALIST_CATEGORIES, specialist_runs, strict=True
            ):
                if isinstance(result, BaseException):
                    specialist_failures[category] = f"{type(result).__name__}: {result}"
                else:
                    specialist_results[category] = result["review"]

            aggregated = await workflow.execute_activity(
                aggregate_review,
                {
                    "specialist_results": specialist_results,
                    "specialist_failures": specialist_failures,
                },
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            posted = await workflow.execute_activity(
                post_review,
                {
                    "review": aggregated,
                    "fetched": fetched,
                    "diff_characters": len(fetched["diff"]),
                },
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            return ReviewWorkflowResult(
                delivery_id=input.delivery_id,
                repository=input.repository,
                pr_number=input.pr_number,
                findings_count=len(aggregated["findings"]),
                posted=posted,
            )
        except Exception:
            await workflow.execute_activity(
                release_review_claim,
                asdict(input),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            raise
