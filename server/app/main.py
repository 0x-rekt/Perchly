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


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await initialize_temporal_client()
    except Exception:
        # Keep health/webhook validation available while Temporal is starting
        # or temporarily unavailable. The webhook returns 503 when it cannot
        # enqueue a review, and the client will retry initialization there.
        logger.warning("Temporal unavailable during startup; review enqueueing is disabled", exc_info=True)
    try:
        await asyncio.to_thread(telemetry.initialize_schema)
    except Exception:
        logger.warning("Telemetry schema initialisation failed; spans will not be persisted", exc_info=True)
    try:
        yield
    finally:
        await close_temporal_client()


app = FastAPI(title="perchly PR Review Agent", lifespan=lifespan)
app.include_router(github_webhook_router)
app.include_router(observability_router)
app.include_router(reviews_router)


@app.get("/")
def health_check() -> dict[str, str]:
    return {"message": "Everything ok"}
