import { useCallback, useEffect, useRef, useState } from "react";
import {
  EmptyState,
  PageHeading,
  PanelHeading,
  SkeletonPanel,
  StatusPill,
} from "../ui/DashboardChrome";
import { getTrace, getTraces, type TraceFilters } from "../../lib/api";
import { Activity, GitPullRequest } from "../../lib/icons";
import {
  formatDateTime,
  formatDuration,
  formatMoney,
  titleCase,
} from "../../lib/format";
import { useSurface } from "../../hooks/use-surface";
import type { Span, TraceDetail, TraceSummary, TracesResponse } from "../../types";

const FILTER_INPUT =
  "min-h-8 w-full rounded-md border border-line bg-canvas px-2 py-1.5 text-[12px] text-ink placeholder:text-faint caret-lime outline-none transition focus:border-lime focus:shadow-[0_0_0_3px_rgba(201,243,107,0.12)]";

export function ReviewRuns({
  onLiveChange,
}: {
  onLiveChange: (live: boolean) => void;
}) {
  const [draftFilters, setDraftFilters] = useState<TraceFilters>({});
  const [filters, setFilters] = useState<TraceFilters>({});
  const firstFilterRender = useRef(true);
  const loadTraces = useCallback(() => getTraces(filters), [filters]);
  const surface = useSurface<TracesResponse>(loadTraces);
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
    if (firstFilterRender.current) {
      firstFilterRender.current = false;
      return;
    }
    reload();
  }, [filters, reload]);

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
    <div className="grid">
      <PageHeading
        title="Review runs"
        description="Every reviewed pull request, expandable to its ordered spans."
        aside={aside}
      />
      <div className="grid grid-cols-[320px_minmax(0,1fr)] items-start gap-3.5 max-[900px]:grid-cols-1">
        <aside
          className="overflow-hidden rounded-lg border border-line bg-panel"
          aria-label="Review runs"
        >
          <PanelHeading title="Review runs" meta="Newest first" />
          <form
            className="grid gap-2 border-b border-line p-3"
            onSubmit={(event) => {
              event.preventDefault();
              setFilters({
                repository: draftFilters.repository?.trim() || undefined,
                agent: draftFilters.agent?.trim() || undefined,
                prNumber: draftFilters.prNumber || undefined,
                headSha: draftFilters.headSha?.trim() || undefined,
              });
            }}
          >
            <input
              aria-label="Repository"
              placeholder="owner/repository"
              className={FILTER_INPUT}
              value={draftFilters.repository ?? ""}
              onChange={(event) => setDraftFilters({ ...draftFilters, repository: event.target.value })}
            />
            <input
              aria-label="PR number"
              placeholder="PR number"
              type="number"
              min="1"
              className={FILTER_INPUT}
              value={draftFilters.prNumber ?? ""}
              onChange={(event) => setDraftFilters({ ...draftFilters, prNumber: event.target.value ? Number(event.target.value) : undefined })}
            />
            <input
              aria-label="Agent"
              placeholder="agent (security)"
              className={FILTER_INPUT}
              value={draftFilters.agent ?? ""}
              onChange={(event) => setDraftFilters({ ...draftFilters, agent: event.target.value })}
            />
            <input
              aria-label="Head SHA"
              placeholder="head SHA"
              className={FILTER_INPUT}
              value={draftFilters.headSha ?? ""}
              onChange={(event) => setDraftFilters({ ...draftFilters, headSha: event.target.value })}
            />
            <div className="grid grid-cols-2 gap-2">
              <button
                type="submit"
                className="min-h-8 rounded-md border border-lime bg-lime px-2 py-1 text-[12px] font-bold text-[#11170f] transition hover:bg-[#dbff87] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
              >
                Apply filters
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraftFilters({});
                  setFilters({});
                }}
                className="min-h-8 rounded-md border border-line bg-transparent px-2 py-1 text-[12px] font-bold text-muted transition hover:border-line-strong hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
              >
                Clear
              </button>
            </div>
          </form>
          {loading && !data ? (
            <SkeletonPanel rows={6} />
          ) : error && !data ? (
            <div className="p-3.5 text-[12.5px] text-red" role="alert">
              {error}
            </div>
          ) : items.length === 0 ? (
            <p className="m-0 p-6 text-center text-[12.5px] leading-[1.6] text-faint">
              No review runs recorded yet.
            </p>
          ) : (
            <div className="p-2">
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
        <div className="grid min-w-0 gap-3.5">
          {showingError ? (
            <div
              className="grid justify-items-center gap-[5px] rounded-lg border border-line bg-panel p-[26px] text-center"
              role="alert"
            >
              <p className="m-0 text-[14px] font-bold text-red">Unable to load this run.</p>
              <span className="text-[12.5px] text-muted">{showingError}</span>
            </div>
          ) : error && !data ? (
            <div
              className="grid justify-items-center gap-[5px] rounded-lg border border-line bg-panel p-[26px] text-center"
              role="alert"
            >
              <p className="m-0 text-[14px] font-bold text-red">Unable to load review runs.</p>
              <span className="text-[12.5px] text-muted">{error}</span>
            </div>
          ) : showing ? (
            <TraceDetailPanel trace={showing} />
          ) : loadingDetail ? (
            <div className="grid min-h-[220px] place-items-center rounded-lg border border-line bg-panel">
              <p className="font-mono text-[12px] text-faint">Loading spans…</p>
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
      className={`mb-[3px] block w-full rounded-lg border px-3 py-[13px] text-left transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime ${
        active
          ? "border-[#2f4730] bg-lime-soft"
          : "border-transparent hover:bg-panel-2"
      }`}
      onClick={onSelect}
      aria-pressed={active}
    >
      <div className="flex items-center gap-2.5">
        <span className="grid size-[26px] shrink-0 place-items-center rounded-[7px] bg-[#293d34] text-[11px] font-bold text-cyan">
          {run.repository.slice(0, 1).toUpperCase()}
        </span>
        <div className="grid min-w-0 gap-0.5">
          <p className="truncate text-[12px] font-semibold text-ink">{run.repository}</p>
          <span className="font-mono text-[10px] text-faint">PR #{run.pr_number}</span>
        </div>
        <span
          className={
            run.status === "failed"
              ? "ml-auto size-[7px] shrink-0 rounded-full bg-red shadow-[0_0_8px_rgba(255,143,145,0.45)]"
              : "ml-auto size-[7px] shrink-0 rounded-full bg-lime shadow-[0_0_8px_rgba(201,243,107,0.55)]"
          }
        />
      </div>
      <div className="mt-2.5 mb-2 flex gap-2.5 font-mono text-[10.5px] tabular-nums text-muted">
        <span>{formatDuration(run.duration_seconds)}</span>
        <span>{run.span_count} spans</span>
        <span>{formatMoney(run.total_cost_usd)}</span>
      </div>
      <div className="font-mono text-[10px] text-faint">{formatDateTime(run.completed_at)}</div>
    </button>
  );
}

function TraceDetailPanel({ trace }: { trace: TraceDetail }) {
  const models = [...new Set(trace.spans.map((span) => span.model).filter(Boolean))];
  return (
    <section
      className="min-w-0 overflow-hidden rounded-lg border border-line bg-panel"
      aria-label="Trace detail"
    >
      <div className="flex items-start justify-between gap-5 border-b border-line px-6 pt-[22px] pb-[18px] max-[520px]:flex-col max-[520px]:px-[18px] max-[520px]:py-[18px]">
        <div>
          <p className="mb-2 font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-lime">
            {trace.repository}
          </p>
          <h3 className="text-[21px] font-extrabold tracking-[-0.03em] text-ink">
            Pull request #{trace.pr_number}
          </h3>
          <p className="mt-[9px] font-mono text-[10.5px] text-faint">
            {trace.review_run_id} · {trace.head_sha.slice(0, 8)}
          </p>
        </div>
        <StatusPill tone={trace.status === "failed" ? "error" : "ok"}>
          {trace.status}
        </StatusPill>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2.5 border-b border-line px-6 py-4 max-[520px]:px-[18px]">
        <SummaryCell label="Started" value={formatDateTime(trace.started_at)} />
        <SummaryCell label="Duration" value={formatDuration(trace.duration_seconds)} />
        <SummaryCell label="Cost" value={formatMoney(trace.total_cost_usd)} />
        <SummaryCell label="Spans" value={trace.span_count.toString()} />
        <SummaryCell label="Models" value={models.join(", ") || "—"} />
      </div>
      <PanelHeading title="Span timeline" meta="Ordered end to end" className="border-t-0 pt-3" />
      <div className="grid gap-2 px-6 pt-0 pb-6 max-[520px]:px-[18px]">
        {trace.spans.map((span) => (
          <SpanRow span={span} key={span.id} />
        ))}
      </div>
    </section>
  );
}

function SummaryCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid min-w-0 gap-1">
      <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-faint">
        {label}
      </span>
      <strong className="truncate text-[13.5px] font-bold tabular-nums text-ink">{value}</strong>
    </div>
  );
}

