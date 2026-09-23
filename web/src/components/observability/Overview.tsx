import { useEffect } from "react";
import {
  EmptyState,
  Metric,
  PageHeading,
  PanelHeading,
  SkeletonPanel,
  StatusPill,
} from "../ui/DashboardChrome";
import { getOverview } from "../../lib/api";
import { GitPullRequest, CircleDollarSign, Inbox, TrendingUp } from "../../lib/icons";
import {
  formatAgeMinutes,
  formatDay,
  formatMoney,
  formatPercent,
  titleCase,
} from "../../lib/format";
import { useSurface } from "../../hooks/use-surface";
import type { OverviewMetrics, ReviewsPerDay } from "../../types";

const TH =
  "border-y border-line bg-canvas/40 px-[18px] py-2.5 text-left font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-faint whitespace-nowrap";
const TH_NUM =
  "border-y border-line bg-canvas/40 px-[18px] py-2.5 text-right font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-faint whitespace-nowrap tabular-nums";
const TD = "border-b border-line px-[18px] py-3 text-[12.5px] text-ink whitespace-nowrap";
const TD_NUM =
  "border-b border-line px-[18px] py-3 text-right font-mono text-[12px] text-ink whitespace-nowrap tabular-nums";

export function Overview({
  onLiveChange,
}: {
  onLiveChange: (live: boolean) => void;
}) {
  const surface = useSurface<OverviewMetrics>(() => getOverview(14));
  const { data, error, loading, reload } = surface;
  useEffect(() => {
    onLiveChange(error === null);
  }, [error, onLiveChange]);

  const hasFailures =
    (data?.latency_by_phase.reduce((sum, row) => sum + row.failures, 0) ?? 0) > 0;
  const aside =
    error !== null ? (
      <StatusPill tone="error">Connection failed</StatusPill>
    ) : hasFailures ? (
      <StatusPill tone="warn">Phase failures recorded</StatusPill>
    ) : (
      <StatusPill tone="ok">
        {data
          ? `${data.total_reviews} reviews · ${data.window_days}-day window`
          : "Syncing…"}
      </StatusPill>
    );

  useEffect(() => {
    const onRefresh = () => reload();
    window.addEventListener("perchly:refresh", onRefresh);
    return () => window.removeEventListener("perchly:refresh", onRefresh);
  }, [reload]);

  if (loading && !data) {
    return (
      <div className="grid">
        <PageHeading
          title="Review at a glance"
          description="Volume, cost, latency, and acceptance across the last 14 days."
          aside={aside}
        />
        <div className="mb-[30px] grid grid-cols-4 gap-2.5 max-[1020px]:grid-cols-2">
          {Array.from({ length: 4 }, (_, index) => (
            <div
              className="min-h-[122px] animate-pulse rounded-lg border border-line bg-panel-2 motion-reduce:animate-none"
              key={index}
            />
          ))}
        </div>
        <SkeletonPanel rows={6} />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="grid">
        <PageHeading
          title="Review at a glance"
          description="Volume, cost, latency, and acceptance across the last 14 days."
          aside={aside}
        />
        <PanelError message={error} />
      </div>
    );
  }

  const overview = data as OverviewMetrics;
  const acceptance = overview.acceptance_rate_by_category;
  const acceptedTotal = acceptance.reduce((sum, row) => sum + row.accepted, 0);
  const findingsTotal = acceptance.reduce((sum, row) => sum + row.total, 0);
  const overallRate = findingsTotal ? acceptedTotal / findingsTotal : 0;

  return (
    <div className="grid">
      <PageHeading
        title="Review at a glance"
        description="Volume, cost, latency, and acceptance across the last 14 days."
        aside={aside}
      />
      <div className="mb-[30px] grid grid-cols-4 gap-2.5 max-[1020px]:grid-cols-2">
        <Metric
          icon={<GitPullRequest size={16} />}
          label="Reviews in window"
          value={overview.total_reviews.toString().padStart(2, "0")}
          detail={`last ${overview.window_days} days`}
          accent="lime"
        />
        <Metric
          icon={<CircleDollarSign size={16} />}
          label="Cost per review"
          value={formatMoney(overview.cost.cost_per_review_usd)}
          detail={`7d total ${formatMoney(overview.cost.total_cost_usd_7d)}`}
          accent="cyan"
        />
        <Metric
          icon={<Inbox size={16} />}
          label="HITL queue"
          value={overview.hitl_queue.depth.toString().padStart(2, "0")}
          detail={`${formatAgeMinutes(overview.hitl_queue.median_age_minutes)} median`}
          accent="orange"
        />
        <Metric
          icon={<TrendingUp size={16} />}
          label="Acceptance"
          value={formatPercent(overview.total_reviews ? overallRate : 0)}
          detail={
            findingsTotal
              ? `${acceptedTotal}/${findingsTotal} findings accepted`
              : "no decisions recorded"
          }
          accent="violet"
        />
      </div>

      {overview.total_reviews === 0 ? (
        <EmptyState
          icon={<GitPullRequest size={40} />}
          title="No telemetry yet"
          body="The overview fills in after the first PR is reviewed. Open a pull request with the Perchly app installed and this dashboard will report volume, cost, latency, and acceptance."
        />
      ) : (
        <div className="grid grid-cols-2 items-start gap-3.5 max-[900px]:grid-cols-1">
          <section
            className="col-span-2 overflow-hidden rounded-lg border border-line bg-panel max-[900px]:col-span-1"
            aria-label="Review volume"
          >
            <PanelHeading
              title="Review volume"
              meta="Distinct reviews started per day"
            />
            <VolumeChart points={overview.reviews_per_day} />
          </section>

          <section
            className="overflow-hidden rounded-lg border border-line bg-panel"
            aria-label="Latency by phase"
          >
            <PanelHeading
              title="Latency by phase"
              meta="p50 / p95 across spans, last 7 days"
            />
            <LatencyTable rows={overview.latency_by_phase} />
          </section>

          <section
            className="overflow-hidden rounded-lg border border-line bg-panel"
            aria-label="Acceptance by category"
          >
            <PanelHeading
              title="Acceptance by category"
              meta="How often each domain passes the bar"
            />
            <AcceptanceTable rows={overview.acceptance_rate_by_category} />
          </section>

          <section
            className="overflow-hidden rounded-lg border border-line bg-panel"
            aria-label="Learning outcomes"
          >
            <PanelHeading
              title="Learning outcomes"
              meta="Finding outcomes used for future calibration"
            />
            <LearningOutcomeTable rows={overview.learning_outcomes} />
          </section>
        </div>
      )}
    </div>
  );
}

