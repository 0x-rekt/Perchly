from __future__ import annotations

import asyncio
import functools
import logging
import os
import re
import ssl
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, TypeVar
from urllib.parse import unquote, urlparse

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace import Status, StatusCode

from app.core.config import OTEL_EXPORTER_OTLP_ENDPOINT, database_url
from pg8000.exceptions import DatabaseError as PGDatabaseError
from pg8000.exceptions import InterfaceError as PGInterfaceError

logger = logging.getLogger(__name__)


def _build_tracer() -> trace.Tracer:
    """Create the process tracer once, with an opt-in local exporter.

    The database writer below remains the product's queryable sink. The SDK
    tracer is deliberately independent of it, so a telemetry database outage
    cannot prevent an OpenTelemetry span from being created. Console export is
    useful during local development and disabled by default to avoid leaking
    source snippets into logs.
    """
    provider = TracerProvider(
        resource=Resource.create({"service.name": "perchly", "service.version": "0.1.0"})
    )
    if OTEL_EXPORTER_OTLP_ENDPOINT:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(
                SimpleSpanProcessor(OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT))
            )
        except Exception:
            logger.warning("OTLP exporter could not be configured", exc_info=True)
    if os.getenv("PERCHLY_OTEL_CONSOLE_EXPORT", "").lower() in {"1", "true", "yes"}:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    try:
        trace.set_tracer_provider(provider)
    except Exception:
        # Test reloaders and embedded workers may initialize the global provider
        # more than once. Reuse the SDK's already-installed provider in that case.
        pass
    return trace.get_tracer("perchly")


_TRACER = _build_tracer()
_SENSITIVE_VALUE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|private[_-]?key)"
    r"(\s*[:=]\s*)([\"']?)([^\s,;\"']+)\3"
)


