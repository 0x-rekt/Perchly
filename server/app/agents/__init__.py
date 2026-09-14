"""Perchly's narrowly scoped pull-request review specialists."""

from app.agents.docs import DOCS_AGENT
from app.agents.quality import QUALITY_AGENT
from app.agents.security import SECURITY_AGENT
from app.agents.test_coverage import TEST_COVERAGE_AGENT

SPECIALIST_AGENTS = (
    SECURITY_AGENT,
    QUALITY_AGENT,
    TEST_COVERAGE_AGENT,
    DOCS_AGENT,
)

__all__ = [
    "DOCS_AGENT",
    "QUALITY_AGENT",
    "SECURITY_AGENT",
    "SPECIALIST_AGENTS",
    "TEST_COVERAGE_AGENT",
]
