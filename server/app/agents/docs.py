from app.agents.base import SpecialistAgent

DOCS_AGENT = SpecialistAgent(
    name="documentation",
    category="docs",
    focus=(
        "missing or outdated docstrings, README or changelog drift, and undocumented "
        "public API or configuration changes"
    ),
)
