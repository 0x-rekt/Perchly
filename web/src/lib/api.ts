import type {
  Decision,
  OverviewMetrics,
  ReviewItem,
  TraceDetail,
  TracesResponse,
} from "../types";

const API = import.meta.env.VITE_API_URL ?? "";
const OBSERVABILITY_KEY = import.meta.env.VITE_OBSERVABILITY_API_KEY;

async function request<T>(
  path: string,
  init?: { method?: string; body?: unknown },
): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method: init?.method ?? "GET",
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(OBSERVABILITY_KEY ? { "X-API-Key": OBSERVABILITY_KEY } : {}),
      ...(init?.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body:
      init?.body !== undefined && typeof init.body === "string"
        ? init.body
        : init?.body !== undefined
          ? JSON.stringify(init.body)
          : undefined,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function getQueue(): Promise<ReviewItem[]> {
  return request<ReviewItem[]>("/reviews/queue");
}

export function getOverview(days = 14): Promise<OverviewMetrics> {
  return request<OverviewMetrics>(`/observability/overview?days=${days}`);
}

export type TraceFilters = {
  repository?: string;
  agent?: string;
  prNumber?: number;
  headSha?: string;
};

export function getTraces(filters: TraceFilters = {}): Promise<TracesResponse> {
  const params = new URLSearchParams();
  if (filters.repository) params.set("repository", filters.repository);
  if (filters.agent) params.set("agent", filters.agent);
  if (filters.prNumber) params.set("pr_number", String(filters.prNumber));
  if (filters.headSha) params.set("head_sha", filters.headSha);
  const query = params.toString();
  return request<TracesResponse>(`/observability/traces${query ? `?${query}` : ""}`);
}

export function getTrace(reviewRunId: string): Promise<TraceDetail> {
  return request<TraceDetail>(
    `/observability/traces/${encodeURIComponent(reviewRunId)}`,
  );
}

export function submitDecision(
  itemId: number,
  decision: Decision,
  body: { reviewer: string; comment: string | null; edited_review?: unknown },
): Promise<unknown> {
  return request<unknown>(`/reviews/queue/${itemId}/${decision}`, {
    method: "POST",
    body,
  });
}

export function previewFixPr(
  itemId: number,
  findingId: string,
  reviewer: string,
): Promise<{ fix_id: number; diff: string; files: string[] }> {
  return request(`/reviews/queue/${itemId}/findings/${encodeURIComponent(findingId)}/fix-pr/preview`, {
    method: "POST",
    body: { reviewer },
  });
}

export function createFixPr(
  fixId: number,
  reviewer: string,
): Promise<{ fix_id: number; pull_request_url: string; branch: string }> {
  return request(`/reviews/fix-pr/${fixId}/create`, {
    method: "POST",
    body: { reviewer },
  });
}
