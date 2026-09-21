import { Activity, AlertCircle, CheckCircle, ChevronRight } from "../icons";
import type { ReviewItem } from "../types";

const label = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
const dateLabel = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
};

export function ReviewQueue({
  items,
  selectedId,
  onSelect,
}: {
  items: ReviewItem[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <aside className="queue-panel">
      <div className="panel-heading">
        <div>
          <h3>Pending reviews</h3>
          <p>Oldest items first</p>
        </div>
        <button
          className="filter-button"
          type="button"
          aria-label="Filter reviews"
        >
          <Activity size={15} />
        </button>
      </div>
      <div className="queue-tabs">
        <span className="selected-tab">
          All <b>{items.length}</b>
        </span>
        <span>Security</span>
        <span>Quality</span>
      </div>
      <div className="queue-list">
        {items.length === 0 ? (
          <div className="empty-queue">
            <CheckCircle size={23} />
            <span>Queue clear</span>
          </div>
        ) : (
          items.map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => onSelect(item.id)}
              className={`queue-item ${selectedId === item.id ? "selected" : ""}`}
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
                  <AlertCircle size={12} /> {label(item.reason)}
                </span>
                <span>{dateLabel(item.created_at)}</span>
              </div>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
