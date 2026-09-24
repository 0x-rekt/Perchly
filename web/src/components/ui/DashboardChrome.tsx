import type { ReactNode } from "react";
import type { AuthUser, MetricCardProps, RouteKey } from "../../types";
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
    <span className="inline-flex items-center gap-2.5 text-ink">
      <span
        className="grid size-[29px] place-items-center rounded-lg bg-lime text-[13px] font-extrabold tracking-[-0.02em] text-[#11170f] shadow-[inset_0_1px_0_rgba(255,255,255,0.25)]"
        aria-hidden="true"
      >
        P
      </span>
      {!compact && (
        <strong className="text-[14.5px] font-extrabold tracking-[-0.03em]">
          Perchly
        </strong>
      )}
    </span>
  );
}

const NAV: {
  label: string;
  href: Record<RouteKey, string>;
  items: readonly { key: RouteKey; label: string; icon: ReactNode }[];
}[] = [
  {
    label: "Workspace",
    href: {
      queue: "/console",
      overview: "/console/overview",
      runs: "/console/runs",
    },
    items: [
      { key: "queue", label: "Approval queue", icon: <Inbox size={17} /> },
    ],
  },
  {
    label: "Observability",
    href: {
      queue: "/console",
      overview: "/console/overview",
      runs: "/console/runs",
    },
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
  user,
  onLogout,
}: {
  route: RouteKey;
  queueCount: number;
  live: boolean;
  onNavigate: (route: RouteKey) => void;
  user: AuthUser;
  onLogout: () => void;
}) {
  return (
    <aside className="flex flex-col border-r border-line bg-[linear-gradient(180deg,rgba(18,23,21,0.55),transparent_45%)] px-3.5 pt-5 pb-[18px] max-[900px]:hidden">
      <div className="grid gap-[5px] px-2.5 pt-1.5 pb-[26px]">
        <Brand />
        <span className="pl-[39px] text-[10px] text-faint">
          single workspace
        </span>
      </div>
      <nav className="grid gap-6" aria-label="Primary navigation">
        {NAV.map((group) => (
          <div className="grid gap-1" key={group.label}>
            <p className="mx-2.5 mb-2 font-mono text-[9px] uppercase tracking-[0.14em] text-faint">
              {group.label}
            </p>
            {group.items.map((item) => (
              <a
                key={item.key}
                className={`group/nav flex h-[38px] items-center gap-[11px] rounded-[7px] px-2.5 text-[12.5px] font-semibold tracking-[-0.005em] transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime [&>svg]:text-faint [&>svg]:transition group-hover/nav:[&>svg]:text-muted ${
                  route === item.key
                    ? "bg-lime-soft text-lime [&>svg]:text-lime"
                    : "text-muted hover:bg-panel-2 hover:text-ink"
                }`}
                href={group.href[item.key]}
                onClick={(event) => {
                  event.preventDefault();
                  onNavigate(item.key);
                }}
                aria-current={route === item.key ? "page" : undefined}
              >
                {item.icon}
                <span>{item.label}</span>
                {item.key === "queue" && (
                  <b className="ml-auto rounded bg-[#263c28] px-1.5 py-0.5 font-mono text-[10px] font-medium tabular-nums text-lime">
                    {queueCount.toString().padStart(2, "0")}
                  </b>
                )}
              </a>
            ))}
          </div>
        ))}
      </nav>
      <div className="mt-auto flex items-center gap-2.5 border-t border-line px-2.5 pt-4 pb-0.5">
        {user.avatar_url ? (
          <img
            src={user.avatar_url}
            alt=""
            className="size-[30px] rounded-full"
          />
        ) : (
          <div className="grid size-[30px] place-items-center rounded-full bg-[#394d43] text-[11px] font-extrabold text-lime">
            {user.login.slice(0, 1).toUpperCase()}
          </div>
        )}
        <div className="grid gap-0.5">
          <strong className="max-w-[100px] truncate text-[12.5px] font-bold">
            {user.name}
          </strong>
          <span className="text-[10px] text-faint">@{user.login}</span>
        </div>
        <span
          className={
            live
              ? "ml-auto size-[7px] rounded-full bg-lime shadow-[0_0_8px_rgba(201,243,107,0.55)]"
              : "ml-auto size-[7px] rounded-full bg-red"
          }
        />
        <button
          type="button"
          onClick={onLogout}
          className="ml-1 text-[10px] text-faint transition hover:text-red focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
          aria-label="Sign out"
        >
          SIGN OUT
        </button>
      </div>
    </aside>
  );
}

