import type { ReactNode } from "react";

export type RouteKey = "queue" | "overview" | "runs";

export type Severity = "info" | "warning" | "critical";
export type Finding = {
  finding_id?: string | null;
  category: string;
  file: string;
  line_start: number;
  line_end: number;
  severity: Severity;
  confidence: number;
  message: string;
  suggested_fix?: string | null;
};
export type Review = { findings: Finding[]; failures: Record<string, string> };
export type ReviewItem = {
  id: number;
  repository: string;
  pr_number: number;
  head_sha: string;
  status: string;
  reason: string;
  created_at: string;
  review_payload: {
    review?: Review;
    title?: string;
    description?: string | null;
  };
  specialist_failures: Record<string, string>;
};
export type Decision = "approve" | "reject" | "edit";
export type MetricCardProps = {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  detail: string;
  accent: string;
};

export type ReviewsPerDay = { day: string; reviews: number };
export type LatencyByPhase = {
  phase: string;
  spans: number;
  p50_ms: number;
  p95_ms: number;
  failures: number;
};
export type AcceptanceByCategory = {
  category: string;
  total: number;
  accepted: number;
  acceptance_rate: number;
};
export type LearningOutcome = { outcome: string; count: number };
export type OverviewMetrics = {
  window_days: number;
  reviews_per_day: ReviewsPerDay[];
  total_reviews: number;
  cost: {
    total_cost_usd_7d: number;
    reviews_7d: number;
    cost_per_review_usd: number;
  };
  latency_by_phase: LatencyByPhase[];
  hitl_queue: { depth: number; median_age_minutes: number };
  acceptance_rate_by_category: AcceptanceByCategory[];
  learning_outcomes: LearningOutcome[];
};

export type TraceSummary = {
  review_run_id: string;
  repository: string;
  pr_number: number;
  head_sha: string;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  status: "success" | "failed";
  total_cost_usd: number;
  span_count: number;
};
export type TracesResponse = { count: number; items: TraceSummary[] };
export type Span = {
  id: number;
  agent: string;
  phase: string;
  span_type: string;
  model: string | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  input_summary: string | null;
  output_summary: string | null;
  status: "success" | "failed";
  error_message: string | null;
  created_at: string | null;
};
export type TraceDetail = TraceSummary & { spans: Span[] };
