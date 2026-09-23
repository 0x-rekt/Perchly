import pytest
from pydantic import ValidationError

from app.schemas.findings import Finding, ReviewResult, assign_finding_ids, stable_finding_id
from app.workers.review import format_review_comment


def test_review_result_rejects_invalid_finding() -> None:
    with pytest.raises(ValidationError):
        ReviewResult.model_validate({"findings": [{"category": "unknown", "line_start": 0}]})


def test_review_comment_formats_valid_finding() -> None:
    review = ReviewResult(findings=[Finding(category="security", file="src/client.py", line_start=5, line_end=5, severity="critical", confidence=0.98, message="A secret is committed to source control.", suggested_fix="Read it from an environment variable.")])
    comment = format_review_comment(review, was_truncated=False)
    assert "## Perchly review" in comment
    assert "CRITICAL" in comment
    assert "`src/client.py:5`" in comment


def test_finding_id_is_stable_for_same_review_context() -> None:
    finding = Finding(
        category="security",
        file="src/client.py",
        line_start=5,
        line_end=5,
        severity="critical",
        confidence=0.98,
        message="A secret is committed to source control.",
    )

    first = stable_finding_id(
        repository="acme/repo", pr_number=7, head_sha="abc123", finding=finding
    )
    second = assign_finding_ids(
        [finding], repository="acme/repo", pr_number=7, head_sha="abc123"
    )[0].finding_id

    assert first == second
    assert len(first) == 64


def test_finding_id_changes_for_a_different_commit() -> None:
    finding = Finding(
        category="quality",
        file="src/app.py",
        line_start=10,
        line_end=12,
        severity="warning",
        confidence=0.8,
        message="This branch is unnecessarily nested.",
    )

    first = assign_finding_ids(
        [finding], repository="acme/repo", pr_number=7, head_sha="abc123"
    )[0].finding_id
    second = assign_finding_ids(
        [finding], repository="acme/repo", pr_number=7, head_sha="def456"
    )[0].finding_id

    assert first != second
