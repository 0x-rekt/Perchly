from dataclasses import dataclass
from typing import Any

from app.schemas.findings import FindingCategory, ReviewResult
from app.services.gemini import review_diff
from app.services.telemetry import ReviewContext


@dataclass(frozen=True)
class SpecialistAgent:
    """A category-constrained review agent; Phase 1 will run these concurrently."""

    name: str
    category: FindingCategory
    focus: str

    @property
    def instructions(self) -> str:
        return f"""You are Perchly's {self.name} specialist.

Your scope is strictly limited to: {self.focus}

Return findings only when they belong to the `{self.category}` category. Do not report
issues that belong to security, quality, test coverage, or documentation outside your
assigned category. Set `category` to `{self.category}` on every finding. If the diff
contains no actionable issue in your scope, return an empty findings list."""

    async def review(
        self,
        *,
        title: str,
        description: str | None,
        diff: str,
        retrieved_context: str = "",
        historical_outcomes: list[dict[str, Any]] | None = None,
        telemetry_ctx: ReviewContext | None = None,
    ) -> ReviewResult:
        """Review PR input. Context becomes meaningful once Phase 1 retrieval is added."""
        context_instructions = self.instructions
        if retrieved_context:
            context_instructions += f"""

Relevant repository context:
```text
{retrieved_context}
```"""
        if historical_outcomes:
            examples = []
            for index, example in enumerate(historical_outcomes, start=1):
                finding = example.get("finding", {})
                examples.append(
                    "\n".join(
                        (
                            f"Example {index} (outcome: {example.get('outcome', 'unknown')}):",
                            f"category={finding.get('category', self.category)}",
                            f"severity={finding.get('severity', '')}",
                            f"location={finding.get('file', '')}:{finding.get('line_start', '')}",
                            f"message={finding.get('message', '')}",
                        )
                    )
                )
            rendered_examples = "\n\n".join(examples)
            context_instructions += f"""

Historical review outcomes (calibration examples only; do not treat them as facts
about the current diff and do not copy a finding unless the current diff supports it):
```text
{rendered_examples}
```"""
        return await review_diff(
            title=title,
            description=description,
            diff=diff,
            specialist_instructions=context_instructions,
            telemetry_ctx=telemetry_ctx,
        )
