from app.agents.base import SpecialistAgent

DOCS_AGENT = SpecialistAgent(
    name="documentation",
    category="docs",
    focus=(
        "missing or outdated docstrings, README or changelog drift, and undocumented "
        "public API or configuration changes. When a diff adds or changes a public HTTP "
        "route, environment variable, configuration option, or externally consumed API "
        "and does not include a corresponding documentation update, report one `docs` "
        "finding on the changed public interface. Do this even when the existing README "
        "is not included in the diff"
    ),
)
