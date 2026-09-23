import asyncio

import app.agents.base as base
from app.agents import SPECIALIST_AGENTS
from app.agents.docs import DOCS_AGENT
from app.agents.security import SECURITY_AGENT


def test_specialist_definitions_cover_the_four_required_categories() -> None:
    assert {agent.category for agent in SPECIALIST_AGENTS} == {
        "security",
        "quality",
        "test_coverage",
        "docs",
    }


def test_specialist_instructions_enforce_category_isolation() -> None:
    for agent in SPECIALIST_AGENTS:
        instructions = agent.instructions
        assert f"`{agent.category}`" in instructions
        assert "strictly limited" in instructions


def test_docs_specialist_requires_docs_for_undocumented_public_changes() -> None:
    instructions = DOCS_AGENT.instructions
    assert "public HTTP route" in instructions
    assert "environment variable" in instructions
    assert "not included in the diff" in instructions


def test_specialist_prompt_includes_historical_outcomes_as_calibration(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_review_diff(**kwargs):
        captured["instructions"] = kwargs["specialist_instructions"]
        from app.schemas.findings import ReviewResult

        return ReviewResult()

    monkeypatch.setattr(base, "review_diff", fake_review_diff)
    asyncio.run(
        SECURITY_AGENT.review(
            title="Add auth",
            description="",
            diff="+token = request.args['token']",
            historical_outcomes=[
                {
                    "outcome": "rejected",
                    "finding": {
                        "category": "security",
                        "severity": "warning",
                        "file": "src/auth.py",
                        "line_start": 4,
                        "message": "Previous false positive",
                    },
                }
            ],
        )
    )

    assert "Historical review outcomes" in captured["instructions"]
    assert "outcome: rejected" in captured["instructions"]
    assert "do not copy a finding" in captured["instructions"]
