import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { Overview } from "./components/observability/Overview";
import { ReviewRuns } from "./components/observability/ReviewRuns";
import { QueuePage } from "./components/queue/QueuePage";
import { Header, Sidebar } from "./components/ui/DashboardChrome";
import { getCurrentUser, logout } from "./lib/api";
import type { AuthUser, RouteKey } from "./types";

const ROUTES: Record<RouteKey, { label: string }> = {
  queue: { label: "Approval queue" },
  overview: { label: "Overview" },
  runs: { label: "Review runs" },
};

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .catch((error: unknown) => {
        const message =
          error instanceof Error ? error.message : "Authentication failed";
        if (!message.includes("401")) setAuthError(message);
      })
      .finally(() => setAuthLoading(false));
  }, []);

  if (authLoading) return <AuthLoading />;
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={
            <HomePage
              user={user}
              authError={authError}
              onLogout={() => {
                void logout().finally(() => setUser(null));
              }}
            />
          }
        />
        <Route
          path="/console/*"
          element={
            user ? (
              <ConsoleApp
                user={user}
                onLogout={() => {
                  void logout().finally(() => setUser(null));
                }}
              />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route
          path="*"
          element={<Navigate to={user ? "/console" : "/"} replace />}
        />
      </Routes>
    </BrowserRouter>
  );
}

function ConsoleApp({
  user,
  onLogout,
}: {
  user: AuthUser;
  onLogout: () => void;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const [live, setLive] = useState(true);
  const [queueCount, setQueueCount] = useState(0);
  const route: RouteKey = location.pathname.includes("overview")
    ? "overview"
    : location.pathname.includes("runs")
      ? "runs"
      : "queue";
  const goTo = (next: RouteKey) =>
    navigate(next === "queue" ? "/console" : `/console/${next}`);
  return (
    <div className="min-h-screen bg-canvas bg-[radial-gradient(circle_at_85%_0%,var(--color-lift),transparent_32%)] font-sans text-[13px] leading-[1.55] text-ink antialiased selection:bg-lime selection:text-[#11170f] [text-rendering:optimizeLegibility]">
      <Header
        refreshing={false}
        live={live}
        label={ROUTES[route].label}
        user={user}
        onLogout={onLogout}
        onRefresh={() => undefined}
      />
      <div className="grid min-h-[calc(100vh-64px)] grid-cols-[232px_minmax(0,1fr)] max-[900px]:block">
        <Sidebar
          route={route}
          queueCount={queueCount}
          live={live}
          onNavigate={goTo}
          user={user}
          onLogout={onLogout}
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
              reviewer={user.login}
            />
          )}
        </main>
      </div>
    </div>
  );
}

