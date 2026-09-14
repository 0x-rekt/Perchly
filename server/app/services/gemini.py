import asyncio

from google import genai
from google.genai import types

from app.core.config import GEMINI_MODEL, gemini_api_key
from app.schemas.findings import ReviewResult

MAX_DIFF_CHARACTERS = 30_000


class GeminiReviewError(RuntimeError):
    """Raised when Gemini cannot return a valid structured review."""


def _review_prompt(
    *, title: str, description: str | None, diff: str, specialist_instructions: str = ""
) -> str:
    return f"""You are Perchly, a careful generalist pull-request reviewer.

Review only the supplied pull-request context. Report actionable, specific issues in
security, code quality, test coverage, or documentation. Do not invent files, line
numbers, dependencies, or behavior not supported by the diff. Prefer zero findings
to speculative or stylistic nitpicks. Each finding must point to a changed line.

For each newly introduced or changed executable branch, check whether the diff adds
corresponding tests. If it does not, emit one `test_coverage` warning that names the
missing behavior or edge cases. Prioritize that test-coverage finding over a generic
code-quality critique of the same changed branch.

{specialist_instructions}

Pull request title: {title}
Pull request description: {description or "(none)"}

Diff:
```diff
{diff[:MAX_DIFF_CHARACTERS]}
```
"""


def _generate_review(*, prompt: str) -> ReviewResult:
    client = genai.Client(api_key=gemini_api_key())
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ReviewResult,
            temperature=0,
        ),
    )
    if not response.text:
        raise GeminiReviewError("Gemini returned an empty review response")

    try:
        return ReviewResult.model_validate_json(response.text)
    except ValueError as error:
        raise GeminiReviewError("Gemini returned an invalid review response") from error


async def review_diff(
    *,
    title: str,
    description: str | None,
    diff: str,
    specialist_instructions: str = "",
) -> ReviewResult:
    """Request a schema-constrained Gemini review without blocking the event loop."""
    return await asyncio.to_thread(
        _generate_review,
        prompt=_review_prompt(
            title=title,
            description=description,
            diff=diff,
            specialist_instructions=specialist_instructions,
        ),
    )
