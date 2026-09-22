import type { ReactNode } from "react";
import type { MetricCardProps, RouteKey } from "../../types";
import {
  Activity,
  Gauge,
  Inbox,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
} from "../../lib/icons";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="brand">
      <span className="brand-mark" aria-hidden="true">
        P
      </span>
      {!compact && <strong>Perchly</strong>}
    </span>
  );
}

const NAV: { label: string; href: Record<RouteKey, string>; items: readonly { key: RouteKey; label: string; icon: ReactNode }[] }[] = [
  {
    label: "Workspace",
    href: { queue: "#queue", overview: "#overview", runs: "#runs" },
    items: [
      { key: "queue", label: "Approval queue", icon: <Inbox size={17} /> },
    ],
  },
  {
    label: "Observability",
    href: { queue: "#queue", overview: "#overview", runs: "#runs" },
    items: [
      { key: "overview", label: "Overview", icon: <Gauge size={17} /> },
      { key: "runs", label: "Review runs", icon: <Activity size={17} /> },
    ],
  },
];

export function Sidebar({
  route,
  queueCount,
  live,
  onNavigate,
}: {
  route: RouteKey;
  queueCount: number;
  live: boolean;
  onNavigate: (route: RouteKey) => void;
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <Brand />
        <span className="workspace-sub">acme / platform</span>
      </div>
      <nav className="nav-group-list" aria-label="Primary navigation">
        {NAV.map((group) => (
          <div className="nav-group" key={group.label}>
            <p>{group.label}</p>
            {group.items.map((item) => (
              <a
                key={item.key}
                className={`nav-item ${route === item.key ? "active" : ""}`}
                href={group.href[item.key]}
                onClick={(event) => {
                  event.preventDefault();
                  onNavigate(item.key);
                }}
                aria-current={route === item.key ? "page" : undefined}
              >
                {item.icon}
                <span>{item.label}</span>
                {item.key === "queue" && <b>{queueCount.toString().padStart(2, "0")}</b>}
              </a>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="avatar">K</div>
        <div className="sidebar-persona">
          <strong>Kolay</strong>
          <span>Maintainer</span>
        </div>
        <span className={`status-dot ${live ? "" : "offline"}`} />
      </div>
    </aside>
  );
}

export function Header({
  refreshing,
  live,
  label,
  onRefresh,
}: {
  refreshing: boolean;
  live: boolean;
  label: string;
  onRefresh: () => void;
}) {
  return (
    <header className="topbar">
      <div className="mobile-brand">
        <Brand />
      </div>
      <span className="topbar-surface">{label}</span>
      <div className="topbar-actions">
        <span className={`live-indicator ${live ? "" : "offline"}`}>
          <span /> {live ? "Live" : "Offline"}
        </span>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="icon-button"
          aria-label="Refresh current view"
          title="Refresh current view"
        >
          <RefreshCw size={17} className={refreshing ? "spin" : ""} />
        </button>
        <div className="topbar-avatar">K</div>
      </div>
    </header>
  );
}

export function PageHeading({
  title,
  description,
  aside,
}: {
  title: string;
  description: string;
  aside?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {aside && <div className="page-aside">{aside}</div>}
    </div>
  );
}

export function StatusPill({
  tone,
  children,
}: {
  tone: "ok" | "warn" | "error" | "idle";
  children: ReactNode;
}) {
  return (
    <span className={`status-pill ${tone}`}>
      <span className="status-dot" />
      {children}
    </span>
  );
}

export function Metric({ icon, label, value, detail, accent }: MetricCardProps) {
  return (
    <div className={`metric-card accent-${accent}`}>
      <div className="metric-icon">{icon}</div>
      <div className="metric-copy">
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

export function SectionLabel({
  label,
  count,
  hint,
}: {
  label: string;
  count?: number;
  hint?: string;
}) {
  return (
    <div className="section-label" role="heading" aria-level={3}>
      <span>{label}</span>
      <span className="section-line" />
      {hint && <span className="section-hint">{hint}</span>}
      {count !== undefined && <span className="section-count">{count} open</span>}
    </div>
  );
}

export function ErrorBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  return (
    <div className="error-banner" role="alert">
      <TriangleAlert className="shrink-0" size={17} />
      <p>{message}</p>
      <button type="button" onClick={onDismiss} aria-label="Dismiss error">
        ×
      </button>
    </div>
  );
}

export function SkeletonPanel({ rows = 4 }: { rows?: number }) {
  return (
    <div className="skeleton-list" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <span className="skeleton-row" key={index} />
      ))}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  body,
}: {
  icon: ReactNode;
  title: string;
  body: string;
}) {
  return (
    <section className="empty-state">
      <div>
        <span className="empty-icon">{icon}</span>
        <h3>{title}</h3>
        <p>{body}</p>
      </div>
    </section>
  );
}

export function PanelHeading({
  title,
  meta,
  actions,
}: {
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="panel-heading">
      <div>
        <h3>{title}</h3>
        {meta && <p>{meta}</p>}
      </div>
      {actions}
    </div>
  );
}

export function NoTelemetry({
  tone,
}: {
  tone: "ok" | "warn" | "error";
}) {
  return (
    <span className={`no-telemetry ${tone}`}>
      <ShieldCheck size={13} />
      No telemetry recorded in this window
    </span>
  );
}