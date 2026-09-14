import asyncio
from dataclasses import dataclass

from app.schemas.findings import ReviewResult
from app.services.specialist_runner import run_specialists


@dataclass
class FakeSpecialist:
    name: str
    category: str
    failure: Exception | None = None
    expected_context: str = ""

    async def review(
        self, *, title: str, description: str | None, diff: str, retrieved_context: str = ""
    ) -> ReviewResult:
        assert title == "Test PR"
        assert diff == "diff"
        assert retrieved_context == self.expected_context
        if self.failure:
            raise self.failure
        await asyncio.sleep(0)
        return ReviewResult()


def test_runner_keeps_successful_results_when_one_specialist_fails() -> None:
    specialists = (
        FakeSpecialist(name="security", category="security", expected_context="auth context"),
        FakeSpecialist(name="quality", category="quality", failure=TimeoutError("timed out")),
        FakeSpecialist(name="tests", category="test_coverage"),
    )

    result = asyncio.run(
        run_specialists(
            title="Test PR",
            description=None,
            diff="diff",
            contexts={"security": "auth context"},
            specialists=specialists,
        )
    )

    assert set(result.results) == {"security", "test_coverage"}
    assert "quality" in result.failures
    assert "TimeoutError" in result.failures["quality"]


def test_runner_rejects_duplicate_categories() -> None:
    specialists = (
        FakeSpecialist(name="security-one", category="security"),
        FakeSpecialist(name="security-two", category="security"),
    )

    try:
        asyncio.run(run_specialists(title="Test PR", description=None, diff="diff", specialists=specialists))
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("Expected duplicate categories to be rejected")
