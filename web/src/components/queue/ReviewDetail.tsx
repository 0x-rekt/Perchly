import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";
import { createFixPr, previewFixPr, submitDecision } from "../../lib/api";
import {
  AlertCircle,
  Check,
  FileCode2,
  LoaderCircle,
  RotateCcw,
  TriangleAlert,
  X,
} from "../../lib/icons";
import { shaShort, titleCase } from "../../lib/format";
import type { Decision, Finding, Review, ReviewItem } from "../../types";
import { DiffView } from "../ui/DiffView";

type DetailTab = "findings" | "diff";

const ACTION_VARIANT: Record<"primary" | "danger" | "secondary", string> = {
  primary:
    "border-lime bg-lime text-[#11170f] shadow-[inset_0_1px_0_rgba(255,255,255,0.25)] hover:bg-[#dbff87]",
  danger: "border-red-line bg-transparent text-red hover:bg-red-soft",
  secondary:
    "border-line bg-transparent text-muted hover:border-line-strong hover:text-ink",
};

export function ReviewDetail({
  item,
  onComplete,
}: {
  item: ReviewItem;
  onComplete: () => void;
}) {
  const review = useMemo(
    () => item.review_payload.review ?? { findings: [], failures: {} },
    [item.review_payload.review],
  );
  const diff = item.review_payload.diff;
  const [reviewer, setReviewer] = useState("");
  const [comment, setComment] = useState("");
  const [tab, setTab] = useState<DetailTab>("findings");
  const [editMode, setEditMode] = useState(false);
  const [edited, setEdited] = useState(() => JSON.stringify(review, null, 2));
  const [busy, setBusy] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fixing, setFixing] = useState<string | null>(null);
  const [fixLinks, setFixLinks] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<{
    fixId: number;
    findingId: string;
    diff: string;
    files: string[];
  } | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEdited(JSON.stringify(review, null, 2));
    setTab("findings");
    setEditMode(false);
    setError(null);
    setPreview(null);
    setFixing(null);
    const persistedLinks: Record<string, string> = {};
    for (const fix of item.fix_prs ?? []) {
      if (fix.status === "created" && fix.pull_request_url) {
        persistedLinks[fix.finding_id] = fix.pull_request_url;
      }
    }
    setFixLinks(persistedLinks);
  }, [item.id, item.fix_prs, review]);

  const findingFiles = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const finding of review.findings) {
      counts[finding.file] = (counts[finding.file] ?? 0) + 1;
    }
    return counts;
  }, [review.findings]);

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
      await submitDecision(item.id, decision, {
        reviewer: reviewer.trim(),
        comment: comment.trim() || null,
        ...(editedReview ? { edited_review: editedReview } : {}),
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

  const failures = Object.entries(item.specialist_failures);
  const hasDiff = typeof diff === "string" && diff.trim().length > 0;

  return (
    <section
      className="min-w-0 overflow-hidden rounded-lg border border-line bg-panel"
      aria-label="Review detail"
    >
      <div className="flex items-start justify-between gap-5 border-b border-line px-6 pt-[22px] pb-[18px] max-[520px]:flex-col max-[520px]:px-[18px] max-[520px]:py-[18px]">
        <div>
          <p className="mb-2 font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-lime">
            {item.repository}
          </p>
          <h3 className="text-[21px] font-extrabold tracking-[-0.03em] text-ink">
            Pull request #{item.pr_number}
          </h3>
          <p className="mt-[9px] font-mono text-[10.5px] text-faint">
            {shaShort(item.head_sha)}
          </p>
        </div>
        <span className="inline-flex items-center gap-[7px] whitespace-nowrap rounded-md border border-warn-line bg-warn-soft px-[11px] py-[7px] font-mono text-[10.5px] uppercase tracking-[0.05em] text-orange">
          <AlertCircle size={14} /> {titleCase(item.reason)}
        </span>
      </div>
      {item.review_payload.title && (
        <p className="mx-6 mt-[18px] text-[13.5px] font-semibold text-ink max-[520px]:mx-[18px]">
          {item.review_payload.title}
        </p>
      )}
      {item.review_payload.description && (
        <p className="mx-6 mt-2 text-[12.5px] leading-[1.7] whitespace-pre-wrap text-muted max-[520px]:mx-[18px]">
          {item.review_payload.description}
        </p>
      )}
      {hasDiff && (
        <div
          className="mt-[18px] flex gap-4 border-b border-line px-6 max-[520px]:px-[18px]"
          role="tablist"
          aria-label="Review detail views"
        >
          <button
            type="button"
            role="tab"
            id="tab-findings"
            aria-selected={tab === "findings"}
            aria-controls="panel-findings"
            onClick={() => setTab("findings")}
            className={`flex items-center gap-2 border-b-2 py-3 text-[12.5px] font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime ${
              tab === "findings"
                ? "border-lime text-ink"
                : "border-transparent text-faint hover:text-muted"
            }`}
          >
            Findings
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[10px] tabular-nums ${
                tab === "findings"
                  ? "bg-lime-soft text-lime"
                  : "bg-panel-3 text-faint"
              }`}
            >
              {review.findings.length}
            </span>
          </button>
          <button
            type="button"
            role="tab"
            id="tab-diff"
            aria-selected={tab === "diff"}
            aria-controls="panel-diff"
            onClick={() => setTab("diff")}
            className={`flex items-center gap-2 border-b-2 py-3 text-[12.5px] font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime ${
              tab === "diff"
                ? "border-lime text-ink"
                : "border-transparent text-faint hover:text-muted"
            }`}
          >
            Files changed
          </button>
        </div>
      )}
      <div
        className="px-6 py-5 max-[520px]:px-[18px]"
        role={hasDiff ? "tabpanel" : undefined}
        id={
          hasDiff
            ? tab === "findings"
              ? "panel-findings"
              : "panel-diff"
            : undefined
        }
        aria-labelledby={
          hasDiff
            ? tab === "findings"
              ? "tab-findings"
              : "tab-diff"
            : undefined
        }
      >
        {tab === "diff" && hasDiff ? (
          <DiffView diff={diff} markFiles={findingFiles} />
        ) : (
          <div className="grid gap-2.5">
            {review.findings.length === 0 && (
              <p className="m-0 rounded-md border border-dashed border-line-strong bg-panel-2 p-3.5 text-[12.5px] text-muted">
                No actionable findings were produced.
              </p>
            )}
            {review.findings.map((finding, index) => (
              <FindingCard
                finding={finding}
                fixing={fixing === finding.finding_id}
                pullRequestUrl={
                  finding.finding_id ? fixLinks[finding.finding_id] : undefined
                }
                onFix={async () => {
                  if (!reviewer.trim()) {
                    setError(
                      "Enter your name or email before raising a fix PR.",
                    );
                    return;
                  }
                  if (!finding.finding_id) {
                    setError(
                      "This finding has no stable ID and cannot be fixed safely.",
                    );
                    return;
                  }
                  setError(null);
                  setFixing(finding.finding_id);
                  try {
                    const result = await previewFixPr(
                      item.id,
                      finding.finding_id,
                      reviewer.trim(),
                    );
                    setPreview({
                      fixId: result.fix_id,
                      findingId: finding.finding_id,
                      diff: result.diff,
                      files: result.files,
                    });
                  } catch (err) {
                    setError(
                      err instanceof Error
                        ? err.message
                        : "Unable to raise a fix PR.",
                    );
                  } finally {
                    setFixing(null);
                  }
                }}
                key={`${finding.file}-${finding.line_start}-${index}`}
              />
            ))}
          </div>
        )}
      </div>
      {failures.length > 0 && (
        <div className="px-6 pb-5 max-[520px]:px-[18px]">
          <div className="grid gap-1.5 rounded-md border border-red-line bg-red-soft p-3.5 text-[12px] text-red">
            <p className="m-0 mb-[3px] font-bold">Specialist failures</p>
            {failures.map(([name, message]) => (
              <span key={name} className="leading-[1.55]">
                <b>{name}:</b> {message}
              </span>
            ))}
          </div>
        </div>
      )}
      {preview &&
        createPortal(
          <FixPreviewDialog
            preview={preview}
            busy={fixing === preview.findingId}
            error={error}
            onCancel={() => setPreview(null)}
            onDismissError={() => setError(null)}
            onConfirm={() => {
              setFixing(preview.findingId);
              void createFixPr(preview.fixId, reviewer.trim())
                .then((result) => {
                  setFixLinks((current) => ({
                    ...current,
                    [preview.findingId]: result.pull_request_url,
                  }));
                  setPreview(null);
                })
                .catch((err: unknown) =>
                  setError(
                    err instanceof Error
                      ? err.message
                      : "Unable to create fix PR.",
                  ),
                )
                .finally(() => setFixing(null));
            }}
          />,
          document.body,
        )}
      <div className="border-t border-line px-6 pt-5 pb-6 max-[520px]:px-[18px]">
        {error && !preview && (
          <div
            className="mb-[18px] flex items-start gap-2.5 rounded-md border border-red-line bg-red-soft px-3.5 py-3 text-[12.5px] text-red"
            role="alert"
          >
            <TriangleAlert size={16} className="mt-px shrink-0" />
            <span className="mt-px flex-1">{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              aria-label="Dismiss error"
              className="bg-transparent p-0 text-inherit transition hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
            >
              <X size={15} />
            </button>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3 max-[520px]:grid-cols-1">
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
          <label className="mt-3.5 grid gap-[7px] text-[12px] text-muted">
            <span className="text-[11px] font-semibold tracking-[0.02em]">
              Edited review JSON
            </span>
            <textarea
              value={edited}
              onChange={(event) => setEdited(event.target.value)}
              rows={12}
              spellCheck={false}
              className="min-h-[210px] w-full resize-vertical rounded-md border border-line bg-[#0c100e] p-3 font-mono text-[11.5px] leading-[1.6] text-ink caret-lime outline-none transition focus:border-lime focus:shadow-[0_0_0_3px_rgba(201,243,107,0.12)]"
            />
          </label>
        )}
        <div className="mt-[18px] flex flex-wrap gap-[9px]">
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
              className="inline-flex min-h-10 items-center gap-2 rounded-md border border-line bg-transparent px-3 text-[12.5px] font-bold text-muted transition hover:border-line-strong hover:text-ink active:translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
            >
              <RotateCcw size={16} /> Reset
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

function FixPreviewDialog({
  preview,
  busy,
  error,
  onCancel,
  onDismissError,
  onConfirm,
}: {
  preview: { findingId: string; diff: string; files: string[] };
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onDismissError: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-[2px]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="fix-preview-title"
        className="flex max-h-[86vh] w-[min(980px,100%)] flex-col overflow-hidden rounded-xl border border-line-strong bg-panel shadow-2xl shadow-black/60"
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2
              id="fix-preview-title"
              className="text-[15px] font-bold text-ink"
            >
              Proposed fix
            </h2>
            <p className="mt-1 truncate font-mono text-[11px] text-faint">
              {preview.files.join(", ")}
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close preview"
            className="grid size-8 shrink-0 place-items-center rounded-md bg-transparent text-muted transition hover:bg-panel-2 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
          >
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {error && (
            <div
              className="mb-3 flex items-start gap-2.5 rounded-md border border-red-line bg-red-soft px-3.5 py-3 text-[12.5px] text-red"
              role="alert"
            >
              <TriangleAlert size={16} className="mt-px shrink-0" />
              <span className="mt-px flex-1">{error}</span>
              <button
                type="button"
                onClick={onDismissError}
                aria-label="Dismiss error"
                className="bg-transparent p-0 text-inherit transition hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
              >
                <X size={15} />
              </button>
            </div>
          )}
          <DiffView diff={preview.diff} />
        </div>
        <div className="flex flex-wrap gap-[9px] border-t border-line px-5 py-4">
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="inline-flex min-h-10 items-center gap-2 rounded-md border border-lime bg-lime px-[15px] text-[12.5px] font-bold text-[#11170f] shadow-[inset_0_1px_0_rgba(255,255,255,0.25)] transition hover:bg-[#dbff87] active:translate-y-px disabled:cursor-wait disabled:opacity-55 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
          >
            {busy ? (
              <LoaderCircle size={16} className="animate-spin" />
            ) : (
              <Check size={16} />
            )}
            {busy ? "Submitting..." : "Confirm and open Fix PR"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            autoFocus
            className="inline-flex min-h-10 items-center gap-2 rounded-md border border-line bg-transparent px-[15px] text-[12.5px] font-bold text-muted transition hover:border-line-strong hover:text-ink active:translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
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
    <label className="grid gap-[7px] text-[12px] text-muted">
      <span className="text-[11px] font-semibold tracking-[0.02em]">
        {label}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        className="w-full rounded-md border border-line bg-[#0c100e] px-3 py-2.5 text-[13px] text-ink caret-lime outline-none transition placeholder:text-faint focus:border-lime focus:shadow-[0_0_0_3px_rgba(201,243,107,0.12)]"
      />
    </label>
  );
}

const SEVERITY_STYLE: Record<string, string> = {
  critical: "bg-red-soft text-red",
  warning: "bg-warn-soft text-orange",
  info: "bg-panel-3 text-muted",
};

function FindingCard({
  finding,
  fixing,
  pullRequestUrl,
  onFix,
}: {
  finding: Finding;
  fixing: boolean;
  pullRequestUrl?: string;
  onFix: () => void;
}) {
  return (
    <article className="rounded-md border border-line bg-[#141a17] p-4">
      <div className="flex flex-wrap items-center gap-[9px]">
        <span
          className={`rounded px-[7px] py-1 font-mono text-[10px] uppercase tracking-[0.05em] ${
            SEVERITY_STYLE[finding.severity] ?? SEVERITY_STYLE.info
          }`}
        >
          {finding.severity}
        </span>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.05em] text-faint">
          {titleCase(finding.category)}
        </span>
        <span className="ml-auto font-mono text-[10.5px] text-faint">
          {Math.round(finding.confidence * 100)}% confidence
        </span>
      </div>
      <p className="mt-3 mb-[9px] text-[13px] leading-[1.7] text-ink">
        {finding.message}
      </p>
      <p className="m-0 inline-flex items-center gap-1.5 font-mono text-[11px] text-cyan">
        <FileCode2 size={13} /> {finding.file}:{finding.line_start}-
        {finding.line_end}
      </p>
      {finding.suggested_fix && (
        <p className="mt-3 rounded-md border border-line bg-panel-3 p-3 text-[12px] leading-[1.6] whitespace-pre-wrap text-muted">
          <b className="font-bold text-ink">Suggested fix:</b>{" "}
          {finding.suggested_fix}
        </p>
      )}
      {finding.suggested_fix && finding.finding_id && (
        <div className="mt-3">
          {pullRequestUrl ? (
            <a
              href={pullRequestUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-10 items-center gap-2 rounded-md border border-[#2f4730] bg-lime-soft px-[15px] text-[12.5px] font-bold text-lime transition hover:border-lime focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
            >
              View generated fix PR
            </a>
          ) : (
            <button
              type="button"
              onClick={onFix}
              disabled={fixing}
              className="inline-flex min-h-10 items-center gap-2 rounded-md border border-line bg-transparent px-[15px] text-[12.5px] font-bold text-muted transition hover:border-line-strong hover:text-ink active:translate-y-px disabled:cursor-wait disabled:opacity-55 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
            >
              {fixing ? (
                <LoaderCircle size={14} className="animate-spin" />
              ) : (
                <FileCode2 size={14} />
              )}
              {fixing ? "Opening fix PR…" : "Raise Fix PR"}
            </button>
          )}
        </div>
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
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className={`inline-flex min-h-10 items-center gap-2 rounded-md border px-[15px] text-[12.5px] font-bold transition active:translate-y-px disabled:cursor-wait disabled:opacity-55 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime ${ACTION_VARIANT[variant]}`}
    >
      {busy ? <LoaderCircle size={16} className="animate-spin" /> : icon}
      {busy ? "Submitting..." : label}
    </button>
  );
}
