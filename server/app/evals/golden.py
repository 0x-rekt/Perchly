import json
from pathlib import Path
from typing import Any

from app.schemas.findings import Finding

GOLDEN_FIXTURE_DIRECTORY = Path(__file__).with_name("fixtures")


def load_golden_cases() -> list[dict[str, Any]]:
    """Load the small, versioned Phase 0 golden PR dataset."""
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(GOLDEN_FIXTURE_DIRECTORY.glob("*.json"))]


def finding_matches_expectation(finding: Finding, expected: dict[str, Any]) -> bool:
    """Match stable properties; allow a small line-number variance in model output."""
    if finding.category != expected["category"]:
        return False
    if finding.severity != expected["severity"]:
        return False
    if finding.file != expected["file"]:
        return False
    expected_line = expected.get("line_start")
    return expected_line is None or abs(finding.line_start - expected_line) <= 2