function PanelError({ message }: { message: string }) {
  return (
    <div
      className="grid justify-items-center gap-[5px] rounded-lg border border-line bg-panel p-[26px] text-center"
      role="alert"
    >
      <p className="m-0 text-[14px] font-bold text-red">Unable to load the overview.</p>
      <span className="text-[12.5px] text-muted">{message}</span>
    </div>
  );
}

function VolumeChart({ points }: { points: ReviewsPerDay[] }) {
  const width = 680;
  const height = 170;
  const top = 14;
  const bottom = 44;
  const max = Math.max(1, ...points.map((point) => point.reviews));
  const n = Math.max(points.length, 1);
  const slot = width / n;
  const barWidth = Math.min(Math.max(8, slot * 0.6), 56);
  const labelEvery = Math.max(1, Math.ceil(n / 7));

  return (
    <div className="px-[18px] pt-1 pb-2.5">
      <svg
        className="block h-auto w-full"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Reviews started per day"
      >
        <title>Reviews per day</title>
        {points.map((point, index) => {
          const barHeight = Math.max(2, (point.reviews / max) * (height - top - bottom));
          const x = index * slot + (slot - barWidth) / 2;
          const y = height - bottom - barHeight;
          const label = index % labelEvery === 0 || index === n - 1;
          return (
            <g key={point.day}>
              <rect
                className="fill-lime/50 transition-[fill] duration-[160ms] hover:fill-lime"
                x={x}
                y={y}
                width={barWidth}
                height={barHeight}
                rx={2}
              >
                <title>
                  {formatDay(point.day)} — {point.reviews}{" "}
                  {point.reviews === 1 ? "review" : "reviews"}
                </title>
              </rect>
              {point.reviews > 0 && max > 1 && (
                <text
                  className="fill-muted font-mono text-[10px] tabular-nums"
                  x={x + barWidth / 2}
                  y={y - 5}
                  textAnchor="middle"
                >
                  {point.reviews}
                </text>
              )}
              {label && (
                <text
                  className="fill-faint font-mono text-[9.5px]"
                  x={x + barWidth / 2}
                  y={height - 16}
                  textAnchor="middle"
                >
                  {formatDay(point.day)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function LatencyTable({ rows }: { rows: OverviewMetrics["latency_by_phase"] }) {
  if (rows.length === 0) {
    return <p className="m-0 p-6 text-center text-[12.5px] leading-[1.6] text-faint">No phase spans recorded in this window.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            <th className={TH}>Phase</th>
            <th className={TH_NUM}>Spans</th>
            <th className={TH_NUM}>p50</th>
            <th className={TH_NUM}>p95</th>
            <th className={TH_NUM}>Failures</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.phase} className="transition hover:bg-panel-2/55">
              <td className={`${TD} font-mono text-[11.5px] text-cyan`}>{row.phase}</td>
              <td className={TD_NUM}>{row.spans}</td>
              <td className={TD_NUM}>{row.p50_ms.toLocaleString()}ms</td>
              <td className={TD_NUM}>{row.p95_ms.toLocaleString()}ms</td>
              <td className={TD_NUM}>
                {row.failures > 0 ? (
                  <span className="font-semibold text-red">{row.failures}</span>
                ) : (
                  <span className="text-faint">0</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AcceptanceTable({
  rows,
}: {
  rows: OverviewMetrics["acceptance_rate_by_category"];
}) {
  if (rows.length === 0) {
    return <p className="m-0 p-6 text-center text-[12.5px] leading-[1.6] text-faint">No review decisions recorded yet.</p>;
  }
  return (
    <div className="grid gap-1 px-[18px] pt-3 pb-[18px]">
      {rows.map((row) => (
        <div key={row.category} className="grid gap-[7px] border-b border-line/60 py-[11px] last:border-b-0">
          <div className="flex items-baseline justify-between gap-2.5">
            <span className="font-mono tabular-nums text-ink">{titleCase(row.category)}</span>
            <span className="font-mono text-[10.5px] tabular-nums text-faint">
              {row.accepted}/{row.total} · {formatPercent(row.acceptance_rate)}
            </span>
          </div>
          <div
            className="h-[5px] overflow-hidden rounded-full border border-line bg-panel-2"
            aria-hidden="true"
          >
            <span
              className="block h-full min-w-0.5 rounded-full bg-lime"
              style={{ width: `${Math.min(100, row.acceptance_rate * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function LearningOutcomeTable({
  rows,
}: {
  rows: OverviewMetrics["learning_outcomes"];
}) {
  if (rows.length === 0) {
    return <p className="m-0 p-6 text-center text-[12.5px] leading-[1.6] text-faint">No learning outcomes recorded yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            <th className={TH}>Outcome</th>
            <th className={TH_NUM}>Findings</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.outcome} className="transition hover:bg-panel-2/55">
              <td className={`${TD} font-mono text-[11.5px] text-cyan`}>{titleCase(row.outcome)}</td>
              <td className={TD_NUM}>{row.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
