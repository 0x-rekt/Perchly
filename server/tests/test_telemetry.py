import asyncio
from decimal import Decimal

import pytest

from app.core.pricing import calculate_cost
from app.services import telemetry


def test_instrument_activity_emits_span_with_phase_and_correlation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_emit_span_async(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(telemetry, "emit_span_async", fake_emit_span_async)

    @telemetry.instrument_activity(phase="posting")
    async def post_review(payload: dict[str, object]) -> bool:
        return True

    result = asyncio.run(
        post_review({"repository": "acme/repo", "pr_number": 7, "head_sha": "abc123"})
    )

    assert result is True
    assert captured["phase"] == "posting"
    assert captured["agent"] == "post_review"
    assert captured["span_type"] == "activity"
    assert captured["status"] == "success"
    assert captured["repository"] == "acme/repo"
    assert captured["pr_number"] == 7
    assert captured["head_sha"] == "abc123"
    assert captured["latency_ms"] >= 0


def test_instrument_activity_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_emit_span_async(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(telemetry, "emit_span_async", fake_emit_span_async)

    @telemetry.instrument_activity(phase="fetch")
    async def fetch(payload: dict[str, object]) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(fetch({"repository": "acme/repo", "pr_number": 1, "head_sha": "aaa"}))

    assert captured["status"] == "failed"
    assert captured["phase"] == "fetch"
    assert "boom" in str(captured["error_message"])


def test_activity_context_recurses_into_nested_payload() -> None:
    args = (
        {
            "retrieved": {
                "repository": "acme/repo",
                "pr_number": 7,
                "head_sha": "abc123",
            },
            "category": "security",
        },
    )
    ctx = telemetry._extract_activity_context(args, default_agent="run_specialist")

    assert ctx["repository"] == "acme/repo"
    assert ctx["pr_number"] == 7
    assert ctx["head_sha"] == "abc123"
    assert ctx["agent"] == "security"


def test_activity_context_ignores_empty_correlation_values() -> None:
    args = ({"repository": "", "pr_number": 0, "head_sha": None},)
    ctx = telemetry._extract_activity_context(args, default_agent="aggregate_review")

    assert ctx["repository"] == ""
    assert ctx["pr_number"] == 0
    assert ctx["head_sha"] == ""


def test_bare_instrument_activity_derives_phase_from_activity_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_emit_span_async(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(telemetry, "emit_span_async", fake_emit_span_async)

    @telemetry.instrument_activity
    async def run_specialist(payload: dict[str, object]) -> None:
        return None

    asyncio.run(run_specialist({}))
    assert captured["phase"] == "agent"


def test_calculate_cost_uses_model_rate_and_falls_back_to_zero() -> None:
    cost = calculate_cost(model="gemini-3.8-flash", tokens_in=1_000_000, tokens_out=0)
    assert cost == Decimal("0.075")

    unknown = calculate_cost(model="unknown-model", tokens_in=1_000_000)
    assert unknown == Decimal("0")