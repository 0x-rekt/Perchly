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

const FACET_TAB =
  "border-b border-b-transparent bg-none px-0 py-[11px] font-mono text-[10.5px] uppercase tracking-[0.05em] text-faint transition hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime";
const FACET_TAB_ACTIVE = "border-b border-b-lime text-lime";

const FACET_BADGE =
  "ml-[5px] rounded bg-[#263c28] px-[5px] py-px font-mono text-[10px] font-medium tabular-nums text-lime";

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
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );
  const visible =
    facet === "all"
      ? ordered
      : ordered.filter((item) => facetOf(item) === facet);
  const securityCount = ordered.filter(
    (item) => facetOf(item) === "security",
  ).length;
  const qualityCount = ordered.filter(
    (item) => facetOf(item) === "quality",
  ).length;
  return (
    <aside
      className="overflow-hidden rounded-lg border border-line bg-panel"
      aria-label="Pending reviews"
    >
      <div className="flex items-start justify-between gap-3 px-[18px] pt-[18px] pb-3.5">
        <div>
          <h3 className="text-[13.5px] font-bold tracking-[-0.01em] text-ink">
            Pending reviews
          </h3>
          <p className="mt-[5px] text-[11.5px] text-faint">
            Oldest items first
          </p>
        </div>
      </div>
      <div
        className="flex gap-[18px] border-b border-line px-[18px]"
        aria-label="Filter by domain"
      >
        <button
          type="button"
          className={`${FACET_TAB} ${facet === "all" ? FACET_TAB_ACTIVE : ""}`}
          aria-pressed={facet === "all"}
          onClick={() => setFacet("all")}
        >
          All <b className={FACET_BADGE}>{items.length}</b>
        </button>
        <button
          type="button"
          className={`${FACET_TAB} ${facet === "security" ? FACET_TAB_ACTIVE : ""}`}
          aria-pressed={facet === "security"}
          onClick={() => setFacet("security")}
        >
          Security{securityCount > 0 ? ` ${securityCount}` : ""}
        </button>
        <button
          type="button"
          className={`${FACET_TAB} ${facet === "quality" ? FACET_TAB_ACTIVE : ""}`}
          aria-pressed={facet === "quality"}
          onClick={() => setFacet("quality")}
        >
          Quality{qualityCount > 0 ? ` ${qualityCount}` : ""}
        </button>
      </div>
      <div className="p-2">
        {visible.length === 0 ? (
          <div className="grid place-items-center gap-2 py-[42px] text-[12px] text-lime">
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
              className={`group mb-[3px] block w-full rounded-lg border px-3 py-[13px] text-left transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime ${
                selectedId === item.id
                  ? "border-[#2f4730] bg-lime-soft"
                  : "border-transparent hover:bg-panel-2"
              }`}
              aria-pressed={selectedId === item.id}
            >
              <div className="flex items-center gap-2.5">
                <span className="grid size-[26px] shrink-0 place-items-center rounded-[7px] bg-[#293d34] text-[11px] font-bold text-cyan">
                  {item.repository.slice(0, 1).toUpperCase()}
                </span>
                <div className="grid min-w-0 gap-0.5">
                  <p className="truncate text-[12px] font-semibold text-ink">
                    {item.repository}
                  </p>
                  <span className="font-mono text-[10px] text-faint">
                    PR #{item.pr_number}
                  </span>
                </div>
                <ChevronRight size={16} className="ml-auto text-faint" />
              </div>
              <p className="mt-[11px] mb-3 truncate text-[12px] text-muted">
                {item.review_payload.title ?? "Review requires attention"}
              </p>
              <div className="flex items-center justify-between gap-2 font-mono text-[10px] text-faint">
                <span className="flex items-center gap-[5px] text-[10px] text-orange">
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
