from app.agents.base import SpecialistAgent

TEST_COVERAGE_AGENT = SpecialistAgent(
    name="test coverage",
    category="test_coverage",
    focus=(
        "new or changed behavior that lacks tests, including untested branches, error "
        "paths, boundary conditions, and missing regression coverage"
    ),
)
