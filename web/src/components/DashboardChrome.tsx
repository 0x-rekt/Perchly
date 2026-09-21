import {
  Activity,
  ChevronRight,
  Inbox,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
} from "../icons";
import type { MetricCardProps } from "../types";

export function Metric({
  icon,
  label,
  value,
  detail,
  accent,
}: MetricCardProps) {
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

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="workspace-switcher">
        <div className="workspace-mark">P</div>
        <div>
          <strong>Perchly</strong>
          <span>acme / platform</span>
        </div>
        <ChevronRight size={15} />
      </div>
      <nav className="nav-group" aria-label="Primary navigation">
        <p>Workspace</p>
        <a className="nav-item active" href="#queue">
          <Inbox size={17} /> Approval queue <b>04</b>
        </a>
        <a className="nav-item" href="#reviews">
          <Activity size={17} /> Review runs
        </a>
        <a className="nav-item" href="#findings">
          <ShieldCheck size={17} /> Findings
        </a>
        <a className="nav-item" href="#traces">
          <TerminalSquare size={17} /> Traces
        </a>
      </nav>
      <nav className="nav-group lower-nav" aria-label="Secondary navigation">
        <p>System</p>
        <a className="nav-item" href="#agents">
          <Sparkles size={17} /> Agent health
        </a>
        <a className="nav-item" href="#settings">
          <Activity size={17} /> Settings
        </a>
      </nav>
      <div className="sidebar-footer">
        <div className="avatar">K</div>
        <div>
          <strong>Kolay</strong>
          <span>Maintainer</span>
        </div>
        <span className="online-dot" />
      </div>
    </aside>
  );
}

export function Header({
  refreshing,
  onRefresh,
}: {
  refreshing: boolean;
  onRefresh: () => void;
}) {
  return (
    <header className="topbar">
      <div className="mobile-brand">
        <div className="workspace-mark">P</div>
        <strong>Perchly</strong>
      </div>
      <div className="topbar-search">
        <Search size={16} />
        <span>Search reviews, repos, traces</span>
        <kbd>Ctrl K</kbd>
      </div>
      <div className="topbar-actions">
        <span className="live-indicator">
          <span /> Live
        </span>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="icon-button"
          aria-label="Refresh queue"
        >
          <RefreshCw size={17} className={refreshing ? "spin" : ""} />
        </button>
        <div className="topbar-avatar">K</div>
      </div>
    </header>
  );
}

export function PageHeading() {
  return (
    <div className="page-heading">
      <div>
        <div className="breadcrumb">
          <span className="status-dot" /> Review operations <span>/</span> Human
          approval
        </div>
        <h2>Approval queue</h2>
        <p>Resolve low-confidence findings before they reach GitHub.</p>
      </div>
      <div className="system-state">
        <span className="pulse-ring" /> All systems nominal{" "}
        <span className="state-time">updated just now</span>
      </div>
    </div>
  );
}

export function SectionLabel({ count }: { count: number }) {
  return (
    <div className="section-label">
      <span>Needs your attention</span>
      <span className="section-line" />
      <span className="section-count">{count} open</span>
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
    <div className="error-banner">
      <Activity className="shrink-0" size={17} />
      <p>{message}</p>
      <button type="button" onClick={onDismiss} aria-label="Dismiss error">
        ×
      </button>
    </div>
  );
}

export function Loading() {
  return (
    <div className="loading-state">
      <div className="text-center">
        <RefreshCw className="spin loading-icon" size={28} />
        <p>Loading review queue...</p>
      </div>
    </div>
  );
}

export function Empty({ hasItems }: { hasItems: boolean }) {
  return (
    <section className="empty-state">
      <div>
        <TerminalSquare className="empty-icon" size={42} />
        <h3>{hasItems ? "Select a review" : "No pending reviews"}</h3>
        <p>
          {hasItems
            ? "Choose a pull request from the queue to inspect its findings."
            : "New approval requests will appear here."}
        </p>
      </div>
    </section>
  );
}
