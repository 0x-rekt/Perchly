from app.evals.golden import load_golden_cases
from app.evals.run import passed_gate, score_case
from app.schemas.findings import Finding


def test_golden_dataset_has_security_and_safe_cases() -> None:
    cases = load_golden_cases()
    assert len(cases) >= 3
    assert any(case["expected_findings"] for case in cases)
    assert any(not case["expected_findings"] for case in cases)
    assert all(case["diff"] for case in cases)
    learning_cases = [case for case in cases if case.get("historical_outcomes")]
    assert learning_cases
    assert all(case.get("specialist_category") for case in learning_cases)


def test_gate_requires_expected_coverage_and_no_unexpected_findings() -> None:
    expected = [{"category": "security", "severity": "critical", "file": "src/a.py", "line_start": 2}]
    matching = Finding(category="security", severity="critical", file="src/a.py", line_start=2, line_end=2, confidence=0.9, message="Secret found")
    result = score_case(name="secret", expected=expected, findings=[matching])
    assert passed_gate([result])

    unexpected = Finding(category="docs", severity="info", file="README.md", line_start=1, line_end=1, confidence=0.9, message="Unexpected")
    failed = score_case(name="secret", expected=expected, findings=[matching, unexpected])
    assert not passed_gate([failed])
