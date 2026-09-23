import asyncio
import json
from dataclasses import asdict, dataclass

from app.evals.golden import finding_matches_expectation, load_golden_cases
from app.agents import SPECIALIST_AGENTS
from app.schemas.findings import Finding
from app.services.gemini import review_diff


@dataclass
class CaseResult:
    name: str
    expected_count: int
    matched_count: int
    unexpected_count: int
    findings: list[dict[str, object]]


def score_case(
    *, name: str, expected: list[dict[str, object]], findings: list[Finding]
) -> CaseResult:
    unmatched_expected = expected.copy()
    unexpected: list[Finding] = []

    for finding in findings:
        match_index = next(
            (
                index
                for index, expectation in enumerate(unmatched_expected)
                if finding_matches_expectation(finding, expectation)
            ),
            None,
        )
        if match_index is None:
            unexpected.append(finding)
        else:
            unmatched_expected.pop(match_index)

    return CaseResult(
        name=name,
        expected_count=len(expected),
        matched_count=len(expected) - len(unmatched_expected),
        unexpected_count=len(unexpected),
        findings=[finding.model_dump() for finding in findings],
    )


async def run_golden_evaluation() -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in load_golden_cases():
        category = case.get("specialist_category")
        if category:
            specialist = next(agent for agent in SPECIALIST_AGENTS if agent.category == category)
            review = await specialist.review(
                title=case["title"],
                description=case["description"],
                diff=case["diff"],
                historical_outcomes=case.get("historical_outcomes", []),
            )
        else:
            review = await review_diff(
                title=case["title"], description=case["description"], diff=case["diff"]
            )
        results.append(
            score_case(
                name=case["name"],
                expected=case["expected_findings"],
                findings=review.findings,
            )
        )
    return results


def passed_gate(results: list[CaseResult]) -> bool:
    """Phase 0 gate: cover every expected issue and add no unexpected findings."""
    return all(
        result.matched_count == result.expected_count and result.unexpected_count == 0
        for result in results
    )


async def main() -> int:
    results = await run_golden_evaluation()
    report = {"passed": passed_gate(results), "cases": [asdict(result) for result in results]}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