export function Header({
  refreshing,
  live,
  label,
  onRefresh,
  user,
  onLogout,
}: {
  refreshing: boolean;
  live: boolean;
  label: string;
  onRefresh: () => void;
  user: AuthUser;
  onLogout: () => void;
}) {
  return (
    <header className="sticky top-0 z-[5] flex h-16 items-center gap-3.5 border-b border-line bg-canvas/80 px-7 backdrop-blur-[14px] max-[900px]:px-[18px]">
      <div className="hidden max-[900px]:flex">
        <Brand />
      </div>
      <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-faint max-[900px]:hidden">
        {label}
      </span>
      <div className="ml-auto flex items-center gap-3.5">
        <span
          className={`inline-flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.08em] ${
            live ? "text-muted" : "text-red"
          }`}
        >
          <span
            className={
              live
                ? "size-[7px] rounded-full bg-lime shadow-[0_0_10px_rgba(201,243,107,0.7)]"
                : "size-[7px] rounded-full bg-red"
            }
          />{" "}
          {live ? "Live" : "Offline"}
        </span>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="grid size-8 place-items-center rounded-md bg-transparent text-muted transition hover:bg-panel-2 hover:text-ink disabled:cursor-wait disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
          aria-label="Refresh current view"
          title="Refresh current view"
        >
          <RefreshCw size={17} className={refreshing ? "animate-spin" : ""} />
        </button>
        {user.avatar_url ? (
          <img
            src={user.avatar_url}
            alt={`${user.name} avatar`}
            className="size-[30px] rounded-full"
          />
        ) : (
          <div className="grid size-[30px] place-items-center rounded-full bg-[#394d43] text-[11px] font-extrabold text-lime">
            {user.login.slice(0, 1).toUpperCase()}
          </div>
        )}
        <button
          type="button"
          onClick={onLogout}
          className="font-mono text-[10px] uppercase tracking-[0.08em] text-faint transition hover:text-red focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
        >
          Sign out
        </button>
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
    <div className="mb-7 flex items-end justify-between gap-6 max-[900px]:flex-col max-[900px]:items-start max-[900px]:gap-3">
      <div>
        <h2 className="text-[32px] font-extrabold leading-[1.12] tracking-[-0.035em] text-ink max-[900px]:text-[26px] max-[520px]:text-[24px]">
          {title}
        </h2>
        <p className="mt-2 max-w-[60ch] text-[13px] text-muted">
          {description}
        </p>
      </div>
      {aside && <div className="flex items-center gap-2 pb-[3px]">{aside}</div>}
    </div>
  );
}

const PILL_TONE: Record<string, string> = {
  ok: "text-lime border-[#2d3d2a]",
  warn: "text-orange border-warn-line",
  error: "text-red border-red-line",
  idle: "text-faint border-line",
};