function SpanRow({ span }: { span: Span }) {
  const failed = span.status === "failed";
  return (
    <article
      className={`grid gap-2 rounded-md border p-3.5 ${
        failed ? "border-red-line bg-[#241516]" : "border-line bg-[#141a17]"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2.5 text-[11.5px]">
        <span
          className={`h-3.5 w-[3px] shrink-0 rounded-sm ${failed ? "bg-red" : "bg-cyan"}`}
          aria-hidden="true"
        />
        <span className="font-bold text-ink">{titleCase(span.agent)}</span>
        <span className="font-mono text-[10.5px] text-faint">{span.phase}</span>
        <span className="font-mono text-[10.5px] text-faint">{span.span_type}</span>
        {span.model && (
          <span className="font-mono text-[10.5px] text-faint">{span.model}</span>
        )}
        <span className="ml-auto font-mono text-[10.5px] tabular-nums text-faint">
          {formatMoney(span.cost_usd)}
        </span>
        <span className="font-mono text-[10.5px] tabular-nums text-faint">
          {span.latency_ms.toLocaleString()}ms
        </span>
        <span className="font-mono text-[10.5px] tabular-nums text-faint">
          {formatDateTime(span.created_at)}
        </span>
      </div>
      <div className="font-mono text-[10.5px] text-muted">
        {span.tokens_in} in · {span.tokens_out} out
      </div>
      {failed && span.error_message && (
        <div
          className="rounded-[5px] border border-dashed border-red-line bg-red-soft px-[11px] py-[9px] text-[12px] leading-[1.55] text-red"
          role="alert"
        >
          {span.error_message}
        </div>
      )}
      <div className="grid gap-2.5">
        {span.input_summary && (
          <div className="grid gap-[5px]">
            <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-faint">
              In
            </span>
            <pre className="m-0 max-h-[180px] overflow-auto rounded-[5px] border border-line bg-[#0c100e] p-3 font-mono text-[11px] leading-[1.6] break-words whitespace-pre-wrap text-muted">
              {span.input_summary}
            </pre>
          </div>
        )}
        {span.output_summary && (
          <div className="grid gap-[5px]">
            <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-faint">
              Out
            </span>
            <pre className="m-0 max-h-[180px] overflow-auto rounded-[5px] border border-line bg-[#0c100e] p-3 font-mono text-[11px] leading-[1.6] break-words whitespace-pre-wrap text-muted">
              {span.output_summary}
            </pre>
          </div>
        )}
      </div>
    </article>
  );
}
