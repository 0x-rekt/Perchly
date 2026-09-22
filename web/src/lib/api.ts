import type {
  Decision,
  OverviewMetrics,
  ReviewItem,
  TraceDetail,
  TracesResponse,
} from "../types";

const API = import.meta.env.VITE_API_URL ?? "";

async function request<T>(
  path: string,
  init?: { method?: string; body?: unknown },
): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method: init?.method ?? "GET",
    headers: {
      Accept: "application/json",
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

export function getTraces(): Promise<TracesResponse> {
  return request<TracesResponse>("/observability/traces");
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