def _redact_summary(value: str | None) -> str | None:
    """Keep useful telemetry context without persisting credential values."""
    if value is None:
        return None
    redacted = _SENSITIVE_VALUE.sub(r"\1\2\3[REDACTED]\3", value)
    redacted = re.sub(r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", "[REDACTED PEM]", redacted, flags=re.S)
    return redacted[:500]


@contextmanager
def otel_span(name: str, *, attributes: dict[str, Any] | None = None):
    """Create an OpenTelemetry span and mark exceptions consistently."""
    with _TRACER.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        else:
            span.set_status(Status(StatusCode.OK))

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class ReviewContext:
    """Run correlation forwarded into services that call LLM APIs."""

    review_run_id: str = ""
    repository: str = ""
    pr_number: int = 0
    head_sha: str = ""
    agent: str = "generalist"


def emit_span(
    *,
    review_run_id: str,
    repository: str,
    pr_number: int,
    head_sha: str,
    agent: str,
    span_type: str,
    latency_ms: int,
    phase: str = "",
    model: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: Decimal | float | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    status: str = "success",
    error_message: str | None = None,
) -> None:
    """Synchronous span write – call from a thread (not the event loop)."""
    cost = Decimal(str(cost_usd)) if cost_usd is not None else Decimal("0")

    def operation(conn) -> None:
        _run(
            conn,
            """
            INSERT INTO agent_spans (
                review_run_id, repository, pr_number, head_sha,
                agent, phase, span_type, model,
                tokens_in, tokens_out, cost_usd, latency_ms,
                input_summary, output_summary,
                status, error_message
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s
            )
            """,
            (
                review_run_id, repository, pr_number, head_sha,
                agent, phase, span_type, model,
                tokens_in, tokens_out, str(cost), latency_ms,
                _redact_summary(input_summary), _redact_summary(output_summary),
                status, error_message,
            ),
        )

    _execute(operation)


async def emit_span_async(
    *,
    review_run_id: str,
    repository: str,
    pr_number: int,
    head_sha: str,
    agent: str,
    span_type: str,
    latency_ms: int,
    phase: str = "",
    model: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: Decimal | float | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    status: str = "success",
    error_message: str | None = None,
) -> None:
    """Non-blocking span write – safe to await from the event loop."""
    try:
        await asyncio.to_thread(
            emit_span,
            review_run_id=review_run_id,
            repository=repository,
            pr_number=pr_number,
            head_sha=head_sha,
            agent=agent,
            span_type=span_type,
            latency_ms=latency_ms,
            phase=phase,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            input_summary=input_summary,
            output_summary=output_summary,
            status=status,
            error_message=error_message,
        )
    except Exception:
        logger.warning(
            "Failed to emit telemetry span agent=%s type=%s phase=%s",
            agent,
            span_type,
            phase,
            exc_info=True,
        )


def query_spans(
    *,
    review_run_id: str | None = None,
    repository: str | None = None,
    pr_number: int | None = None,
    head_sha: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return raw spans filtered by repository, run, and optional time window."""
    conditions: list[str] = []
    params: list[Any] = []

    if review_run_id:
        conditions.append("review_run_id = %s")
        params.append(review_run_id)
    if repository:
        conditions.append("repository = %s")
        params.append(repository)
    if pr_number is not None:
        conditions.append("pr_number = %s")
        params.append(pr_number)
    if head_sha:
        conditions.append("head_sha = %s")
        params.append(head_sha)
    if since:
        conditions.append("created_at >= %s")
        params.append(since)
    if until:
        conditions.append("created_at < %s")
        params.append(until)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    def operation(conn) -> list[list[Any]]:
        return _run(
            conn,
            f"""
            SELECT
                id, review_run_id, repository, pr_number, head_sha,
                agent, phase, span_type, model,
                tokens_in, tokens_out, cost_usd, latency_ms,
                input_summary, output_summary,
                status, error_message, created_at
            FROM agent_spans
            {where}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            tuple(params),
        )

    rows = _execute(operation)

    fields = (
        "id", "review_run_id", "repository", "pr_number", "head_sha",
        "agent", "phase", "span_type", "model",
        "tokens_in", "tokens_out", "cost_usd", "latency_ms",
        "input_summary", "output_summary",
        "status", "error_message", "created_at",
    )
    return [dict(zip(fields, row, strict=True)) for row in rows]


def overview_metrics(days: int = 14) -> dict[str, Any]:
    """Aggregate volume, cost, latency, queue, and acceptance-rate metrics."""

    def operation(conn) -> None:
        def safe(query: str, params: tuple[Any, ...] = ()) -> list[list[Any]]:
            # Queue/decision tables may not exist until the first review runs.
            try:
                return _run(conn, query, params)
            except Exception:
                return []

        aggregate_per_day = safe(
            """
            SELECT day::date AS day, COALESCE(sum(total_reviews), 0)::integer AS reviews
            FROM daily_review_metrics
            WHERE day >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
            GROUP BY day::date
            ORDER BY day::date
            """,
            (days,),
        )
        per_day_rows.append(
            aggregate_per_day
            or safe(
                """
                SELECT created_at::date AS day, count(DISTINCT review_run_id) AS reviews
                FROM agent_spans
                WHERE created_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                GROUP BY created_at::date
                ORDER BY created_at::date
                """,
                (days,),
            )
        )
        aggregate_cost = safe(
            """
            SELECT COALESCE(sum(total_cost), 0), COALESCE(sum(total_reviews), 0)::integer
            FROM daily_review_metrics
            WHERE day >= CURRENT_TIMESTAMP - (7 * INTERVAL '1 day')
            """
        )
        cost_rows.append(
            aggregate_cost
            or safe(
                """
                SELECT COALESCE(sum(cost_usd), 0), count(DISTINCT review_run_id)
                FROM agent_spans
                WHERE created_at >= CURRENT_TIMESTAMP - (7 * INTERVAL '1 day')
                """
            )
        )
        aggregate_latency = safe(
            """
            SELECT phase, sum(span_count)::integer,
                   percentile_cont(0.50) WITHIN GROUP (ORDER BY p50_latency_ms),
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY p95_latency_ms),
                   sum(failures)::integer
            FROM phase_daily_metrics
            WHERE day >= CURRENT_TIMESTAMP - (7 * INTERVAL '1 day')
            GROUP BY phase
            ORDER BY 4 DESC
            """
        )
        latency_rows.append(
            aggregate_latency
            or safe(
                """
                SELECT phase, count(*),
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms),
                       percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),
                       count(*) FILTER (WHERE status = 'failed')
                FROM agent_spans
                WHERE created_at >= CURRENT_TIMESTAMP - (7 * INTERVAL '1 day')
                  AND phase <> ''
                GROUP BY phase
                ORDER BY 4 DESC
                """
            )
        )
        queue_rows.append(
            safe(
                """
                SELECT count(*),
                       COALESCE(percentile_cont(0.5) WITHIN GROUP (
                           ORDER BY EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - created_at)) / 60
                       ), 0)
                FROM review_queue
                WHERE status = 'pending'
                """
            )
        )
        acceptance_rows.append(
            safe(
                """
                SELECT category, count(*) AS total,
                       count(*) FILTER (WHERE accepted) AS accepted
                FROM (
                    SELECT f.value ->> 'category' AS category, TRUE AS accepted
                    FROM review_outcomes ro
                    CROSS JOIN LATERAL jsonb_array_elements(
                        COALESCE(ro.review_payload_json -> 'findings', '[]'::jsonb)
                    ) AS f
                    WHERE ro.outcome = 'auto_post'
                    UNION ALL
                    SELECT f.value ->> 'category',
                           (d.decision IN ('approve', 'edit'))
                    FROM review_decisions d
                    JOIN review_queue q ON q.id = d.queue_item_id
                    CROSS JOIN LATERAL jsonb_array_elements(
                        COALESCE(
                            CASE WHEN d.edited_review_json IS NOT NULL
                                 THEN d.edited_review_json -> 'findings'
                                 ELSE q.review_payload_json -> 'review' -> 'findings'
                            END,
                            '[]'::jsonb
                        )
                    ) AS f
                ) s
                GROUP BY category
                ORDER BY total DESC
                """
            )
        )

    per_day_rows: list[list[list[Any]]] = []
    cost_rows: list[list[list[Any]]] = []
    latency_rows: list[list[list[Any]]] = []
    queue_rows: list[list[list[Any]]] = []
    acceptance_rows: list[list[list[Any]]] = []

    _execute(operation)
    per_day_rows = per_day_rows[0]
    cost_rows = cost_rows[0]
    latency_rows = latency_rows[0]
    queue_rows = queue_rows[0]
    acceptance_rows = acceptance_rows[0]

    reviews_per_day = [
        {"day": row[0].isoformat(), "reviews": int(row[1])} for row in per_day_rows
    ]
    total_reviews = sum(item["reviews"] for item in reviews_per_day)

    total_cost_7d = float(cost_rows[0][0]) if cost_rows else 0.0
    reviews_7d = int(cost_rows[0][1]) if cost_rows else 0
    cost_per_review = (total_cost_7d / reviews_7d) if reviews_7d else 0.0

    latency_by_phase = [
        {
            "phase": row[0],
            "spans": int(row[1]),
            "p50_ms": int(round(float(row[2] or 0))),
            "p95_ms": int(round(float(row[3] or 0))),
            "failures": int(row[4]),
        }
        for row in latency_rows
    ]

    hitl_queue = {
        "depth": int(queue_rows[0][0]) if queue_rows else 0,
        "median_age_minutes": float(queue_rows[0][1] or 0.0) if queue_rows else 0.0,
    }

    acceptance_by_category = [
        {
            "category": row[0],
            "total": int(row[1]),
            "accepted": int(row[2]),
            "acceptance_rate": (
                round(float(row[2]) / float(row[1]), 4) if float(row[1]) else 0.0
            ),
        }
        for row in acceptance_rows
    ]

    return {
        "window_days": days,
        "reviews_per_day": reviews_per_day,
        "total_reviews": total_reviews,
        "cost": {
            "total_cost_usd_7d": total_cost_7d,
            "reviews_7d": reviews_7d,
            "cost_per_review_usd": round(cost_per_review, 6),
        },
        "latency_by_phase": latency_by_phase,
        "hitl_queue": hitl_queue,
        "acceptance_rate_by_category": acceptance_by_category,
    }


def list_traces(
    *,
    repository: str | None = None,
    agent: str | None = None,
    pr_number: int | None = None,
    head_sha: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Group spans into review runs (traces), newest first."""
    conditions: list[str] = []
    params: list[Any] = []
    if repository:
        conditions.append("s.repository = %s")
        params.append(repository)
    if agent:
        conditions.append("s.agent = %s")
        params.append(agent)
    if pr_number is not None:
        conditions.append("s.pr_number = %s")
        params.append(pr_number)
    if head_sha:
        conditions.append("s.head_sha = %s")
        params.append(head_sha)
    if since:
        conditions.append("s.created_at >= %s")
        params.append(since)
    if until:
        conditions.append("s.created_at < %s")
        params.append(until)
    where = (" AND ".join(conditions)) if conditions else "TRUE"
    params.append(limit)

    def operation(conn) -> list[list[Any]]:
        return _run(
            conn,
            f"""
            SELECT s.review_run_id, s.repository, s.pr_number, s.head_sha,
                   min(s.created_at) AS started_at,
                   max(s.created_at) AS completed_at,
                   bool_or(s.status = 'failed') AS has_failure,
                   COALESCE(sum(s.cost_usd), 0) AS total_cost,
                   count(*) AS span_count
            FROM agent_spans s
            WHERE {where}
            GROUP BY s.review_run_id, s.repository, s.pr_number, s.head_sha
            ORDER BY completed_at DESC
            LIMIT %s
            """,
            tuple(params),
        )

    rows = _execute(operation)

    return [_trace_summary(row) for row in rows]


def get_trace(*, review_run_id: str) -> dict[str, Any] | None:
    """Return one trace with its ordered spans and a run summary."""
    spans = query_spans(review_run_id=review_run_id, limit=500)
    if not spans:
        return None

    timestamps = [span["created_at"] for span in spans if span["created_at"] is not None]
    started_at = min(timestamps) if timestamps else None
    completed_at = max(timestamps) if timestamps else None

    summary = {
        "review_run_id": review_run_id,
        "repository": spans[0]["repository"],
        "pr_number": int(spans[0]["pr_number"]),
        "head_sha": spans[0]["head_sha"],
        "started_at": started_at.isoformat() if started_at else None,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "duration_seconds": (
            round((completed_at - started_at).total_seconds(), 3)
            if started_at and completed_at
            else None
        ),
        "status": (
            "failed"
            if any(span["status"] == "failed" for span in spans)
            else "success"
        ),
        "total_cost_usd": round(sum(float(span["cost_usd"] or 0) for span in spans), 6),
        "span_count": len(spans),
    }
    summary["spans"] = [
        {
            "id": int(span["id"]),
            "agent": span["agent"],
            "phase": span["phase"],
            "span_type": span["span_type"],
            "model": span["model"],
            "tokens_in": int(span["tokens_in"] or 0),
            "tokens_out": int(span["tokens_out"] or 0),
            "cost_usd": float(span["cost_usd"] or 0),
            "latency_ms": int(span["latency_ms"]),
            "input_summary": span["input_summary"],
            "output_summary": span["output_summary"],
            "status": span["status"],
            "error_message": span["error_message"],
            "created_at": (
                span["created_at"].isoformat() if span["created_at"] else None
            ),
        }
        for span in sorted(spans, key=lambda span: span["created_at"] or datetime.min)
    ]
    return summary


def _trace_summary(row: list[Any]) -> dict[str, Any]:
    (
        review_run_id, repository, pr_number, head_sha,
        started_at, completed_at, has_failure, total_cost, span_count,
    ) = row
    return {
        "review_run_id": review_run_id,
        "repository": repository,
        "pr_number": int(pr_number),
        "head_sha": head_sha,
        "started_at": started_at.isoformat() if started_at else None,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "duration_seconds": (
            round((completed_at - started_at).total_seconds(), 3)
            if started_at and completed_at
            else None
        ),
        "status": "failed" if has_failure else "success",
        "total_cost_usd": float(total_cost),
        "span_count": int(span_count),
    }


def refresh_aggregates() -> None:
    """Refresh the Timescale aggregate or PostgreSQL materialized-view fallback."""

    def operation(conn) -> None:
        for view in ("daily_review_metrics", "phase_daily_metrics"):
            if _is_continuous_aggregate(conn, view):
                _run(
                    conn,
                    f"CALL refresh_continuous_aggregate('{view}', NULL, NULL)",
                )
                continue
            try:
                rows = _run(conn, f"SELECT count(*) FROM {view}")
                is_empty = not rows or int(rows[0][0]) == 0
            except Exception:
                # A WITH NO DATA materialized view cannot be scanned until its
                # first refresh. Treat that state as empty.
                is_empty = True
            if is_empty:
                _run(conn, f"REFRESH MATERIALIZED VIEW {view}")
            else:
                _run(conn, f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")

    # Materialized-view refreshes can scan a large span history and exceed the
    # short request timeout used by ordinary telemetry reads/writes.
    _execute(operation, timeout=120)


def _is_continuous_aggregate(conn, view_name: str) -> bool:
    """Return whether the metrics view is registered as a Timescale aggregate."""
    try:
        rows = _run(
            conn,
            """
            SELECT 1
            FROM timescaledb_information.continuous_aggregates
            WHERE view_name = %s
            LIMIT 1
            """,
            (view_name,),
        )
        return bool(rows)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Activity instrumentation decorator
# ---------------------------------------------------------------------------

_ACTIVITY_PHASES = {
    "fetch_review_context": "fetch",
    "retrieve_repository_context": "retrieval",
    "run_specialist": "agent",
    "aggregate_review": "aggregation",
    "route_aggregated_review": "routing",
    "post_review": "posting",
    "persist_automatic_decision": "persistence",
    "persist_reviewer_decision": "persistence",
    "validate_edited_review": "validation",
    "release_review_claim": "cleanup",
}


def instrument_activity(
    fn_or_phase: F | str | None = None, *, phase: str | None = None
) -> F:
    """Wrap a Temporal activity to emit activity spans on completion.

    Supports both forms::

        @activity.defn
        @instrument_activity
        async def my_activity(...): ...

        @activity.defn
        @instrument_activity(phase="posting")
        async def my_activity(...): ...

    Bare usage derives the phase from the activity name; explicit phases take
    precedence. Correlation keys (repository / pr / head_sha) are extracted
    best-effort from the activity payload.
    """
    if callable(fn_or_phase):
        fn = fn_or_phase
        return _instrument_activity(
            fn,
            phase=phase or _ACTIVITY_PHASES.get(fn.__name__, "activity"),
        )

    chosen = phase or fn_or_phase or "activity"

    def decorator(fn: F) -> F:
        return _instrument_activity(fn, phase=chosen)

    return decorator


def _instrument_activity(fn: F, *, phase: str) -> F:
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = _extract_activity_context(args, default_agent=fn.__name__)
        t0 = time.monotonic()
        attrs = {
            "perchly.review_run_id": ctx["review_run_id"],
            "perchly.repository": ctx["repository"],
            "perchly.pr_number": ctx["pr_number"],
            "perchly.head_sha": ctx["head_sha"],
            "perchly.agent": ctx["agent"],
            "perchly.phase": phase,
            "perchly.span_type": "activity",
        }
        with otel_span(f"perchly.activity.{phase}", attributes=attrs):
            try:
                result = await fn(*args, **kwargs)
            except Exception as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                await _silent_emit(
                    review_run_id=ctx["review_run_id"],
                    repository=ctx["repository"],
                    pr_number=ctx["pr_number"],
                    head_sha=ctx["head_sha"],
                    agent=ctx["agent"],
                    phase=phase,
                    span_type="activity",
                    latency_ms=latency_ms,
                    status="failed",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                raise

            latency_ms = int((time.monotonic() - t0) * 1000)
            await _silent_emit(
                review_run_id=ctx["review_run_id"],
                repository=ctx["repository"],
                pr_number=ctx["pr_number"],
                head_sha=ctx["head_sha"],
                agent=ctx["agent"],
                phase=phase,
                span_type="activity",
                latency_ms=latency_ms,
                status="success",
            )
            return result

    return wrapper  # type: ignore[return-value]


async def _silent_emit(**kwargs: Any) -> None:
    try:
        await emit_span_async(**kwargs)
    except Exception:
        pass


def _extract_activity_context(
    args: tuple[Any, ...], *, default_agent: str
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "review_run_id": "",
        "repository": "",
        "pr_number": 0,
        "head_sha": "",
        "agent": default_agent,
    }
    try:
        from temporalio import activity as _activity

        ctx["review_run_id"] = _activity.info().workflow_id
    except Exception:
        pass

    for arg in args:
        if isinstance(arg, dict) and isinstance(arg.get("category"), str):
            ctx["agent"] = arg["category"]
        _collect_correlation(ctx, arg)
    return ctx


def _collect_correlation(ctx: dict[str, Any], value: Any) -> None:
    """Recursively find repository/pr_number/head_sha anywhere in a payload."""
    if isinstance(value, dict):
        for key in ("repository", "head_sha"):
            if key in value and value[key] not in (None, "") and not ctx[key]:
                ctx[key] = str(value[key])
        if "pr_number" in value and value["pr_number"] not in (None, "") and not ctx["pr_number"]:
            try:
                ctx["pr_number"] = int(value["pr_number"])
            except (TypeError, ValueError):
                pass
        for nested in value.values():
            _collect_correlation(ctx, nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _collect_correlation(ctx, nested)


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


def initialize_schema() -> None:
    """Idempotently apply the telemetry schema.

    Drops stale tables from earlier incorrect schemas, then creates the
    canonical agent_spans hypertable and daily_review_metrics view.
    """

    def operation(conn) -> None:
        _migrate_drop_old_schema(conn)
        timescaledb_available = _ensure_timescaledb(conn)
        _create_agent_spans(conn)
        _create_hypertable(conn)
        _create_indexes(conn)
        timescaledb_available = _create_daily_metrics_view(
            conn, timescaledb_available=timescaledb_available
        )
        _create_phase_metrics_view(conn, timescaledb_available=timescaledb_available)

    _execute(operation)


def _migrate_drop_old_schema(conn) -> None:
    """Drop objects from previous incorrect schema versions."""
    for view in (
        "agent_spans_hourly",
        "agent_spans_daily",
        "daily_review_metrics",
        "phase_daily_metrics",
    ):
        _run(conn, f"DROP MATERIALIZED VIEW IF EXISTS {view} CASCADE")

    # Drop agent_spans only if it has the old incorrect layout.
    rows = _run(
        conn,
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'agent_spans' AND column_name = 'activity_name'
        """,
    )
    if rows:
        logger.info("Dropping stale agent_spans table (old schema)")
        _run(conn, "DROP TABLE IF EXISTS agent_spans CASCADE")


def _ensure_timescaledb(conn) -> bool:
    try:
        _run(conn, "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
        return True
    except Exception:
        logger.warning("timescaledb unavailable; agent_spans will remain a plain table")
        return False


def _create_agent_spans(conn) -> None:
    _run(
        conn,
        """
        CREATE TABLE IF NOT EXISTS agent_spans (
            id              BIGSERIAL,
            review_run_id   TEXT           NOT NULL,
            repository      TEXT           NOT NULL,
            pr_number       INTEGER        NOT NULL,
            head_sha        TEXT           NOT NULL,
            agent           TEXT           NOT NULL,
            phase           TEXT           NOT NULL DEFAULT '',
            span_type       TEXT           NOT NULL,
            model           TEXT,
            tokens_in       INTEGER        NOT NULL DEFAULT 0,
            tokens_out      INTEGER        NOT NULL DEFAULT 0,
            cost_usd        NUMERIC(10,6)  NOT NULL DEFAULT 0,
            latency_ms      INTEGER        NOT NULL,
            input_summary   TEXT,
            output_summary  TEXT,
            status          TEXT           NOT NULL DEFAULT 'success'
                CHECK (status IN ('success', 'failed')),
            error_message   TEXT,
            created_at      TIMESTAMPTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id, created_at)
        )
        """,
    )


def _create_hypertable(conn) -> None:
    try:
        _run(
            conn,
            "SELECT create_hypertable('agent_spans', 'created_at', if_not_exists => TRUE)",
        )
    except Exception:
        logger.warning("could not create hypertable; agent_spans remains a plain table")


def _create_indexes(conn) -> None:
    for ddl in [
        "CREATE INDEX IF NOT EXISTS idx_agent_spans_run_id  ON agent_spans (review_run_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_agent_spans_repo_pr ON agent_spans (repository, pr_number, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_agent_spans_agent   ON agent_spans (agent, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_agent_spans_phase   ON agent_spans (phase, created_at DESC)",
    ]:
        _run(conn, ddl)


def _create_daily_metrics_view(conn, *, timescaledb_available: bool) -> bool:
    """Create a Timescale continuous aggregate or PostgreSQL fallback."""
    bucket_expression = (
        "time_bucket('1 day', created_at)"
        if timescaledb_available
        else "date_trunc('day', created_at)"
    )
    view_options = "WITH (timescaledb.continuous)" if timescaledb_available else ""
    try:
        _run(
            conn,
            f"""
            CREATE MATERIALIZED VIEW IF NOT EXISTS daily_review_metrics
            {view_options} AS
            SELECT
                {bucket_expression}                         AS day,
                repository,
                count(DISTINCT review_run_id)               AS total_reviews,
                sum(cost_usd)                               AS total_cost,
                sum(cost_usd) / NULLIF(count(DISTINCT review_run_id), 0)
                                                            AS avg_cost_per_review,
                percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms)
                                                            AS p50_latency_ms,
                percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)
                                                            AS p95_latency_ms
            FROM agent_spans
            GROUP BY day, repository
            WITH NO DATA
            """,
        )
    except Exception:
        if not timescaledb_available:
            raise
        logger.warning("Timescale continuous aggregate unavailable; using PostgreSQL materialized view")
        _rollback_after_schema_error(conn)
        return _create_daily_metrics_view(conn, timescaledb_available=False)
    _run(
        conn,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_metrics_pk "
        "ON daily_review_metrics (day, repository)",
    )
    return timescaledb_available


def _create_phase_metrics_view(conn, *, timescaledb_available: bool) -> bool:
    """Create the phase-level aggregate used for p50/p95 dashboard metrics."""
    bucket_expression = (
        "time_bucket('1 day', created_at)"
        if timescaledb_available
        else "date_trunc('day', created_at)"
    )
    view_options = "WITH (timescaledb.continuous)" if timescaledb_available else ""
    try:
        _run(
            conn,
            f"""
            CREATE MATERIALIZED VIEW IF NOT EXISTS phase_daily_metrics
            {view_options} AS
            SELECT
                {bucket_expression} AS day,
                phase,
                count(*) AS span_count,
                percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms,
                percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
                count(*) FILTER (WHERE status = 'failed') AS failures
            FROM agent_spans
            WHERE phase <> ''
            GROUP BY day, phase
            WITH NO DATA
            """,
        )
    except Exception:
        if not timescaledb_available:
            raise
        logger.warning("Timescale phase aggregate unavailable; using PostgreSQL materialized view")
        _rollback_after_schema_error(conn)
        return _create_phase_metrics_view(conn, timescaledb_available=False)
    _run(
        conn,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_phase_daily_metrics_pk "
        "ON phase_daily_metrics (day, phase)",
    )
    return timescaledb_available


def _rollback_after_schema_error(conn) -> None:
    """Clear PostgreSQL's failed transaction before applying a fallback DDL."""
    try:
        _run(conn, "ROLLBACK")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Connection / query helpers
# ---------------------------------------------------------------------------


def _connect(*, timeout: int = 10):
    from pg8000.native import Connection

    parsed = urlparse(database_url())
    return Connection(
        user=parsed.username or "",
        password=unquote(parsed.password or ""),
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/"),
        ssl_context=ssl.create_default_context(),
        timeout=timeout,
    )


_STALE_SQLSTATES = frozenset(
    {"26000", "08000", "08001", "08003", "08004", "08006", "08P01", "57P01", "57P02"}
)


def _is_stale_session(exc: BaseException) -> bool:
    if isinstance(exc, (PGInterfaceError, OSError, TimeoutError)):
        return True
    if isinstance(exc, PGDatabaseError):
        detail = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
        return detail.get("C") in _STALE_SQLSTATES
    return False


def _execute(operation: Callable[[Any], Any], *, timeout: int = 10) -> Any:
    """Run one DB operation, retrying once with a fresh connection.

    Every operation uses its own short-lived connection, so the Neon
    transaction-mode pooler recycling a session (which drops pg8000's
    extended-protocol prepared statements, SQLSTATE 26000) is always
    recovered simply by connecting again.
    """
    for attempt in range(2):
        conn = _connect() if timeout == 10 else _connect(timeout=timeout)
        try:
            return operation(conn)
        except Exception as exc:
            if attempt == 1 or not _is_stale_session(exc):
                raise
            logger.warning(
                "db session recycled, reconnecting (attempt %d): %s",
                attempt + 1,
                exc,
            )
        finally:
            conn.close()
    return None  # unreachable


def _run(conn, query: str, parameters: tuple[Any, ...] = ()) -> list[list[Any]]:
    import re
    names = iter(f"param_{i}" for i in range(len(parameters)))
    query = re.sub(r"%s", lambda _: f":{next(names)}", query)
    values = {f"param_{i}": v for i, v in enumerate(parameters)}
    return conn.run(query, **values)
