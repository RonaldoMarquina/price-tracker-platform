/**
 * Freshness state management for price observations.
 *
 * Rules:
 * - until exactly 7 days: 'fresh'
 * - more than 7 days: 'stale'
 * - missing or invalid date: 'unknown' -> "Fecha de actualización no disponible"
 */

export type FreshnessState = "fresh" | "stale" | "unknown";

export const FRESHNESS_THRESHOLD_DAYS = 7;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

export function getFreshnessState(
  capturedAtStr: string | null | undefined,
  now: Date = new Date()
): FreshnessState {
  if (!capturedAtStr) {
    return "unknown";
  }

  const capturedDate = new Date(capturedAtStr);
  if (isNaN(capturedDate.getTime())) {
    return "unknown";
  }

  const diffMs = now.getTime() - capturedDate.getTime();
  if (diffMs <= FRESHNESS_THRESHOLD_DAYS * MS_PER_DAY) {
    return "fresh";
  }

  return "stale";
}

export function formatCapturedDate(
  capturedAtStr: string | null | undefined,
  now: Date = new Date()
): { state: FreshnessState; label: string } {
  const state = getFreshnessState(capturedAtStr, now);
  if (state === "unknown") {
    return { state: "unknown", label: "Fecha de actualización no disponible" };
  }

  const date = new Date(capturedAtStr!);
  const formatted = date.toLocaleDateString("es-PE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });

  return { state, label: formatted };
}
