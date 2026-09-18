from enum import StrEnum
from dataclasses import dataclass
from typing import Final, Literal

from app.core.config import (
    AUTO_POST_THRESHOLD,
    MAX_AUTO_POST_FINDINGS,
    SECURITY_AUTO_POST_THRESHOLD,
)
from app.schemas.findings import Finding


RoutingMode = Literal["auto_post", "needs_approval"]


@dataclass(frozen=True)
class RoutingDecision:
    mode: RoutingMode
    reason: str


AUTO_POST: Final[RoutingMode] = "auto_post"
NEEDS_APPROVAL: Final[RoutingMode] = "needs_approval"


def route_review(
    *,
    findings: list[Finding] | tuple[Finding, ...],
    failures: dict[str, str],
    unresolved_errors: list[str] | tuple[str, ...] = (),
    auto_post_threshold: float = AUTO_POST_THRESHOLD,
    security_auto_post_threshold: float = SECURITY_AUTO_POST_THRESHOLD,
    max_auto_post_findings: int = MAX_AUTO_POST_FINDINGS,
) -> RoutingDecision:
    """Choose direct posting only when the complete review is safe to publish."""
    if failures:
        return RoutingDecision(NEEDS_APPROVAL, "specialist_failure")
    if unresolved_errors:
        return RoutingDecision(NEEDS_APPROVAL, "unresolved_review_error")
    if len(findings) > max_auto_post_findings:
        return RoutingDecision(NEEDS_APPROVAL, "finding_count_exceeds_auto_post_limit")

    for finding in findings:
        if finding.category == "security" and finding.severity == "critical":
            return RoutingDecision(NEEDS_APPROVAL, "critical_security_finding")
        threshold = (
            security_auto_post_threshold
            if finding.category == "security"
            else auto_post_threshold
        )
        if finding.confidence < threshold:
            return RoutingDecision(NEEDS_APPROVAL, "finding_below_confidence_threshold")

    return RoutingDecision(AUTO_POST, "all_findings_meet_policy")