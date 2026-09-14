from app.schemas.findings import Finding, ReviewResult
from app.services.aggregation import aggregate_specialist_results
from app.services.specialist_runner import SpecialistRunResult
from app.workers.review import format_aggregated_review_comment


def finding(*, category: str, severity: str, confidence: float, line_start: int, line_end: int | None = None) -> Finding:
    return Finding(
        category=category,
        file="src/client.py",
        line_start=line_start,
        line_end=line_end or line_start,
        severity=severity,
        confidence=confidence,
        message=f"{category} finding",
    )


def test_aggregation_keeps_strongest_overlapping_finding() -> None:
    run = SpecialistRunResult(
        results={
            "security": ReviewResult(findings=[finding(category="security", severity="critical", confidence=0.8, line_start=8)]),
            "quality": ReviewResult(findings=[finding(category="quality", severity="warning", confidence=0.99, line_start=8)]),
        }
    )

    aggregated = aggregate_specialist_results(run)

    assert len(aggregated.findings) == 1
    assert aggregated.findings[0].category == "security"
    assert aggregated.category_counts == {"security": 1}


def test_aggregation_sorts_and_preserves_partial_failures() -> None:
    run = SpecialistRunResult(
        results={
            "docs": ReviewResult(findings=[finding(category="docs", severity="info", confidence=0.8, line_start=20)]),
            "tests": ReviewResult(findings=[finding(category="test_coverage", severity="warning", confidence=0.8, line_start=4)]),
        },
        failures={"security": "TimeoutError: timed out"},
    )

    aggregated = aggregate_specialist_results(run)

    assert [item.severity for item in aggregated.findings] == ["warning", "info"]
    assert aggregated.failures == {"security": "TimeoutError: timed out"}


def test_aggregation_keeps_distinct_non_overlapping_findings() -> None:
    run = SpecialistRunResult(
        results={
            "security": ReviewResult(findings=[finding(category="security", severity="critical", confidence=0.9, line_start=2)]),
            "quality": ReviewResult(findings=[finding(category="quality", severity="warning", confidence=0.9, line_start=9)]),
        }
    )

    assert len(aggregate_specialist_results(run).findings) == 2


def test_aggregated_comment_shows_category_counts_and_failures() -> None:
    aggregated = aggregate_specialist_results(
        SpecialistRunResult(
            results={
                "security": ReviewResult(
                    findings=[finding(category="security", severity="critical", confidence=0.9, line_start=2)]
                )
            },
            failures={"docs": "TimeoutError: timed out"},
        )
    )

    comment = format_aggregated_review_comment(aggregated, was_truncated=False)

    assert "1 security" in comment
    assert "Unavailable specialists: docs." in comment
