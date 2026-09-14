from app.agents import SPECIALIST_AGENTS
from app.agents.docs import DOCS_AGENT


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
