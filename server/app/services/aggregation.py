from collections import Counter
from dataclasses import dataclass

from app.schemas.findings import Finding, FindingCategory
from app.services.specialist_runner import SpecialistRunResult

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class AggregatedReview:
    """Deduplicated findings and any isolated specialist failures."""

    findings: tuple[Finding, ...]
    failures: dict[FindingCategory, str]

    @property
    def category_counts(self) -> dict[FindingCategory, int]:
        return dict(Counter(finding.category for finding in self.findings))


def aggregate_specialist_results(run: SpecialistRunResult) -> AggregatedReview:
    """Merge successful specialist findings without allowing a failed agent to block review."""
    findings = [
        finding
        for review in run.results.values()
        for finding in review.findings
    ]
    return AggregatedReview(
        findings=tuple(_deduplicate_and_sort(findings)),
        failures=run.failures.copy(),
    )


def _deduplicate_and_sort(findings: list[Finding]) -> list[Finding]:
    """Keep the strongest finding when specialists flag overlapping changed lines."""
    selected: list[Finding] = []
    for finding in sorted(findings, key=_priority_key):
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(selected)
                if _overlaps(existing, finding)
            ),
            None,
        )
        if duplicate_index is None:
            selected.append(finding)
            continue

        if _priority_key(finding) < _priority_key(selected[duplicate_index]):
            selected[duplicate_index] = finding

    return sorted(selected, key=_display_key)


def _overlaps(first: Finding, second: Finding) -> bool:
    return (
        first.file == second.file
        and first.line_start <= second.line_end
        and second.line_start <= first.line_end
    )


def _priority_key(finding: Finding) -> tuple[int, float, str, int]:
    """Lower key is stronger: severity, then confidence, then stable location."""
    return (
        SEVERITY_RANK[finding.severity],
        -finding.confidence,
        finding.file,
        finding.line_start,
    )


def _display_key(finding: Finding) -> tuple[int, str, int, int]:
    return (
        SEVERITY_RANK[finding.severity],
        finding.file,
        finding.line_start,
        finding.line_end,
    )