function HomePage({
  user,
  authError,
  onLogout,
}: {
  user: AuthUser | null;
  authError: string | null;
  onLogout: () => void;
}) {
  const installUrl = "/auth/github/install";
  const [heroStep, setHeroStep] = useState(0);
  const heroStates = [
    "Four specialists are reading the diff.",
    "Confidence is shaping the handoff.",
    "A human decision is the next step.",
  ];
  useEffect(() => {
    const timer = setInterval(
      () => setHeroStep((current) => (current + 1) % heroStates.length),
      4200,
    );
    return () => clearInterval(timer);
  }, [heroStates.length]);
  return (
    <main className="min-h-screen overflow-hidden bg-canvas text-ink selection:bg-lime selection:text-[#11170f]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_75%_8%,rgba(118,217,219,0.11),transparent_28%),radial-gradient(circle_at_15%_35%,rgba(201,243,107,0.09),transparent_24%)]" />
      <nav className="relative mx-auto flex max-w-[1240px] items-center justify-between px-6 py-6 lg:px-10">
        <Link to="/" className="group inline-flex items-center gap-3 text-ink">
          <span className="grid size-10 place-items-center rounded-xl bg-lime text-lg font-black text-[#11170f] shadow-[0_0_28px_rgba(201,243,107,0.18)] transition duration-300 group-hover:rotate-6 group-hover:scale-105">
            P
          </span>
          <span className="text-[17px] font-extrabold tracking-[-0.04em]">
            Perchly
          </span>
        </Link>
        <div className="flex items-center gap-2 sm:gap-3">
          <a
            href="https://github.com/0x-rekt/perchly"
            target="_blank"
            rel="noreferrer"
            className="hidden rounded-md px-3 py-2 font-mono text-[10px] uppercase tracking-[0.1em] text-muted transition hover:bg-panel-2 hover:text-ink sm:inline-flex"
          >
            GitHub
          </a>
          {user ? (
            <>
              <Link
                to="/console"
                className="rounded-md bg-lime px-4 py-2 font-mono text-[10px] uppercase tracking-[0.1em] text-[#11170f] transition hover:-translate-y-0.5 hover:bg-[#dcff8a]"
              >
                Go to console
              </Link>
              <button
                type="button"
                onClick={onLogout}
                className="rounded-md px-3 py-2 font-mono text-[10px] uppercase tracking-[0.1em] text-muted transition hover:bg-panel-2 hover:text-red"
              >
                Sign out
              </button>
            </>
          ) : (
            <a
              href="/auth/github"
              className="rounded-md border border-line-strong px-4 py-2 font-mono text-[10px] uppercase tracking-[0.1em] text-ink transition hover:border-lime hover:text-lime"
            >
              Sign in
            </a>
          )}
        </div>
      </nav>
      <section className="relative mx-auto grid max-w-[1240px] items-center gap-14 px-6 pb-24 pt-14 lg:grid-cols-[0.92fr_1.08fr] lg:px-10 lg:pb-32 lg:pt-24">
        <div className="animate-[fade-in_700ms_ease-out_both]">
          <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-[#2d4938] bg-lime-soft px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-lime">
            <span className="size-1.5 animate-pulse rounded-full bg-lime" />{" "}
            {user
              ? `Welcome back, ${user.name.split(" ")[0]}`
              : "Human-calibrated code review"}
          </div>
          <h1 className="max-w-[700px] text-[clamp(48px,7vw,84px)] font-black leading-[0.95] tracking-[-0.07em] text-ink">
            Ship faster.
            <br />
            <span className="text-lime">Trust deeper.</span>
          </h1>
          <p className="mt-8 max-w-[540px] text-[17px] leading-[1.65] text-muted">
            Perchly reviews every pull request with specialist agents, then
            knows when to hand the decision back to you.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <a
              href={user ? "/console" : "/auth/github"}
              className="group inline-flex items-center gap-3 rounded-md bg-lime px-5 py-3.5 text-[13px] font-extrabold text-[#11170f] transition duration-300 hover:-translate-y-0.5 hover:bg-[#dcff8a] hover:shadow-[0_12px_30px_rgba(201,243,107,0.16)]"
            >
              {user ? "Go to console" : "Sign in with GitHub"}{" "}
              <span className="transition-transform duration-300 group-hover:translate-x-1">
                →
              </span>
            </a>
            <a
              href={installUrl}
              className="inline-flex items-center gap-2 rounded-md border border-line-strong px-5 py-3.5 text-[13px] font-bold text-ink transition duration-300 hover:-translate-y-0.5 hover:border-cyan hover:text-cyan"
            >
              Install the app <span>↗</span>
            </a>
          </div>
          {authError && (
            <p className="mt-5 max-w-[500px] rounded-md border border-red-line bg-red-soft px-3 py-2 font-mono text-[11px] text-red">
              {authError}
            </p>
          )}
          <div className="mt-10 flex flex-wrap gap-x-7 gap-y-2 font-mono text-[10px] uppercase tracking-[0.11em] text-faint">
            <span>4 specialist agents</span>
            <span>Confidence-aware routing</span>
            <span>Fix PRs included</span>
          </div>
        </div>
        <ReviewPreview />
      </section>
      <section className="relative border-y border-line bg-panel/55">
        <div className="mx-auto grid max-w-[1240px] gap-8 px-6 py-16 lg:grid-cols-3 lg:px-10">
          <Feature title="Specialists, not a single guess" color="text-cyan">
            Security, quality, test coverage, and documentation agents inspect
            the same diff from different angles.
          </Feature>
          <Feature title="Confidence is a control" color="text-orange">
            High-signal findings can post automatically. Uncertain calls land in
            a queue for a human decision.
          </Feature>
          <Feature title="Remediation has a next step" color="text-violet">
            Turn a suggested fix into a reviewed GitHub PR without leaving the
            Perchly console.
          </Feature>
        </div>
      </section>
      <div className="mx-auto max-w-[1240px] px-6 pt-2 lg:px-10">
        <div className="inline-flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-2 font-mono text-[10px] uppercase tracking-[0.1em] text-faint transition duration-500">
          <span className="size-1.5 animate-pulse rounded-full bg-lime" />{" "}
          {heroStates[heroStep]}
        </div>
      </div>
      <WorkflowSection />
      <CalibrationSection />
      <section className="relative mx-auto max-w-[1240px] px-6 py-20 lg:px-10 lg:py-28">
        <div className="overflow-hidden rounded-2xl border border-[#3d5b46] bg-lime-soft px-7 py-10 sm:px-12 sm:py-14">
          <div className="grid items-end gap-8 lg:grid-cols-[1fr_auto]">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.13em] text-lime">
                Connect your repositories
              </p>
              <h2 className="mt-4 max-w-[650px] text-[clamp(30px,4vw,52px)] font-black leading-[1] tracking-[-0.06em] text-ink">
                Let the first review earn its place in your workflow.
              </h2>
              <p className="mt-5 max-w-[560px] text-[14px] leading-[1.7] text-muted">
                Install the GitHub App, open a pull request, and keep the final
                call in your hands.
              </p>
            </div>
            <a
              href={installUrl}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-lime px-5 py-3.5 text-[13px] font-extrabold text-[#11170f] transition hover:-translate-y-0.5 hover:bg-[#dcff8a]"
            >
              Install Perchly <span>↗</span>
            </a>
          </div>
        </div>
      </section>
      <footer className="mx-auto flex max-w-[1240px] flex-col gap-3 border-t border-line px-6 py-8 font-mono text-[10px] uppercase tracking-[0.1em] text-faint sm:flex-row sm:items-center sm:justify-between lg:px-10">
        <span>Perchly / review intelligence</span>
        <span>Built for maintainers who care about the diff</span>
      </footer>
    </main>
  );
}

function WorkflowSection() {
  return (
    <section className="mx-auto max-w-[1240px] px-6 py-20 lg:px-10 lg:py-28">
      <div className="grid gap-12 lg:grid-cols-[0.72fr_1.28fr] lg:items-start">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.13em] text-lime">
            The review loop
          </p>
          <h2 className="mt-4 max-w-[470px] text-[clamp(32px,4vw,52px)] font-black leading-[1] tracking-[-0.06em] text-ink">
            A second set of eyes, with a clear handoff.
          </h2>
          <p className="mt-5 max-w-[430px] text-[14px] leading-[1.7] text-muted">
            Perchly keeps the machine fast and the human accountable. Every
            decision has a visible reason.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            [
              "01",
              "Inspect",
              "Four specialists read the diff and its surrounding context.",
            ],
            [
              "02",
              "Calibrate",
              "Confidence and severity decide whether a finding needs you.",
            ],
            [
              "03",
              "Resolve",
              "Approve, edit, reject, or raise a fix PR from the queue.",
            ],
          ].map(([number, title, copy]) => (
            <article
              key={number}
              className="group rounded-lg border border-line bg-panel p-5 transition duration-300 hover:-translate-y-1 hover:border-line-strong"
            >
              <span className="font-mono text-[10px] text-lime">{number}</span>
              <h3 className="mt-12 text-[17px] font-extrabold text-ink">
                {title}
              </h3>
              <p className="mt-3 text-[12.5px] leading-[1.65] text-muted">
                {copy}
              </p>
              <div className="mt-6 h-px w-8 bg-lime transition-all duration-300 group-hover:w-full" />
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function CalibrationSection() {
  return (
    <section className="border-y border-line bg-[#0e1411]">
      <div className="mx-auto grid max-w-[1240px] gap-12 px-6 py-20 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:px-10 lg:py-28">
        <div className="overflow-hidden rounded-lg border border-line bg-[#0a0e0c] font-mono text-[11px] leading-[1.9] shadow-[0_20px_70px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-2 border-b border-line px-4 py-3 text-faint">
            <span className="size-2 rounded-full bg-red/70" />
            <span className="size-2 rounded-full bg-orange/70" />
            <span className="size-2 rounded-full bg-lime/70" />
            <span className="ml-2">perchly decision trace</span>
          </div>
          <div className="grid gap-1 p-5">
            <p>
              <span className="text-faint">agent.security</span>{" "}
              <span className="text-cyan">→</span>{" "}
              <span className="text-ink">critical finding</span>
            </p>
            <p>
              <span className="text-faint">confidence</span>{" "}
              <span className="text-orange">→ 0.84</span>
            </p>
            <p>
              <span className="text-faint">policy</span>{" "}
              <span className="text-lime">→ needs_approval</span>
            </p>
            <p>
              <span className="text-faint">human.review</span>{" "}
              <span className="text-violet">→ waiting</span>
            </p>
            <p className="mt-3 text-faint">// no silent guesses shipped</p>
          </div>
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.13em] text-violet">
            Trust is a product feature
          </p>
          <h2 className="mt-4 text-[clamp(30px,4vw,48px)] font-black leading-[1] tracking-[-0.06em] text-ink">
            The best automation knows when to pause.
          </h2>
          <p className="mt-5 max-w-[470px] text-[14px] leading-[1.7] text-muted">
            See why a review was posted, held, or escalated. Perchly gives
            maintainers the context to make a fast, informed call.
          </p>
        </div>
      </div>
    </section>
  );
}

function ReviewPreview() {
  return (
    <div className="relative animate-[float-in_900ms_180ms_ease-out_both]">
      <div className="absolute -inset-8 rounded-[40px] bg-cyan/5 blur-3xl" />
      <div className="relative overflow-hidden rounded-xl border border-line-strong bg-panel shadow-[0_24px_90px_rgba(0,0,0,0.35)] transition duration-500 hover:-translate-y-1 hover:border-[#52665a]">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-lime shadow-[0_0_10px_rgba(201,243,107,0.7)]" />
            <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted">
              live review / #184
            </span>
          </div>
          <span className="font-mono text-[10px] text-faint">
            perchly-run-7f2a
          </span>
        </div>
        <div className="grid gap-5 p-5 sm:p-7">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-cyan">
              security specialist
            </p>
            <p className="mt-2 text-[17px] font-bold text-ink">
              Potential credential exposed in config.ts
            </p>
            <p className="mt-2 text-[12px] leading-[1.6] text-muted">
              A low-confidence finding is waiting for a human decision before it
              reaches GitHub.
            </p>
          </div>
          <div className="rounded-lg border border-line bg-[#0c100e] p-4 font-mono text-[11px] leading-[1.8]">
            <p className="text-faint">config.ts:18</p>
            <p className="text-red">- API_KEY = "sk_live_••••"</p>
            <p className="text-lime">+ API_KEY = process.env.API_KEY</p>
          </div>
          <div className="flex items-center justify-between border-t border-line pt-4">
            <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-orange">
              needs approval · 84% confidence
            </span>
            <span className="rounded-md bg-lime px-3 py-2 text-[11px] font-extrabold text-[#11170f]">
              Review finding
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
function Feature({
  title,
  color,
  children,
}: {
  title: string;
  color: string;
  children: string;
}) {
  return (
    <article className="group border-t border-line pt-4 transition duration-300 hover:-translate-y-1">
      <p
        className={`font-mono text-[10px] uppercase tracking-[0.12em] ${color}`}
      >
        Perchly signal
      </p>
      <h2 className="mt-3 text-[18px] font-extrabold tracking-[-0.03em] text-ink">
        {title}
      </h2>
      <p className="mt-3 max-w-[34ch] text-[13px] leading-[1.7] text-muted">
        {children}
      </p>
    </article>
  );
}
function AuthLoading() {
  return (
    <div className="grid min-h-screen place-items-center bg-canvas text-muted">
      <p className="animate-pulse font-mono text-[11px] uppercase tracking-[0.12em]">
        Checking session…
      </p>
    </div>
  );
}
