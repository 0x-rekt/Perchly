import asyncio
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Literal

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        aggregate_review,
        fetch_review_context,
        post_review,
        persist_automatic_decision,
        persist_reviewer_decision,
        validate_edited_review,
        release_review_claim,
        retrieve_repository_context,
        route_aggregated_review,
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
class ReviewDecisionInput:
    decision: Literal["approve", "reject", "edit"]
    reviewer: str
    edited_review: dict[str, Any] | None = None
    comment: str | None = None


@dataclass(frozen=True)
class ReviewWorkflowResult:
    delivery_id: str
    repository: str
    pr_number: int
    findings_count: int
    posted: bool
    route: str


_RETRY_POLICY = RetryPolicy(maximum_attempts=3)
_SPECIALIST_RETRY_POLICY = RetryPolicy(maximum_attempts=2)
_ACTIVITY_TIMEOUT = timedelta(minutes=3)
_SPECIALIST_TIMEOUT = timedelta(minutes=2)
_SPECIALIST_CATEGORIES = ("security", "quality", "test_coverage", "docs")


@workflow.defn
class ReviewWorkflow:
    """Durable orchestration for one GitHub pull-request review."""

    decision: ReviewDecisionInput | None = None
    state: str = "starting"

    @workflow.query
    def status(self) -> dict[str, str | None]:
        return {
            "state": self.state,
            "decision": self.decision.decision if self.decision else None,
        }

    @workflow.signal
    async def approve_review(self, decision: ReviewDecisionInput) -> None:
        if decision.decision != "approve":
            raise ValueError("approve_review requires decision='approve'")
        if self.decision is None:
            self.decision = decision

    @workflow.signal
    async def reject_review(self, decision: ReviewDecisionInput) -> None:
        if decision.decision != "reject":
            raise ValueError("reject_review requires decision='reject'")
        if self.decision is None:
            self.decision = decision

    @workflow.signal
    async def edit_review(
        self, decision: ReviewDecisionInput
    ) -> None:
        if decision.decision != "edit" or decision.edited_review is None:
            raise ValueError("edit_review requires decision='edit' and edited_review")
        if self.decision is None:
            self.decision = decision

    @workflow.run
    async def run(self, input: ReviewWorkflowInput) -> ReviewWorkflowResult:
        self.decision = None
        self.state = "running"
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
            routing = await workflow.execute_activity(
                route_aggregated_review,
                {"review": aggregated, "fetched": fetched},
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            if routing["mode"] == "needs_approval":
                self.state = "awaiting_approval"
                await workflow.wait_condition(lambda: self.decision is not None)
                self.state = "processing_decision"
                decision = self.decision
                if decision.decision == "edit":
                    edited_review = await workflow.execute_activity(
                        validate_edited_review,
                        decision.edited_review,
                        start_to_close_timeout=_ACTIVITY_TIMEOUT,
                        retry_policy=_RETRY_POLICY,
                    )
                    decision = ReviewDecisionInput(
                        decision="edit",
                        reviewer=decision.reviewer,
                        edited_review=edited_review,
                        comment=decision.comment,
                    )
                await workflow.execute_activity(
                    persist_reviewer_decision,
                    {
                        "queue_item_id": routing["queue_item_id"],
                        "decision": asdict(decision),
                    },
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                    retry_policy=_RETRY_POLICY,
                )
                if decision.decision == "reject":
                    self.state = "completed"
                    return ReviewWorkflowResult(
                        delivery_id=input.delivery_id,
                        repository=input.repository,
                        pr_number=input.pr_number,
                        findings_count=len(aggregated["findings"]),
                        posted=False,
                        route="needs_approval",
                    )
                review_to_post = decision.edited_review or aggregated
                posted = await workflow.execute_activity(
                    post_review,
                    {
                        "review": review_to_post,
                        "fetched": fetched,
                        "diff_characters": len(fetched["diff"]),
                    },
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                    retry_policy=_RETRY_POLICY,
                )
                self.state = "completed"
                return ReviewWorkflowResult(
                    delivery_id=input.delivery_id,
                    repository=input.repository,
                    pr_number=input.pr_number,
                    findings_count=len(aggregated["findings"]),
                    posted=posted,
                    route="needs_approval",
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
            await workflow.execute_activity(
                persist_automatic_decision,
                {
                    "review": aggregated,
                    "fetched": fetched,
                    "reason": routing["reason"],
                },
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            self.state = "completed"
            return ReviewWorkflowResult(
                delivery_id=input.delivery_id,
                repository=input.repository,
                pr_number=input.pr_number,
                findings_count=len(aggregated["findings"]),
                posted=posted,
                route="auto_post",
            )
        except Exception:
            await workflow.execute_activity(
                release_review_claim,
                asdict(input),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            raise
