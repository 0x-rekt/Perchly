import { useEffect, useState } from "react";
import { Overview } from "./components/observability/Overview";
import { ReviewRuns } from "./components/observability/ReviewRuns";
import { QueuePage } from "./components/queue/QueuePage";
import { Header, Sidebar } from "./components/ui/DashboardChrome";
import type { AuthUser, RouteKey } from "./types";
import { getCurrentUser, logout } from "./lib/api";

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
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [route, setRoute] = useState<RouteKey>(routeFromHash);
  const [live, setLive] = useState(true);
  const [queueCount, setQueueCount] = useState(0);

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : "Authentication failed";
        if (!message.includes("401")) setAuthError(message);
      })
      .finally(() => setAuthLoading(false));
  }, []);

  useEffect(() => {
    const onHashChange = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const login = () => {
    const api = import.meta.env.VITE_API_URL ?? "";
    window.location.assign(`${api}/auth/github`);
  };

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      setUser(null);
    }
  };


  if (authLoading) return <AuthLoading />;
  if (!user) return <LoginScreen error={authError} onLogin={login} />;

  const navigate = (next: RouteKey) => {
    window.location.hash = next === "queue" ? "#queue" : `#${next}`;
  };

  return (
    <div className="min-h-screen bg-canvas bg-[radial-gradient(circle_at_85%_0%,var(--color-lift),transparent_32%)] font-sans text-[13px] leading-[1.55] text-ink antialiased selection:bg-lime selection:text-[#11170f] [text-rendering:optimizeLegibility]">
      <Header
        refreshing={false}
        live={live}
        label={ROUTES[route].label}
        user={user}
        onLogout={handleLogout}
        onRefresh={() => window.dispatchEvent(new Event("perchly:refresh"))}
      />
      <div className="grid min-h-[calc(100vh-64px)] grid-cols-[232px_minmax(0,1fr)] max-[900px]:block">
        <Sidebar
          route={route}
          queueCount={queueCount}
          live={live}
          onNavigate={navigate}
          user={user}
          onLogout={handleLogout}
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

function AuthLoading() {
  return (
    <div className="grid min-h-screen place-items-center bg-canvas text-muted">
      <p className="font-mono text-[11px] uppercase tracking-[0.12em]">Checking session…</p>
    </div>
  );
}

function LoginScreen({ error, onLogin }: { error: string | null; onLogin: () => void }) {
  return (
    <main className="grid min-h-screen place-items-center bg-canvas px-6 text-ink bg-[radial-gradient(circle_at_80%_0%,var(--color-lift),transparent_36%)]">
      <section className="w-full max-w-[420px] rounded-lg border border-line bg-panel p-7 shadow-[0_18px_50px_rgba(0,0,0,0.24)]">
        <div className="mb-8 flex items-center gap-2.5">
          <span className="grid size-[29px] place-items-center rounded-lg bg-lime text-[13px] font-extrabold text-[#11170f]">P</span>
          <strong className="text-[14.5px] font-extrabold">Perchly</strong>
        </div>
        <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.12em] text-lime">Authenticated workspace</p>
        <h1 className="text-[30px] font-extrabold leading-[1.12] tracking-[-0.035em]">Review with context.</h1>
        <p className="mt-3 max-w-[36ch] text-[13px] leading-[1.55] text-muted">
          Sign in with GitHub to access your review queue, traces, and workspace data.
        </p>
        {error && <p className="mt-5 rounded-md border border-red-line bg-red-soft px-3 py-2 font-mono text-[11px] text-red">{error}</p>}
        <button type="button" onClick={onLogin} className="mt-7 w-full rounded-md bg-lime px-4 py-3 text-[12px] font-extrabold text-[#11170f] transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime">
          CONTINUE WITH GITHUB
        </button>
      </section>
    </main>
  );
}