export function StatusPill({
  tone,
  children,
}: {
  tone: "ok" | "warn" | "error" | "idle";
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border bg-panel px-3 py-[7px] font-mono text-[10.5px] uppercase tracking-[0.06em] whitespace-nowrap ${PILL_TONE[tone]}`}
    >
      <span className="size-1.5 rounded-full bg-current" />
      {children}
    </span>
  );
}

const ACCENT: Record<string, string> = {
  lime: "text-lime",
  cyan: "text-cyan",
  orange: "text-orange",
  violet: "text-violet",
};

export function Metric({
  icon,
  label,
  value,
  detail,
  accent,
}: MetricCardProps) {
  return (
    <div
      className={`relative flex min-h-[122px] gap-3.5 overflow-hidden rounded-lg border border-line bg-[linear-gradient(160deg,#151b18,#101411)] p-[17px] ${ACCENT[accent] ?? ACCENT.lime}`}
    >
      <div className="mt-px">{icon}</div>
      <div className="grid min-w-0 gap-[5px]">
        <span className="text-[10px] font-semibold uppercase tracking-[0.09em] text-muted">
          {label}
        </span>
        <strong className="mt-0.5 text-[27px] font-extrabold leading-[1.05] tracking-[-0.045em] tabular-nums break-words">
          {value}
        </strong>
        <small className="truncate font-mono text-[10.5px] text-current">
          {detail}
        </small>
      </div>
      <span
        aria-hidden="true"
        className="absolute bottom-0 left-0 h-0.5 w-1/3 bg-current"
      />
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
    <div
      className="mb-3.5 flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.09em] text-ink"
      role="heading"
      aria-level={3}
    >
      <span>{label}</span>
      <span className="h-px flex-1 bg-line" />
      {hint && (
        <span className="text-[10px] normal-case tracking-[0.04em] text-cyan">
          {hint}
        </span>
      )}
      {count !== undefined && (
        <span className="text-[10px] normal-case tracking-[0.04em] text-faint">
          {count} open
        </span>
      )}
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
    <div
      className="mb-[18px] flex items-start gap-2.5 rounded-md border border-red-line bg-red-soft px-3.5 py-3 text-[12.5px] text-red"
      role="alert"
    >
      <TriangleAlert className="shrink-0" size={17} />
      <p className="mt-px flex-1">{message}</p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss error"
        className="bg-transparent p-0 text-inherit transition hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
      >
        ×
      </button>
    </div>
  );
}

export function SkeletonPanel({ rows = 4 }: { rows?: number }) {
  return (
    <div
      className="grid gap-2.5 rounded-lg border border-line bg-panel p-3.5"
      aria-hidden="true"
    >
      {Array.from({ length: rows }, (_, index) => (
        <span
          className="h-[52px] animate-pulse rounded-lg bg-panel-2 motion-reduce:animate-none"
          key={index}
        />
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
    <section className="grid min-h-[430px] place-items-center rounded-lg border border-line bg-panel p-8 text-center text-muted">
      <div>
        <span className="inline-grid place-items-center text-lime">{icon}</span>
        <h3 className="mt-[18px] text-[15.5px] font-bold tracking-[-0.01em] text-ink">
          {title}
        </h3>
        <p className="mx-auto mt-2 max-w-[340px] text-[13px] leading-[1.65] text-muted">
          {body}
        </p>
      </div>
    </section>
  );
}

export function PanelHeading({
  title,
  meta,
  actions,
  className = "",
}: {
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex items-start justify-between gap-3 px-[18px] pt-[18px] pb-3.5 ${className}`}
    >
      <div>
        <h3 className="text-[13.5px] font-bold tracking-[-0.01em] text-ink">
          {title}
        </h3>
        {meta && <p className="mt-[5px] text-[11.5px] text-faint">{meta}</p>}
      </div>
      {actions}
    </div>
  );
}

export function NoTelemetry({ tone }: { tone: "ok" | "warn" | "error" }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-dashed px-2.5 py-[5px] font-mono text-[10px] uppercase tracking-[0.07em] ${
        tone === "warn"
          ? "border-warn-line text-orange"
          : "border-line-strong text-faint"
      }`}
    >
      <ShieldCheck size={13} />
      No telemetry recorded in this window
    </span>
  );
}
