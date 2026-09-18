import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from app.temporal import activities
from app.temporal.workflows import ReviewWorkflow


async def run_worker() -> None:
    """Run the Temporal worker that hosts review workflows and activities."""
    client = await Client.connect(os.getenv("TEMPORAL_ADDRESS", "localhost:7233"))
    async with Worker(
        client,
        task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "perchly-reviews"),
        workflows=[ReviewWorkflow],
        activities=[
            activities.fetch_review_context,
            activities.retrieve_repository_context,
            activities.run_specialist,
            activities.aggregate_review,
            activities.route_aggregated_review,
            activities.persist_automatic_decision,
            activities.persist_reviewer_decision,
            activities.validate_edited_review,
            activities.post_review,
            activities.release_review_claim,
        ],
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(run_worker())