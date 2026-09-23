import asyncio
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.routers import observability
from app.services import telemetry


def _make_conn() -> object:
    class FakeConn:
        def close(self) -> None:
            pass

    return FakeConn()


def test_overview_metrics_maps_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(conn: object, query: str, params: tuple[object, ...] = ()) -> list:
        if "created_at::date" in query:
            return [
                [date(2026, 9, 21), 3],
                [date(2026, 9, 22), 2],
            ]
        if "FROM review_queue" in query:
            return [[2, 7.5]]
        if "percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms)" in query:
            return [["agent", 6, 120.0, 350.0, 1]]
        if "COALESCE(sum(cost_usd), 0)" in query:
            return [[Decimal("0.75"), 5]]
        if "jsonb_array_elements" in query:
            return [["security", 4, 3]]
        if "FROM outcome_examples" in query:
            return [["auto_post", 3], ["rejected", 1]]
        raise AssertionError(f"unexpected query: {query[:120]}")

    monkeypatch.setattr(telemetry, "_connect", _make_conn)
    monkeypatch.setattr(telemetry, "_run", fake_run)

    metrics = telemetry.overview_metrics(days=14)

    assert metrics["window_days"] == 14
    assert metrics["reviews_per_day"] == [
        {"day": "2026-09-21", "reviews": 3},
        {"day": "2026-09-22", "reviews": 2},
    ]
    assert metrics["total_reviews"] == 5
    assert metrics["cost"] == {
        "total_cost_usd_7d": 0.75,
        "reviews_7d": 5,
        "cost_per_review_usd": 0.15,
    }
    assert metrics["latency_by_phase"] == [
        {"phase": "agent", "spans": 6, "p50_ms": 120, "p95_ms": 350, "failures": 1}
    ]
    assert metrics["hitl_queue"] == {"depth": 2, "median_age_minutes": 7.5}
    assert metrics["acceptance_rate_by_category"] == [
        {"category": "security", "total": 4, "accepted": 3, "acceptance_rate": 0.75}
    ]


def test_overview_metrics_handles_missing_queue_and_decision_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(conn: object, query: str, params: tuple[object, ...] = ()) -> list:
        if "FROM review_queue" in query or "jsonb_array_elements" in query:
            raise Exception("relation does not exist")
        return []

    monkeypatch.setattr(telemetry, "_connect", _make_conn)
    monkeypatch.setattr(telemetry, "_run", fake_run)

    metrics = telemetry.overview_metrics(days=7)

    assert metrics["reviews_per_day"] == []
    assert metrics["total_reviews"] == 0
    assert metrics["cost"] == {
        "total_cost_usd_7d": 0.0,
        "reviews_7d": 0,
        "cost_per_review_usd": 0.0,
    }
    assert metrics["latency_by_phase"] == []
    assert metrics["hitl_queue"] == {"depth": 0, "median_age_minutes": 0.0}
    assert metrics["acceptance_rate_by_category"] == []


def test_query_spans_builds_where_for_all_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(conn: object, query: str, params: tuple[object, ...] = ()) -> list:
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr(telemetry, "_connect", _make_conn)
    monkeypatch.setattr(telemetry, "_run", fake_run)

    since = datetime(2026, 9, 1)
    until = datetime(2026, 9, 10)
    telemetry.query_spans(
        review_run_id="perchly-review-acme/repo-7-abc",
        repository="acme/repo",
        pr_number=7,
        head_sha="abc",
        since=since,
        until=until,
        limit=33,
    )

    sql = str(captured["query"])
    params = tuple(captured["params"])
    assert "review_run_id = %s" in sql
    assert "repository = %s" in sql
    assert "pr_number = %s" in sql
    assert "head_sha = %s" in sql
    assert "created_at >= %s" in sql
    assert "created_at < %s" in sql
    assert params[:5] == (
        "perchly-review-acme/repo-7-abc",
        "acme/repo",
        7,
        "abc",
        since,
    )
    assert params[-1] == 33


