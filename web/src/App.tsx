import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertCircle,
  Check,
  ChevronRight,
  FileCode2,
  GitPullRequest,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  X,
} from "./icons";

type Severity = "info" | "warning" | "critical";
type Finding = {
  category: string;
  file: string;
  line_start: number;
  line_end: number;
  severity: Severity;
  confidence: number;
  message: string;
  suggested_fix?: string | null;
};
type Review = { findings: Finding[]; failures: Record<string, string> };
type Item = {
  id: number;
  repository: string;
  pr_number: number;
  head_sha: string;
  status: string;
  reason: string;
  created_at: string;
  review_payload: {
    review?: Review;
    title?: string;
    description?: string | null;
  };
  specialist_failures: Record<string, string>;
};
type Decision = "approve" | "reject" | "edit";

const API = import.meta.env.VITE_API_URL ?? "";
const label = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
const dateLabel = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export default function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) ?? null,
    [items, selectedId],
  );
  const load = useCallback(async (refresh = false) => {
    setError(null);
    refresh ? setRefreshing(true) : setLoading(true);
    try {
      const queue = await api<Item[]>("/reviews/queue");
      setItems(queue);
      setSelectedId((current) =>
        current && queue.some((item) => item.id === current)
          ? current
          : (queue[0]?.id ?? null),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load the queue.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <Header refreshing={refreshing} onRefresh={() => void load(true)} />
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {error && (
          <ErrorBanner message={error} onDismiss={() => setError(null)} />
        )}
        <div className="mb-6 flex items-end justify-between">
          <div>
            <p className="text-sm font-medium text-teal-700">Human review</p>
            <h2 className="mt-1 text-2xl font-semibold">Approval queue</h2>
            <p className="mt-2 text-sm text-slate-500">
              Review low-confidence findings before they reach GitHub.
            </p>
          </div>
          <div className="hidden rounded-xl bg-white px-4 py-3 text-right shadow-sm ring-1 ring-slate-200 sm:block">
            <p className="text-2xl font-semibold">{items.length}</p>
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Pending
            </p>
          </div>
        </div>
        {loading ? (
          <Loading />
        ) : (
          <div className="grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
            <Queue
              items={items}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
            {selected ? (
              <Detail item={selected} onComplete={() => void load(true)} />
            ) : (
              <Empty hasItems={items.length > 0} />
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function Header({
  refreshing,
  onRefresh,
}: {
  refreshing: boolean;
  onRefresh: () => void;
}) {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-teal-700 text-white">
            <GitPullRequest size={20} />
          </div>
          <div>
            <h1 className="font-semibold">Perchly</h1>
            <p className="text-xs text-slate-500">Review console</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium hover:bg-slate-50 disabled:opacity-60"
        >
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />{" "}
          Refresh
        </button>
      </div>
    </header>
  );
}

function Queue({
  items,
  selectedId,
  onSelect,
}: {
  items: Item[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <aside className="h-fit rounded-2xl bg-white p-3 shadow-sm ring-1 ring-slate-200">
      <div className="px-3 pb-3 pt-2">
        <h3 className="font-semibold">Pending reviews</h3>
        <p className="mt-1 text-xs text-slate-500">
          Oldest items appear first.
        </p>
      </div>
      {items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-500">
          Your queue is clear.
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => onSelect(item.id)}
              className={`w-full rounded-xl border p-3 text-left transition ${selectedId === item.id ? "border-teal-300 bg-teal-50" : "border-transparent hover:border-slate-200 hover:bg-slate-50"}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">
                    {item.repository}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Pull request #{item.pr_number}
                  </p>
                </div>
                <ChevronRight size={16} className="shrink-0 text-slate-400" />
              </div>
              <div className="mt-3 flex justify-between gap-2 text-xs text-slate-500">
                <span className="truncate">{label(item.reason)}</span>
                <span className="shrink-0">{dateLabel(item.created_at)}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </aside>
  );
}

function Detail({ item, onComplete }: { item: Item; onComplete: () => void }) {
  const review = item.review_payload.review ?? { findings: [], failures: {} };
  const [reviewer, setReviewer] = useState("");
  const [comment, setComment] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [edited, setEdited] = useState(() => JSON.stringify(review, null, 2));
  const [busy, setBusy] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setEdited(JSON.stringify(review, null, 2));
    setEditMode(false);
    setError(null);
  }, [item.id]);
  const submit = async (decision: Decision) => {
    if (!reviewer.trim()) {
      setError("Enter your name or email before submitting.");
      return;
    }
    let editedReview: Review | undefined;
    if (decision === "edit") {
      try {
        editedReview = JSON.parse(edited) as Review;
        if (!Array.isArray(editedReview.findings)) throw new Error();
      } catch {
        setError("Edited review must be valid JSON with a findings array.");
        return;
      }
    }
    setError(null);
    setBusy(decision);
    try {
      await api(`/reviews/queue/${item.id}/${decision}`, {
        method: "POST",
        body: JSON.stringify({
          reviewer: reviewer.trim(),
          comment: comment.trim() || null,
          ...(editedReview ? { edited_review: editedReview } : {}),
        }),
      });
      onComplete();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to submit decision.",
      );
    } finally {
      setBusy(null);
    }
  };
  return (
    <section className="min-w-0 rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
      <div className="border-b border-slate-200 px-5 py-5 sm:px-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-teal-700">
              {item.repository}
            </p>
            <h3 className="mt-1 text-xl font-semibold">
              Pull request #{item.pr_number}
            </h3>
            <p className="mt-2 font-mono text-xs text-slate-400">
              {item.head_sha}
            </p>
          </div>
          <span className="inline-flex items-center gap-2 rounded-full bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-700 ring-1 ring-amber-200">
            <AlertCircle size={14} /> {label(item.reason)}
          </span>
        </div>
        {item.review_payload.title && (
          <p className="mt-5 text-sm font-medium">
            {item.review_payload.title}
          </p>
        )}
        {item.review_payload.description && (
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-500">
            {item.review_payload.description}
          </p>
        )}
      </div>
      <div className="space-y-4 px-5 py-5 sm:px-7">
        {review.findings.length === 0 && (
          <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
            No actionable findings were produced.
          </p>
        )}
        {review.findings.map((finding, index) => (
          <FindingCard
            finding={finding}
            key={`${finding.file}-${finding.line_start}-${index}`}
          />
        ))}
        {Object.keys(item.specialist_failures).length > 0 && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            <p className="font-semibold">Specialist failures</p>
            {Object.entries(item.specialist_failures).map(([name, message]) => (
              <p key={name} className="mt-1">
                <b>{name}:</b> {message}
              </p>
            ))}
          </div>
        )}
      </div>
      <div className="border-t border-slate-200 px-5 py-5 sm:px-7">
        {error && (
          <ErrorBanner message={error} onDismiss={() => setError(null)} />
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Reviewer"
            value={reviewer}
            onChange={setReviewer}
            placeholder="you@example.com"
          />
          <Field
            label="Comment (optional)"
            value={comment}
            onChange={setComment}
            placeholder="Why did you choose this decision?"
          />
        </div>
        {editMode && (
          <label className="mt-4 block text-sm font-medium">
            Edited review JSON
            <textarea
              value={edited}
              onChange={(event) => setEdited(event.target.value)}
              rows={12}
              spellCheck={false}
              className="mt-1.5 w-full rounded-lg border border-slate-300 bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-100 outline-none focus:border-teal-600"
            />
          </label>
        )}
        <div className="mt-5 flex flex-wrap gap-3">
          <Action
            label="Approve"
            icon={<Check size={16} />}
            busy={busy === "approve"}
            onClick={() => void submit("approve")}
            variant="primary"
          />
          <Action
            label="Reject"
            icon={<X size={16} />}
            busy={busy === "reject"}
            onClick={() => void submit("reject")}
            variant="danger"
          />
          {editMode ? (
            <Action
              label="Submit edited review"
              icon={<Check size={16} />}
              busy={busy === "edit"}
              onClick={() => void submit("edit")}
              variant="secondary"
            />
          ) : (
            <Action
              label="Edit review"
              icon={<FileCode2 size={16} />}
              busy={false}
              onClick={() => setEditMode(true)}
              variant="secondary"
            />
          )}
          {editMode && (
            <button
              type="button"
              onClick={() => {
                setEditMode(false);
                setEdited(JSON.stringify(review, null, 2));
              }}
              className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100"
            >
              <RotateCcw size={16} /> Reset
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label className="text-sm font-medium text-slate-700">
      {label}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
      />
    </label>
  );
}
function FindingCard({ finding }: { finding: Finding }) {
  const severity =
    finding.severity === "critical"
      ? "bg-red-50 text-red-700 ring-red-200"
      : finding.severity === "warning"
        ? "bg-amber-50 text-amber-700 ring-amber-200"
        : "bg-slate-100 text-slate-600 ring-slate-200";
  return (
    <article className="rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded-full px-2 py-1 text-[11px] font-bold uppercase ring-1 ${severity}`}
        >
          {finding.severity}
        </span>
        <span className="text-xs font-semibold uppercase text-slate-400">
          {finding.category}
        </span>
        <span className="ml-auto text-xs text-slate-500">
          {Math.round(finding.confidence * 100)}% confidence
        </span>
      </div>
      <p className="mt-3 text-sm font-medium leading-6">{finding.message}</p>
      <p className="mt-2 inline-flex items-center gap-1.5 font-mono text-xs text-slate-500">
        <FileCode2 size={13} />
        {finding.file}:{finding.line_start}-{finding.line_end}
      </p>
      {finding.suggested_fix && (
        <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm leading-6 text-slate-600">
          <b>Suggested fix:</b> {finding.suggested_fix}
        </p>
      )}
    </article>
  );
}
function Action({
  label,
  icon,
  busy,
  onClick,
  variant,
}: {
  label: string;
  icon: ReactNode;
  busy: boolean;
  onClick: () => void;
  variant: "primary" | "danger" | "secondary";
}) {
  const style =
    variant === "primary"
      ? "bg-teal-700 text-white hover:bg-teal-800"
      : variant === "danger"
        ? "border border-red-200 text-red-700 hover:bg-red-50"
        : "border border-slate-300 text-slate-700 hover:bg-slate-50";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className={`inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold disabled:opacity-60 ${style}`}
    >
      {busy ? <LoaderCircle size={16} className="animate-spin" /> : icon}
      {busy ? "Submitting..." : label}
    </button>
  );
}
function Loading() {
  return (
    <div className="grid min-h-[32rem] place-items-center rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
      <div className="text-center text-slate-500">
        <LoaderCircle
          className="mx-auto animate-spin text-teal-700"
          size={28}
        />
        <p className="mt-3 text-sm">Loading review queue...</p>
      </div>
    </div>
  );
}
function Empty({ hasItems }: { hasItems: boolean }) {
  return (
    <section className="grid min-h-[32rem] place-items-center rounded-2xl bg-white p-8 text-center shadow-sm ring-1 ring-slate-200">
      <div>
        <FileCode2 className="mx-auto text-slate-300" size={42} />
        <h3 className="mt-4 font-semibold">
          {hasItems ? "Select a review" : "No pending reviews"}
        </h3>
        <p className="mt-2 max-w-sm text-sm leading-6 text-slate-500">
          {hasItems
            ? "Choose a pull request from the queue to inspect its findings."
            : "New approval requests will appear here."}
        </p>
      </div>
    </section>
  );
}
function ErrorBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  return (
    <div className="mb-5 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <AlertCircle className="shrink-0" size={17} />
      <p className="flex-1">{message}</p>
      <button type="button" onClick={onDismiss} aria-label="Dismiss error">
        <X size={16} />
      </button>
    </div>
  );
}
