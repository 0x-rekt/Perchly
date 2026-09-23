import { useEffect, useMemo, useState } from "react";
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
  const [fixing, setFixing] = useState<string | null>(null);
  const [fixLinks, setFixLinks] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<{ fixId: number; findingId: string; diff: string; files: string[] } | null>(null);

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
            fixing={fixing === finding.finding_id}
            pullRequestUrl={finding.finding_id ? fixLinks[finding.finding_id] : undefined}
            onFix={async () => {
              if (!reviewer.trim()) {
                setError("Enter your name or email before raising a fix PR.");
                return;
              }
              if (!finding.finding_id) {
                setError("This finding has no stable ID and cannot be fixed safely.");
                return;
              }
              setError(null);
              setFixing(finding.finding_id);
              try {
                const result = await previewFixPr(item.id, finding.finding_id, reviewer.trim());
                setPreview({ fixId: result.fix_id, findingId: finding.finding_id, diff: result.diff, files: result.files });
              } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to raise a fix PR.");
              } finally {
                setFixing(null);
              }
            }}
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
      {preview && (
        <div className="fix-preview" role="dialog" aria-label="Proposed fix preview">
          <div className="fix-preview-header">
            <b>Proposed fix</b>
            <span>{preview.files.join(", ")}</span>
          </div>
          <pre>{preview.diff}</pre>
          <div className="decision-actions">
            <Action
              label="Confirm and open Fix PR"
              icon={<Check size={16} />}
              busy={fixing === preview.findingId}
              onClick={() => {
                setFixing(preview.findingId);
                void createFixPr(preview.fixId, reviewer.trim())
                  .then((result) => {
                    setFixLinks((current) => ({ ...current, [preview.findingId]: result.pull_request_url }));
                    setPreview(null);
                  })
                  .catch((err: unknown) => setError(err instanceof Error ? err.message : "Unable to create fix PR."))
                  .finally(() => setFixing(null));
              }}
              variant="primary"
            />
            <button type="button" className="reset-button" onClick={() => setPreview(null)}>Cancel</button>
          </div>
        </div>
      )}
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
      {finding.suggested_fix && finding.finding_id && (
        <div className="finding-fix-action">
          {pullRequestUrl ? (
            <a href={pullRequestUrl} target="_blank" rel="noreferrer">
              View generated fix PR
            </a>
          ) : (
            <button type="button" onClick={onFix} disabled={fixing} className="action action-secondary">
              {fixing ? <LoaderCircle size={14} className="spin" /> : <FileCode2 size={14} />}
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
      className={`action action-${variant}`}
    >
      {busy ? <LoaderCircle size={16} className="spin" /> : icon}
      {busy ? "Submitting..." : label}
    </button>
  );
}
