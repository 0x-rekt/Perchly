import { useEffect, useMemo, useState } from "react";
import { getQueue } from "../../lib/api";
import { formatAgeMinutes } from "../../lib/format";
import {
  AlertCircle,
  Clock3,
  Flame,
  GitPullRequest,
  Inbox,
} from "../../lib/icons";
import {
  EmptyState,
  ErrorBanner,
  Metric,
  PageHeading,
  SectionLabel,
  SkeletonPanel,
  StatusPill,
} from "../ui/DashboardChrome";
import { useSurface } from "../../hooks/use-surface";
import type { ReviewItem } from "../../types";
import { ReviewDetail } from "./ReviewDetail";
import { ReviewQueue } from "./ReviewQueue";

export function QueuePage({
  onLiveChange,
  onQueueCount,
  reviewer,
}: {
  onLiveChange: (live: boolean) => void;
  onQueueCount: (count: number) => void;
  reviewer: string;
}) {
  const surface = useSurface<ReviewItem[]>(getQueue);
  const { data, error, loading, reloading, reload } = surface;
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [dismissedError, setDismissedError] = useState<string | null>(null);
  const items = useMemo(() => data ?? [], [data]);
  const active =
    items.find((item) => item.id === selectedId) ?? items[0] ?? null;

  useEffect(() => {
    onLiveChange(error === null);
  }, [error, onLiveChange]);

  useEffect(() => {
    onQueueCount(items.length);
  }, [items, onQueueCount]);

  useEffect(() => {
    const onRefresh = () => reload();
    window.addEventListener("perchly:refresh", onRefresh);
    return () => window.removeEventListener("perchly:refresh", onRefresh);
  }, [reload]);

  const findings = items.reduce(
    (count, item) => count + (item.review_payload.review?.findings.length ?? 0),
    0,
  );
  const critical = items.reduce(
    (count, item) =>
      count +
      (item.review_payload.review?.findings.filter(
        (finding) => finding.severity === "critical",
      ).length ?? 0),
    0,
  );
  const oldest = [...items].sort(
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )[0];
  const hasFailures = items.some(
    (item) => Object.keys(item.specialist_failures).length > 0,
  );

  const aside = error ? (
    <StatusPill tone="error">Connection failed</StatusPill>
  ) : hasFailures ? (
    <StatusPill tone="warn">Specialist failure logged</StatusPill>
  ) : (
    <StatusPill tone="ok">{items.length} pending · agent nominal</StatusPill>
  );

  return (
    <>
      {error && items.length === 0 && error !== dismissedError && (
        <ErrorBanner
          message={error}
          onDismiss={() => setDismissedError(error)}
        />
      )}
      <PageHeading
        title="Approval queue"
        description="Resolve low-confidence findings before they reach GitHub."
        aside={aside}
      />
      <div className="mb-[30px] grid grid-cols-4 gap-2.5 max-[1020px]:grid-cols-2">
        <Metric
          icon={<Inbox size={16} />}
          label="Awaiting review"
          value={items.length.toString().padStart(2, "0")}
          detail="in approval queue"
          accent="lime"
        />
        <Metric
          icon={<AlertCircle size={16} />}
          label="Findings to triage"
          value={findings.toString().padStart(2, "0")}
          detail="across active runs"
          accent="violet"
        />
        <Metric
          icon={<Clock3 size={16} />}
          label="Oldest pending"
          value={oldest ? <AgeValue createdAt={oldest.created_at} /> : "—"}
          detail="waiting for a decision"
          accent="cyan"
        />
        <Metric
          icon={<Flame size={16} />}
          label="Critical findings"
          value={critical.toString().padStart(2, "0")}
          detail="need eyes first"
          accent="orange"
        />
      </div>
      <SectionLabel
        label="Needs your attention"
        count={items.length}
        hint={reloading ? "refreshing…" : undefined}
      />
      {loading && !data ? (
        <div className="grid grid-cols-[320px_minmax(0,1fr)] gap-3.5 items-start max-[900px]:grid-cols-1">
          <SkeletonPanel rows={5} />
          <SkeletonPanel rows={8} />
        </div>
      ) : (
        <div className="grid grid-cols-[320px_minmax(0,1fr)] gap-3.5 items-start max-[900px]:grid-cols-1">
          <ReviewQueue
            items={items}
            selectedId={active?.id ?? null}
            onSelect={setSelectedId}
          />
          {active ? (
            <ReviewDetail item={active} reviewer={reviewer} onComplete={reload} />
          ) : (
            <EmptyState
              icon={<GitPullRequest size={40} />}
              title={error ? "Queue unavailable" : "No pending reviews"}
              body={
                error
                  ? "The approval queue could not be reached. Reconnect and try again."
                  : "New approval requests will appear here when the reviewers flag a low-confidence finding."
              }
            />
          )}
        </div>
      )}
    </>
  );
}

function AgeValue({ createdAt }: { createdAt: string }) {
  const [label, setLabel] = useState("—");
  useEffect(() => {
    const update = () =>
      setLabel(
        formatAgeMinutes((Date.now() - new Date(createdAt).getTime()) / 60_000),
      );
    update();
    const id = window.setInterval(update, 60_000);
    return () => window.clearInterval(id);
  }, [createdAt]);
  return <>{label}</>;
}
