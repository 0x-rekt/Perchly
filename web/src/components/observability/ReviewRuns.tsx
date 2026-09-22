import { useEffect, useState } from "react";
import {
  EmptyState,
  PageHeading,
  PanelHeading,
  SkeletonPanel,
  StatusPill,
} from "../ui/DashboardChrome";
import { getTrace, getTraces } from "../../lib/api";
import { Activity, GitPullRequest } from "../../lib/icons";
import {
  formatDateTime,
  formatDuration,
  formatMoney,
  titleCase,
} from "../../lib/format";
import { useSurface } from "../../hooks/use-surface";
import type { Span, TraceDetail, TraceSummary, TracesResponse } from "../../types";

export function ReviewRuns({
  onLiveChange,
}: {
  onLiveChange: (live: boolean) => void;
}) {
  const surface = useSurface<TracesResponse>(getTraces);
  const { data, error, loading, reload } = surface;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailState, setDetailState] = useState<{
    id: string | null;
    trace: TraceDetail | null;
    error: string | null;
  }>({ id: null, trace: null, error: null });
  const items = data?.items ?? [];
  const failures = items.filter((item) => item.status === "failed").length;
  const activeId =
    selectedId && items.some((run) => run.review_run_id === selectedId)
      ? selectedId
      : (items[0]?.review_run_id ?? null);

  useEffect(() => {
    onLiveChange(error === null);
  }, [error, onLiveChange]);

  useEffect(() => {
    const onRefresh = () => reload();
    window.addEventListener("perchly:refresh", onRefresh);
    return () => window.removeEventListener("perchly:refresh", onRefresh);
  }, [reload]);

  useEffect(() => {
    if (!activeId) return;
    let active = true;
    getTrace(activeId)
      .then((trace) => {
        if (active) setDetailState({ id: activeId, trace, error: null });
      })
      .catch((err) => {
        if (active) {
          setDetailState({
            id: activeId,
            trace: null,
            error: err instanceof Error ? err.message : "Failed to load trace.",
          });
        }
      });
    return () => {
      active = false;
    };
  }, [activeId]);

  const detail = detailState.id === activeId ? detailState : null;
  const showing = detail?.trace ?? null;
  const showingError = detail?.error ?? null;
  const loadingDetail = activeId !== null && !showing && !showingError;

  const aside =
    error !== null ? (
      <StatusPill tone="error">Connection failed</StatusPill>
    ) : failures > 0 ? (
      <StatusPill tone="warn">{failures} run{failures === 1 ? "" : "s"} failed</StatusPill>
    ) : (
      <StatusPill tone="ok">{items.length} runs in this window</StatusPill>
    );

  return (
    <div className="runs-layout">
      <PageHeading
        title="Review runs"
        description="Every reviewed pull request, expandable to its ordered spans."
        aside={aside}
      />
      <div className="runs-grid">
      <aside className="queue-panel" aria-label="Review runs">
        <PanelHeading title="Review runs" meta="Newest first" />
        {loading && !data ? (
          <SkeletonPanel rows={6} />
        ) : error && !data ? (
          <div className="panel-error-text" role="alert">
            {error}
          </div>
        ) : items.length === 0 ? (
          <p className="table-null">No review runs recorded yet.</p>
        ) : (
          <div className="runs-list">
            {items.map((run) => (
              <RunRow
                key={run.review_run_id}
                run={run}
                active={run.review_run_id === activeId}
                onSelect={() => setSelectedId(run.review_run_id)}
              />
            ))}
          </div>
        )}
      </aside>
      <div className="runs-detail">
        {showingError ? (
          <div className="panel panel-error" role="alert">
            <p>Unable to load this run.</p>
            <span>{showingError}</span>
          </div>
        ) : showing ? (
          <TraceDetailPanel trace={showing} />
        ) : loadingDetail ? (
          <div className="trace-loading">
            <p>Loading spans…</p>
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<GitPullRequest size={40} />}
            title="No review runs yet"
            body="Each reviewed pull request appears here as a trace you can expand into its ordered LLM and tool calls."
          />
        ) : (
          <EmptyState
            icon={<Activity size={40} />}
            title="Select a run"
            body="Choose a review run from the list to inspect its spans end to end."
          />
        )}
      </div>
      </div>
    </div>
  );
}

