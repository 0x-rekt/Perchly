import { useEffect, useState } from "react";
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
    <div className="min-h-screen bg-canvas bg-[radial-gradient(circle_at_85%_0%,var(--color-lift),transparent_32%)] font-sans text-[13px] leading-[1.55] text-ink antialiased selection:bg-lime selection:text-[#11170f] [text-rendering:optimizeLegibility]">
      <Header
        refreshing={false}
        live={live}
        label={ROUTES[route].label}
        onRefresh={() => window.dispatchEvent(new Event("perchly:refresh"))}
      />
      <div className="grid min-h-[calc(100vh-64px)] grid-cols-[232px_minmax(0,1fr)] max-[900px]:block">
        <Sidebar
          route={route}
          queueCount={queueCount}
          live={live}
          onNavigate={navigate}
        />
        <main className="mx-auto w-[min(1440px,100%)] px-[clamp(24px,5vw,72px)] pt-[38px] pb-[72px] max-[900px]:px-[18px] max-[900px]:pt-[30px] max-[900px]:pb-[54px]">
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
