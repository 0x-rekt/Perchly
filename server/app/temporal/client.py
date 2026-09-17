import asyncio
import inspect
import os

from temporalio.client import Client

from app.temporal.workflows import ReviewWorkflow, ReviewWorkflowInput

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
        id=f"perchly-review-{input.repository}-{input.pr_number}-{input.head_sha}",
        task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "perchly-reviews"),
    )
    return handle.id