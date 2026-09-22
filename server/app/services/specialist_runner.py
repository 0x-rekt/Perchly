import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from app.agents import SPECIALIST_AGENTS
from app.schemas.findings import FindingCategory, ReviewResult
from app.services.telemetry import ReviewContext

logger = logging.getLogger(__name__)


class ReviewSpecialist(Protocol):
    name: str
    category: FindingCategory

    async def review(
        self,
        *,
        title: str,
        description: str | None,
        diff: str,
        retrieved_context: str = "",
        telemetry_ctx: ReviewContext | None = None,
    ) -> ReviewResult: ...


@dataclass
class SpecialistRunResult:
    """Successful category results plus isolated specialist failures."""

    results: dict[FindingCategory, ReviewResult] = field(default_factory=dict)
    failures: dict[FindingCategory, str] = field(default_factory=dict)

    @property
    def findings_count(self) -> int:
        return sum(len(review.findings) for review in self.results.values())


async def run_specialists(
    *,
    title: str,
    description: str | None,
    diff: str,
    contexts: dict[FindingCategory, str] | None = None,
    specialists: Sequence[ReviewSpecialist] = SPECIALIST_AGENTS,
    telemetry_ctx: ReviewContext | None = None,
) -> SpecialistRunResult:
    """Run specialists concurrently; one agent failure never discards other results."""
    _validate_specialists(specialists)
    contexts = contexts or {}
    calls: list[object] = []
    for specialist in specialists:
        kwargs: dict[str, object] = {
            "title": title,
            "description": description,
            "diff": diff,
            "retrieved_context": contexts.get(specialist.category, ""),
        }
        if telemetry_ctx is not None:
            kwargs["telemetry_ctx"] = telemetry_ctx
        calls.append(specialist.review(**kwargs))
    responses = await asyncio.gather(*calls, return_exceptions=True)

    run = SpecialistRunResult()
    for specialist, response in zip(specialists, responses, strict=True):
        if isinstance(response, BaseException):
            failure = f"{type(response).__name__}: {response}"
            run.failures[specialist.category] = failure
            logger.warning(
                "Specialist failed name=%s category=%s error=%s",
                specialist.name,
                specialist.category,
                failure,
            )
            continue
        run.results[specialist.category] = response

    return run


def _validate_specialists(specialists: Sequence[ReviewSpecialist]) -> None:
    categories = [specialist.category for specialist in specialists]
    if len(categories) != len(set(categories)):
        raise ValueError("Specialist categories must be unique")
