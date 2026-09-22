import { useEffect, useState } from "react";
import "./styles/app.css";
import { Overview } from "./components/observability/Overview";
import { ReviewRuns } from "./components/observability/ReviewRuns";
import { QueuePage } from "./components/queue/QueuePage";
import { Header, Sidebar } from "./components/ui/DashboardChrome";
import type { RouteKey } from "./types";

const ROUTES: Record<RouteKey, { label: string }> = {
  queue: { label: "Approval queue" },
  overview: { label: "Overview" },
  runs: { label: "Review runs" },
};

function routeFromHash(): RouteKey {
  const hash = window.location.hash.replace("#", "");
  if (hash === "overview" || hash === "runs") return hash;
  return "queue";
}

export default function App() {
  const [route, setRoute] = useState<RouteKey>(routeFromHash);
  const [live, setLive] = useState(true);
  const [queueCount, setQueueCount] = useState(0);

  useEffect(() => {
    const onHashChange = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = (next: RouteKey) => {
    window.location.hash = next === "queue" ? "#queue" : `#${next}`;
  };

  return (
    <div className="app-shell">
      <Header
        refreshing={false}
        live={live}
        label={ROUTES[route].label}
        onRefresh={() => window.dispatchEvent(new Event("perchly:refresh"))}
      />
      <div className="app-layout">
        <Sidebar
          route={route}
          queueCount={queueCount}
          live={live}
          onNavigate={navigate}
        />
        <main className="workspace">
          {route === "overview" ? (
            <Overview onLiveChange={setLive} />
          ) : route === "runs" ? (
            <ReviewRuns onLiveChange={setLive} />
          ) : (
            <QueuePage
              onLiveChange={setLive}
              onQueueCount={setQueueCount}
            />
          )}
        </main>
      </div>
    </div>
  );
}