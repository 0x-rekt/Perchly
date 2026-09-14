import pytest
from pydantic import ValidationError

from app.schemas.findings import Finding, ReviewResult
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