function RunRow({
  run,
  active,
  onSelect,
}: {
  run: TraceSummary;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`queue-item run-item ${active ? "selected" : ""}`}
      onClick={onSelect}
      aria-pressed={active}
    >
      <div className="queue-item-top">
        <span className="repo-avatar">{run.repository.slice(0, 1).toUpperCase()}</span>
        <div className="queue-item-name">
          <p>{run.repository}</p>
          <span>PR #{run.pr_number}</span>
        </div>
        <span className={`run-state ${run.status}`} />
      </div>
      <div className="run-meta">
        <span>{formatDuration(run.duration_seconds)}</span>
        <span>{run.span_count} spans</span>
        <span>{formatMoney(run.total_cost_usd)}</span>
      </div>
      <div className="run-stamp">{formatDateTime(run.completed_at)}</div>
    </button>
  );
}

function TraceDetailPanel({ trace }: { trace: TraceDetail }) {
  const models = [...new Set(trace.spans.map((span) => span.model).filter(Boolean))];
  return (
    <section className="review-detail runs-detail-panel" aria-label="Trace detail">
      <div className="detail-header">
        <div>
          <p className="repo-label">{trace.repository}</p>
          <h3>Pull request #{trace.pr_number}</h3>
          <p className="sha">
            {trace.review_run_id} · {trace.head_sha.slice(0, 8)}
          </p>
        </div>
        <StatusPill tone={trace.status === "failed" ? "error" : "ok"}>
          {trace.status}
        </StatusPill>
      </div>
      <div className="trace-summary">
        <SummaryCell label="Started" value={formatDateTime(trace.started_at)} />
        <SummaryCell label="Duration" value={formatDuration(trace.duration_seconds)} />
        <SummaryCell label="Cost" value={formatMoney(trace.total_cost_usd)} />
        <SummaryCell label="Spans" value={trace.span_count.toString()} />
        <SummaryCell label="Models" value={models.join(", ") || "—"} />
      </div>
      <PanelHeading title="Span timeline" meta="Ordered end to end" />
      <div className="span-list">
        {trace.spans.map((span) => (
          <SpanRow span={span} key={span.id} />
        ))}
      </div>
    </section>
  );
}

function SummaryCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-cell">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SpanRow({ span }: { span: Span }) {
  const failed = span.status === "failed";
  return (
    <article className={`span-row ${failed ? "failed" : ""}`}>
      <div className="span-head">
        <span className="span-rail" aria-hidden="true" />
        <span className="span-agent">{titleCase(span.agent)}</span>
        <span className="span-phase mono">{span.phase}</span>
        <span className="span-type mono">{span.span_type}</span>
        {span.model && <span className="span-model mono">{span.model}</span>}
        <span className="span-cost mono">{formatMoney(span.cost_usd)}</span>
        <span className="span-latency mono">{span.latency_ms.toLocaleString()}ms</span>
        <span className="span-time mono">{formatDateTime(span.created_at)}</span>
      </div>
      <div className="span-tokens mono">
        {span.tokens_in} in · {span.tokens_out} out
      </div>
      {failed && span.error_message && (
        <div className="span-error" role="alert">
          {span.error_message}
        </div>
      )}
      <div className="span-bodies">
        {span.input_summary && (
          <div className="span-summ">
            <span>In</span>
            <pre>{span.input_summary}</pre>
          </div>
        )}
        {span.output_summary && (
          <div className="span-summ">
            <span>Out</span>
            <pre>{span.output_summary}</pre>
          </div>
        )}
      </div>
    </article>
  );
}