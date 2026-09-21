import { useCallback, useEffect, useMemo, useState } from "react";
import "./App.css";
import { AlertCircle, Clock3, Inbox, ShieldCheck } from "./icons";
import {
  Empty,
  ErrorBanner,
  Header,
  Loading,
  Metric,
  PageHeading,
  SectionLabel,
  Sidebar,
} from "./components/DashboardChrome";
import { ReviewDetail } from "./components/ReviewDetail";
import { ReviewQueue } from "./components/ReviewQueue";
import type { ReviewItem } from "./types";

const API = import.meta.env.VITE_API_URL ?? "";

async function getQueue(): Promise<ReviewItem[]> {
  const response = await fetch(`${API}/reviews/queue`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<ReviewItem[]>;
}

export default function App() {
  const [items, setItems] = useState<ReviewItem[]>([]);
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
    if (refresh) setRefreshing(true);
    else setLoading(true);
    try {
      const queue = await getQueue();
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);
  const findingCount = items.reduce(
    (count, item) => count + (item.review_payload.review?.findings.length ?? 0),
    0,
  );

  return (
    <div className="app-shell">
      <Header refreshing={refreshing} onRefresh={() => void load(true)} />
      <div className="app-layout">
        <Sidebar />
        <main className="workspace">
          {error && (
            <ErrorBanner message={error} onDismiss={() => setError(null)} />
          )}
          <PageHeading />
          <div className="metrics-row">
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
              value={findingCount.toString().padStart(2, "0")}
              detail="across active runs"
              accent="orange"
            />
            <Metric
              icon={<Clock3 size={16} />}
              label="Median decision time"
              value="18m"
              detail="down 12% this week"
              accent="cyan"
            />
            <Metric
              icon={<ShieldCheck size={16} />}
              label="Precision proxy"
              value="94.8%"
              detail="up 2.4% this month"
              accent="violet"
            />
          </div>
          <SectionLabel count={items.length} />
          {loading ? (
            <Loading />
          ) : (
            <div className="queue-layout">
              <ReviewQueue
                items={items}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
              {selected ? (
                <ReviewDetail
                  item={selected}
                  onComplete={() => void load(true)}
                />
              ) : (
                <Empty hasItems={items.length > 0} />
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
