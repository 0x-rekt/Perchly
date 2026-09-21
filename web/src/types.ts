import type { ReactNode } from "react";

export type Severity = "info" | "warning" | "critical";
export type Finding = {
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
  value: string;
  detail: string;
  accent: string;
};
