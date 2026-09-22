import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { submitDecision } from "../../lib/api";
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
  const [reviewer, setReviewer] = useState("");
  const [comment, setComment] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [edited, setEdited] = useState(() => JSON.stringify(review, null, 2));
  const [busy, setBusy] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEdited(JSON.stringify(review, null, 2));
    setEditMode(false);
    setError(null);
  }, [item.id, review]);

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

  return (
    <section className="review-detail" aria-label="Review detail">
      <div className="detail-header">
        <div>
          <p className="repo-label">{item.repository}</p>
          <h3>Pull request #{item.pr_number}</h3>
          <p className="sha">{shaShort(item.head_sha)}</p>
        </div>
        <span className="reason-tag">
          <AlertCircle size={14} /> {titleCase(item.reason)}
        </span>
      </div>
      {item.review_payload.title && (
        <p className="pr-title">{item.review_payload.title}</p>
      )}
      {item.review_payload.description && (
        <p className="pr-description">{item.review_payload.description}</p>
      )}
      <div className="finding-list">
        {review.findings.length === 0 && (
          <p className="no-findings">No actionable findings were produced.</p>
        )}
        {review.findings.map((finding, index) => (
          <FindingCard
            finding={finding}
            key={`${finding.file}-${finding.line_start}-${index}`}
          />
        ))}
        {failures.length > 0 && (
          <div className="specialist-failures">
            <p>Specialist failures</p>
            {failures.map(([name, message]) => (
              <span key={name}>
                <b>{name}:</b> {message}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="decision-panel">
        {error && (
          <div className="decision-error" role="alert">
            <TriangleAlert size={16} />
            <span>{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              aria-label="Dismiss error"
            >
              <X size={15} />
            </button>
          </div>
        )}
        <div className="form-grid">
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
          <label className="json-editor">
            Edited review JSON
            <textarea
              value={edited}
              onChange={(event) => setEdited(event.target.value)}
              rows={12}
              spellCheck={false}
            />
          </label>
        )}
        <div className="decision-actions">
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
              className="reset-button"
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
    <label className="field">
      <span>{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete="off"
      />
    </label>
  );
}

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <article className="finding-card">
      <div className="finding-meta">
        <span className={`severity severity-${finding.severity}`}>
          {finding.severity}
        </span>
        <span className="category">{titleCase(finding.category)}</span>
        <span className="confidence">
          {Math.round(finding.confidence * 100)}% confidence
        </span>
      </div>
      <p className="finding-message">{finding.message}</p>
      <p className="finding-location">
        <FileCode2 size={13} /> {finding.file}:{finding.line_start}-
        {finding.line_end}
      </p>
      {finding.suggested_fix && (
        <p className="suggested-fix">
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
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className={`action action-${variant}`}
    >
      {busy ? <LoaderCircle size={16} className="spin" /> : icon}
      {busy ? "Submitting..." : label}
    </button>
  );
}