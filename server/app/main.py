import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.core.logging import configure_logging
from app.routers.github_webhooks import router as github_webhook_router
from app.routers.observability import router as observability_router
from app.routers.reviews import router as reviews_router
from app.services import telemetry
from app.temporal.client import close_temporal_client, initialize_temporal_client

configure_logging()
logger = logging.getLogger(__name__)


async def _aggregate_refresh_loop() -> None:
    """Keep the dashboard aggregate current without blocking the API loop."""
    while True:
        await asyncio.sleep(300)
        try:
            await asyncio.to_thread(telemetry.refresh_aggregates)
        except Exception:
            logger.warning("Telemetry aggregate refresh failed", exc_info=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    aggregate_task: asyncio.Task[None] | None = None
    try:
        await initialize_temporal_client()
    except Exception:
        # Keep health/webhook validation available while Temporal is starting
        # or temporarily unavailable. The webhook returns 503 when it cannot
        # enqueue a review, and the client will retry initialization there.
        logger.warning("Temporal unavailable during startup; review enqueueing is disabled", exc_info=True)
    try:
        await asyncio.to_thread(telemetry.initialize_schema)
        await asyncio.to_thread(telemetry.refresh_aggregates)
        aggregate_task = asyncio.create_task(_aggregate_refresh_loop())
    except Exception:
        logger.warning("Telemetry schema initialisation failed; spans will not be persisted", exc_info=True)
    try:
        yield
    finally:
        if aggregate_task is not None:
            aggregate_task.cancel()
            await asyncio.gather(aggregate_task, return_exceptions=True)
        await close_temporal_client()


app = FastAPI(title="perchly PR Review Agent", lifespan=lifespan)
app.include_router(github_webhook_router)
app.include_router(observability_router)
app.include_router(reviews_router)


@app.get("/")
def health_check() -> dict[str, str]:
    return {"message": "Everything ok"}
