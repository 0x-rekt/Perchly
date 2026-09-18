import asyncio
import inspect
import os
from typing import Any

from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDReusePolicy

from app.temporal.workflows import (
    ReviewDecisionInput,
    ReviewWorkflow,
    ReviewWorkflowInput,
)

_client: Client | None = None
_client_lock = asyncio.Lock()


async def initialize_temporal_client() -> Client:
    """Initialize the process-shared Temporal client during application startup."""
    global _client
    async with _client_lock:
        if _client is None:
            _client = await Client.connect(os.getenv("TEMPORAL_ADDRESS", "localhost:7233"))
        return _client


async def temporal_client() -> Client:
    """Return the shared Temporal client, initializing it for non-server callers."""
    return await initialize_temporal_client()


async def close_temporal_client() -> None:
    """Close the process-shared Temporal client during application shutdown."""
    global _client
    async with _client_lock:
        if _client is not None:
            close = getattr(_client.service_client, "close", None)
            if close is not None:
                result = close()
                if inspect.isawaitable(result):
                    await result
            _client = None


async def start_review_workflow(input: ReviewWorkflowInput) -> str:
    """Start one durable review workflow and return its workflow ID."""
    client = await temporal_client()
    handle = await client.start_workflow(
        ReviewWorkflow.run,
        input,
        id=review_workflow_id(input),
        task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "perchly-reviews"),
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )
    return handle.id


def review_workflow_id(input: ReviewWorkflowInput) -> str:
    """Build the deterministic workflow ID used by starts and lookups."""
    return f"perchly-review-{input.repository}-{input.pr_number}-{input.head_sha}"


async def find_review_workflow(input: ReviewWorkflowInput) -> WorkflowHandle:
    """Return a handle for an existing review workflow without starting it."""
    client = await temporal_client()
    return client.get_workflow_handle(review_workflow_id(input))


async def find_review_workflow_by_id(workflow_id: str) -> WorkflowHandle:
    client = await temporal_client()
    return client.get_workflow_handle(workflow_id)


async def send_signal_by_workflow_id(
    workflow_id: str, signal_name: str, decision: ReviewDecisionInput
) -> None:
    handle = await find_review_workflow_by_id(workflow_id)
    signal = getattr(ReviewWorkflow, signal_name)
    await handle.signal(signal, decision)


async def send_approval_signal(
    input: ReviewWorkflowInput, *, reviewer: str, comment: str | None = None
) -> None:
    handle = await find_review_workflow(input)
    await handle.signal(
        ReviewWorkflow.approve_review,
        ReviewDecisionInput(decision="approve", reviewer=reviewer, comment=comment),
    )


async def send_rejection_signal(
    input: ReviewWorkflowInput, *, reviewer: str, comment: str | None = None
) -> None:
    handle = await find_review_workflow(input)
    await handle.signal(
        ReviewWorkflow.reject_review,
        ReviewDecisionInput(decision="reject", reviewer=reviewer, comment=comment),
    )


async def send_edited_review_signal(
    input: ReviewWorkflowInput,
    *,
    reviewer: str,
    edited_review: dict[str, Any],
    comment: str | None = None,
) -> None:
    handle = await find_review_workflow(input)
    await handle.signal(
        ReviewWorkflow.edit_review,
        ReviewDecisionInput(
            decision="edit",
            reviewer=reviewer,
            edited_review=edited_review,
            comment=comment,
        ),
    )


async def query_review_status(input: ReviewWorkflowInput) -> dict[str, str | None]:
    """Query the current durable workflow state."""
    handle = await find_review_workflow(input)
    return await handle.query(ReviewWorkflow.status)
