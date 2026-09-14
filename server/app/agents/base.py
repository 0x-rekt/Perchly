from dataclasses import dataclass

from app.schemas.findings import FindingCategory, ReviewResult
from app.services.gemini import review_diff


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
    ) -> ReviewResult:
        """Review PR input. Context becomes meaningful once Phase 1 retrieval is added."""
        context_instructions = self.instructions
        if retrieved_context:
            context_instructions += f"""

Relevant repository context:
```text
{retrieved_context}
```"""
        return await review_diff(
            title=title,
            description=description,
            diff=diff,
            specialist_instructions=context_instructions,
        )
