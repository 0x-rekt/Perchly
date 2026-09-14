from app.evals.golden import load_golden_cases


def test_golden_dataset_has_security_and_safe_cases() -> None:
    cases = load_golden_cases()
    assert len(cases) >= 3
    assert any(case["expected_findings"] for case in cases)
    assert any(not case["expected_findings"] for case in cases)
    assert all(case["diff"] for case in cases)
