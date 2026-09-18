import pytest

from app.schemas.findings import Finding
from app.services.routing import AUTO_POST, NEEDS_APPROVAL, route_review


def finding(*, category="quality", severity="warning", confidence=0.9) -> Finding:
    return Finding(
        category=category,
        file="src/example.py",
        line_start=1,
        line_end=1,
        severity=severity,
        confidence=confidence,
        message="Actionable finding",
    )


def test_high_confidence_non_security_finding_auto_posts() -> None:
    decision = route_review(findings=[finding()], failures={})
    assert decision.mode == AUTO_POST
    assert decision.reason == "all_findings_meet_policy"


def test_security_warning_requires_higher_threshold() -> None:
    assert route_review(
        findings=[finding(category="security", confidence=0.94)], failures={}
    ).mode == NEEDS_APPROVAL
    assert route_review(
        findings=[finding(category="security", confidence=0.95)], failures={}
    ).mode == AUTO_POST


def test_critical_security_always_requires_approval() -> None:
    assert route_review(
        findings=[finding(category="security", severity="critical", confidence=1.0)],
        failures={},
    ).mode == NEEDS_APPROVAL


@pytest.mark.parametrize("category", ["quality", "test_coverage", "docs"])
def test_below_default_threshold_requires_approval(category: str) -> None:
    assert route_review(
        findings=[finding(category=category, confidence=0.89)], failures={}
    ).mode == NEEDS_APPROVAL


def test_any_specialist_failure_requires_approval() -> None:
    decision = route_review(findings=[], failures={"security": "timeout"})
    assert decision.mode == NEEDS_APPROVAL
    assert decision.reason == "specialist_failure"


def test_empty_successful_review_can_auto_post() -> None:
    assert route_review(findings=[], failures={}).mode == AUTO_POST


def test_thresholds_are_overridable() -> None:
    assert route_review(
        findings=[finding(confidence=0.75)],
        failures={},
        auto_post_threshold=0.8,
        security_auto_post_threshold=0.9,
    ).mode == NEEDS_APPROVAL
    assert route_review(
        findings=[finding(confidence=0.85)],
        failures={},
        auto_post_threshold=0.8,
        security_auto_post_threshold=0.9,
    ).mode == AUTO_POST


def test_unresolved_errors_require_approval() -> None:
    decision = route_review(
        findings=[finding(confidence=1.0)],
        failures={},
        unresolved_errors=["aggregation incomplete"],
    )
    assert decision.mode == NEEDS_APPROVAL
    assert decision.reason == "unresolved_review_error"


def test_excessive_finding_count_requires_approval() -> None:
    findings = [finding(confidence=1.0) for _ in range(3)]
    decision = route_review(
        findings=findings,
        failures={},
        max_auto_post_findings=2,
    )
    assert decision.mode == NEEDS_APPROVAL
    assert decision.reason == "finding_count_exceeds_auto_post_limit"
