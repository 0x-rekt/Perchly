from app.agents.base import SpecialistAgent

QUALITY_AGENT = SpecialistAgent(
    name="code quality",
    category="quality",
    focus=(
        "new complexity, duplication, dead code, unclear naming, error-handling gaps, "
        "resource leaks, and maintainability anti-patterns introduced by the change"
    ),
)
