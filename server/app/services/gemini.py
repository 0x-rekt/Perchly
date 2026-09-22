import asyncio
import time
from decimal import Decimal

from google import genai
from google.genai import types

from app.core.config import GEMINI_MODEL, gemini_api_key
from app.core.pricing import calculate_cost
from app.schemas.findings import ReviewResult
from app.services.telemetry import ReviewContext, otel_span

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


def _generate_review(
    *, prompt: str, telemetry_ctx: ReviewContext, model: str
) -> ReviewResult:
    client = genai.Client(api_key=gemini_api_key())
    t0 = time.monotonic()
    try:
        with otel_span(
            "perchly.llm.generate_content",
            attributes={
                "perchly.review_run_id": telemetry_ctx.review_run_id,
                "perchly.repository": telemetry_ctx.repository,
                "perchly.pr_number": telemetry_ctx.pr_number,
                "perchly.head_sha": telemetry_ctx.head_sha,
                "perchly.agent": telemetry_ctx.agent,
                "perchly.phase": "agent",
                "perchly.span_type": "llm_call",
                "gen_ai.system": "gemini",
                "gen_ai.request.model": model,
            },
        ) as otel:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ReviewResult,
                    temperature=0,
                ),
            )
            usage = getattr(response, "usage_metadata", None)
            otel.set_attribute("gen_ai.usage.input_tokens", getattr(usage, "prompt_token_count", 0) or 0)
            otel.set_attribute("gen_ai.usage.output_tokens", getattr(usage, "candidates_token_count", 0) or 0)
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        _emit_llm_span(
            ctx=telemetry_ctx, model=model, phase="agent", latency_ms=latency_ms,
            tokens_in=0, tokens_out=0,
            input_summary=prompt[:500],
            status="failed", error_message=str(exc),
        )
        raise

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Extract token usage from response metadata when available.
    usage = getattr(response, "usage_metadata", None)
    tokens_in  = getattr(usage, "prompt_token_count",     0) or 0
    tokens_out = getattr(usage, "candidates_token_count", 0) or 0
    cost = calculate_cost(model=model, tokens_in=tokens_in, tokens_out=tokens_out)

    response_text = _response_text(response)

    _emit_llm_span(
        ctx=telemetry_ctx, model=model, phase="agent", latency_ms=latency_ms,
        tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost,
        input_summary=prompt[:500],
        output_summary=response_text[:500],
    )

    if not response_text:
        finish_reasons = [
            str(getattr(candidate, "finish_reason", "unknown"))
            for candidate in (getattr(response, "candidates", None) or [])
        ]
        prompt_feedback = getattr(response, "prompt_feedback", None)
        detail = ", ".join(finish_reasons) or "no candidates"
        if prompt_feedback:
            detail = f"{detail}; prompt_feedback={prompt_feedback}"
        raise GeminiReviewError(f"Gemini returned an empty review response ({detail})")

    try:
        return ReviewResult.model_validate_json(response_text)
    except ValueError as error:
        raise GeminiReviewError("Gemini returned an invalid review response") from error


def _response_text(response: object) -> str:
    """Extract text from Gemini's normal and structured-output response forms."""
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    # Some google-genai versions expose schema-constrained output as ``parsed``
    # instead of populating the convenience ``text`` property.
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        try:
            return ReviewResult.model_validate(parsed).model_dump_json()
        except (TypeError, ValueError):
            pass

    parts: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                parts.append(part_text)
    return "\n".join(parts)


def _emit_llm_span(
    *,
    ctx: ReviewContext,
    model: str,
    phase: str,
    latency_ms: int,
    tokens_in: int,
    tokens_out: int,
    cost_usd: Decimal | float | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    status: str = "success",
    error_message: str | None = None,
) -> None:
    """Fire-and-forget span write – runs inside the thread, never raises."""
    try:
        from app.services.telemetry import emit_span
        emit_span(
            review_run_id=ctx.review_run_id,
            repository=ctx.repository,
            pr_number=ctx.pr_number,
            head_sha=ctx.head_sha,
            agent=ctx.agent,
            phase=phase,
            span_type="llm_call",
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            input_summary=input_summary,
            output_summary=output_summary,
            status=status,
            error_message=error_message,
        )
    except Exception:
        pass


async def review_diff(
    *,
    title: str,
    description: str | None,
    diff: str,
    specialist_instructions: str = "",
    telemetry_ctx: ReviewContext | None = None,
) -> ReviewResult:
    """Request a schema-constrained Gemini review without blocking the event loop."""
    ctx = telemetry_ctx or ReviewContext()
    prompt = _review_prompt(
        title=title,
        description=description,
        diff=diff,
        specialist_instructions=specialist_instructions,
    )
    for attempt in range(2):
        try:
            return await asyncio.to_thread(
                _generate_review,
                prompt=prompt,
                telemetry_ctx=ctx,
                model=GEMINI_MODEL,
            )
        except GeminiReviewError as exc:
            # Gemini can transiently return promptFeedback=OTHER with no
            # candidates. A single retry avoids turning that transient response
            # into a specialist failure while keeping the retry bounded.
            if attempt == 0 and "empty review response" in str(exc):
                await asyncio.sleep(0.75)
                continue
            raise
    raise AssertionError("unreachable")
