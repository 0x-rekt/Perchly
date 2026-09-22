import { useState } from "react";
import { AlertCircle, CheckCircle, ChevronRight } from "../../lib/icons";
import { formatDateTime, titleCase } from "../../lib/format";
import type { ReviewItem } from "../../types";

type QueueFacet = "all" | "security" | "quality";

function facetOf(item: ReviewItem): "security" | "quality" | "other" {
  const categories = new Set(
    (item.review_payload.review?.findings ?? []).map(
      (finding) => finding.category,
    ),
  );
  if (categories.has("security")) return "security";
  if (categories.has("quality")) return "quality";
  return "other";
}

export function ReviewQueue({
  items,
  selectedId,
  onSelect,
}: {
  items: ReviewItem[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const [facet, setFacet] = useState<QueueFacet>("all");
  const ordered = [...items].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );
  const visible =
    facet === "all" ? ordered : ordered.filter((item) => facetOf(item) === facet);
  const securityCount = ordered.filter((item) => facetOf(item) === "security").length;
  const qualityCount = ordered.filter((item) => facetOf(item) === "quality").length;
  return (
    <aside className="queue-panel" aria-label="Pending reviews">
      <div className="panel-heading">
        <div>
          <h3>Pending reviews</h3>
          <p>Oldest items first</p>
        </div>
      </div>
      <div className="queue-tabs" aria-label="Filter by domain">
        <button
          type="button"
          className={facet === "all" ? "selected-tab" : ""}
          aria-pressed={facet === "all"}
          onClick={() => setFacet("all")}
        >
          All <b>{items.length}</b>
        </button>
        <button
          type="button"
          className={facet === "security" ? "selected-tab" : ""}
          aria-pressed={facet === "security"}
          onClick={() => setFacet("security")}
        >
          Security{securityCount > 0 ? ` ${securityCount}` : ""}
        </button>
        <button
          type="button"
          className={facet === "quality" ? "selected-tab" : ""}
          aria-pressed={facet === "quality"}
          onClick={() => setFacet("quality")}
        >
          Quality{qualityCount > 0 ? ` ${qualityCount}` : ""}
        </button>
      </div>
      <div className="queue-list">
        {visible.length === 0 ? (
          <div className="empty-queue">
            <CheckCircle size={23} />
            <span>
              {facet === "all" ? "Queue clear" : `No ${facet} reviews pending`}
            </span>
          </div>
        ) : (
          visible.map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => onSelect(item.id)}
              className={`queue-item ${selectedId === item.id ? "selected" : ""}`}
              aria-pressed={selectedId === item.id}
            >
              <div className="queue-item-top">
                <span className="repo-avatar">
                  {item.repository.slice(0, 1).toUpperCase()}
                </span>
                <div className="queue-item-name">
                  <p>{item.repository}</p>
                  <span>PR #{item.pr_number}</span>
                </div>
                <ChevronRight size={16} />
              </div>
              <p className="queue-item-title">
                {item.review_payload.title ?? "Review requires attention"}
              </p>
              <div className="queue-item-meta">
                <span className="warning-tag">
                  <AlertCircle size={12} /> {titleCase(item.reason)}
                </span>
                <span>{formatDateTime(item.created_at)}</span>
              </div>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}