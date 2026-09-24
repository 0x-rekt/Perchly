export const pad = (value: number) => value.toString().padStart(2, "0");

export function formatMoney(value: number): string {
  if (!Number.isFinite(value) || value === 0) return "$0.00";
  if (value >= 1) return `$${value.toFixed(2)}`;
  if (value >= 0.01) return `$${value.toFixed(3)}`;
  return `$${value.toFixed(4)}`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "—";
  }
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${pad(rest)}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${pad(minutes % 60)}m`;
}

export function formatAgeMinutes(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes <= 0) return "just now";
  if (minutes < 60) return `${Math.round(minutes)}m old`;
  if (minutes < 1440)
    return `${Math.round(minutes / 60)}h ${pad(Math.round(minutes % 60))}m old`;
  return `${Math.round(minutes / 1440)}d old`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDay(value: string): string {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatPercent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

export function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function shaShort(value: string): string {
  return value.length > 8 ? value.slice(0, 8) : value;
}