def test_list_traces_maps_run_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    started = datetime(2026, 9, 22, 10, 0, 0)
    completed = datetime(2026, 9, 22, 10, 1, 30)

    def fake_run(conn: object, query: str, params: tuple[object, ...] = ()) -> list:
        return [
            [
                "perchly-review-acme/repo-7-abc",
                "acme/repo",
                7,
                "abc",
                started,
                completed,
                True,
                Decimal("0.30"),
                5,
            ]
        ]

    monkeypatch.setattr(telemetry, "_connect", _make_conn)
    monkeypatch.setattr(telemetry, "_run", fake_run)

    traces = telemetry.list_traces(repository="acme/repo", limit=10)
    assert len(traces) == 1
    item = traces[0]
    assert item["review_run_id"] == "perchly-review-acme/repo-7-abc"
    assert item["repository"] == "acme/repo"
    assert item["pr_number"] == 7
    assert item["started_at"] == started.isoformat()
    assert item["status"] == "failed"
    assert item["total_cost_usd"] == 0.3
    assert item["span_count"] == 5
    assert item["duration_seconds"] == 90.0


def test_get_trace_builds_summary_and_orders_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans = [
        {
            "id": 2,
            "review_run_id": "perchly-review-acme/repo-7-abc",
            "repository": "acme/repo",
            "pr_number": 7,
            "head_sha": "abc",
            "agent": "aggregate",
            "phase": "aggregation",
            "span_type": "activity",
            "model": None,
            "tokens_in": None,
            "tokens_out": None,
            "cost_usd": None,
            "latency_ms": 400,
            "input_summary": None,
            "output_summary": None,
            "status": "success",
            "error_message": None,
            "created_at": datetime(2026, 9, 22, 10, 0, 30),
        },
        {
            "id": 1,
            "review_run_id": "perchly-review-acme/repo-7-abc",
            "repository": "acme/repo",
            "pr_number": 7,
            "head_sha": "abc",
            "agent": "security",
            "phase": "agent",
            "span_type": "llm_call",
            "model": "gemini-3.8-flash",
            "tokens_in": 5000,
            "tokens_out": 200,
            "cost_usd": Decimal("0.30"),
            "latency_ms": 1200,
            "input_summary": "diff",
            "output_summary": "ok",
            "status": "failed",
            "error_message": "boom",
            "created_at": datetime(2026, 9, 22, 10, 0, 0),
        },
    ]
    monkeypatch.setattr(telemetry, "query_spans", lambda **kwargs: spans)

    trace = telemetry.get_trace(review_run_id="perchly-review-acme/repo-7-abc")

    assert trace is not None
    assert trace["status"] == "failed"
    assert trace["span_count"] == 2
    assert trace["total_cost_usd"] == 0.3
    assert trace["duration_seconds"] == 30.0
    assert [span["id"] for span in trace["spans"]] == [1, 2]
    llm = trace["spans"][0]
    assert llm["tokens_in"] == 5000
    assert llm["tokens_out"] == 200
    assert llm["cost_usd"] == 0.3
    activity = trace["spans"][1]
    assert activity["tokens_in"] == 0
    assert activity["cost_usd"] == 0.0


def test_get_trace_returns_none_when_no_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry, "query_spans", lambda **kwargs: [])
    assert telemetry.get_trace(review_run_id="perchly-review-acme/repo-7-abc") is None


def test_traces_endpoint_rejects_inverted_time_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    monkeypatch.setattr(
        telemetry,
        "list_traces",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("list_traces should not be called")
        ),
    )
    since = datetime(2026, 9, 10)
    until = datetime(2026, 9, 1)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            observability.traces(since=since, until=until)
        )
    assert exc.value.status_code == 422


def test_overview_endpoint_delegates_to_service(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {"window_days": 14, "reviews_per_day": []}
    monkeypatch.setattr(telemetry, "overview_metrics", lambda days: expected)

    result = asyncio.run(observability.overview(days=14))
    assert result is expected


def test_trace_detail_endpoint_returns_404_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    monkeypatch.setattr(telemetry, "get_trace", lambda **kwargs: None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            observability.trace_detail("perchly-review-acme/repo-7-abc")
        )
    assert exc.value.status_code == 404
