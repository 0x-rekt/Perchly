import { useEffect } from "react";
import {
  EmptyState,
  Metric,
  NoTelemetry,
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
      <div className="overview">
        <PageHeading
          title="Review at a glance"
          description="Volume, cost, latency, and acceptance across the last 14 days."
          aside={aside}
        />
        <div className="metrics-row">
          {Array.from({ length: 4 }, (_, index) => (
            <div className="metric-card skeleton" key={index} />
          ))}
        </div>
        <SkeletonPanel rows={6} />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="overview">
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
    <div className="overview">
      <PageHeading
        title="Review at a glance"
        description="Volume, cost, latency, and acceptance across the last 14 days."
        aside={aside}
      />
      <div className="metrics-row">
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
        <div className="overview-grid">
          <section className="panel volume-panel" aria-label="Review volume">
            <PanelHeading
              title="Review volume"
              meta="Distinct reviews started per day"
              actions={<NoTelemetry tone="ok" />}
            />
            <VolumeChart points={overview.reviews_per_day} />
          </section>

          <section className="panel table-panel" aria-label="Latency by phase">
            <PanelHeading
              title="Latency by phase"
              meta="p50 / p95 across spans, last 7 days"
            />
            <LatencyTable rows={overview.latency_by_phase} />
          </section>

          <section className="panel table-panel" aria-label="Acceptance by category">
            <PanelHeading
              title="Acceptance by category"
              meta="How often each domain passes the bar"
            />
            <AcceptanceTable rows={overview.acceptance_rate_by_category} />
          </section>

          <section className="panel table-panel" aria-label="Learning outcomes">
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
    <div className="panel panel-error" role="alert">
      <p>Unable to load the overview.</p>
      <span>{message}</span>
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
  const barWidth = Math.max(8, slot * 0.6);
  const labelEvery = Math.max(1, Math.ceil(n / 7));

  return (
    <div className="volume-chart">
      <svg
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
                className="chart-bar"
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
                  className="chart-value"
                  x={x + barWidth / 2}
                  y={y - 5}
                  textAnchor="middle"
                >
                  {point.reviews}
                </text>
              )}
              {label && (
                <text
                  className="chart-label"
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
    return <p className="table-null">No phase spans recorded in this window.</p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Phase</th>
            <th className="num">Spans</th>
            <th className="num">p50</th>
            <th className="num">p95</th>
            <th className="num">Failures</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.phase}>
              <td className="mono">{row.phase}</td>
              <td className="num">{row.spans}</td>
              <td className="num">{row.p50_ms.toLocaleString()}ms</td>
              <td className="num">{row.p95_ms.toLocaleString()}ms</td>
              <td className="num">
                {row.failures > 0 ? (
                  <span className="cell-fail">{row.failures}</span>
                ) : (
                  <span className="cell-clean">0</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AcceptanceTable({ rows }: { rows: OverviewMetrics["acceptance_rate_by_category"] }) {
  if (rows.length === 0) {
    return <p className="table-null">No review decisions recorded yet.</p>;
  }
  return (
    <div className="acceptance-list">
      {rows.map((row) => (
        <div className="acceptance-row" key={row.category}>
          <div className="acceptance-top">
            <span className="mono">{titleCase(row.category)}</span>
            <span className="acceptance-meta">
              {row.accepted}/{row.total} · {formatPercent(row.acceptance_rate)}
            </span>
          </div>
          <div className="rate-track" aria-hidden="true">
            <span
              className="rate-fill"
              style={{ width: `${Math.min(100, row.acceptance_rate * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function LearningOutcomeTable({ rows }: { rows: OverviewMetrics["learning_outcomes"] }) {
  if (rows.length === 0) {
    return <p className="table-null">No learning outcomes recorded yet.</p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Outcome</th>
            <th className="num">Findings</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.outcome}>
              <td className="mono">{titleCase(row.outcome)}</td>
              <td className="num">{row.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
