/**
 * Small formatting helpers.
 *
 * In plain words: one place that decides how numbers and dates look, so "FAR 1.2%"
 * is written the same way on every screen, and a missing value is always shown as
 * an em dash - never as a misleading 0.
 */

export const DASH = "—";

export function pct(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? DASH : `${(value * 100).toFixed(digits)}%`;
}

export function num(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined || Number.isNaN(value) ? DASH : value.toFixed(digits);
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
}

export function count(value: number | null | undefined): string {
  return value === null || value === undefined ? DASH : value.toLocaleString("en-US");
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? DASH
    : date.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? DASH : date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Sentence-style label for a snake_case code: "ambiguous_margin" -> "Ambiguous margin". */
export function humanize(code: string): string {
  const text = code.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
