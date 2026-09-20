import { describe, it, expect } from "vitest";
import { getFreshnessState, formatCapturedDate } from "./freshness";

describe("getFreshnessState", () => {
  const baseNow = new Date("2026-09-20T12:00:00Z");

  it("returns 'unknown' when date string is missing or null", () => {
    expect(getFreshnessState(null, baseNow)).toBe("unknown");
    expect(getFreshnessState(undefined, baseNow)).toBe("unknown");
    expect(getFreshnessState("", baseNow)).toBe("unknown");
  });

  it("returns 'unknown' when date string is invalid", () => {
    expect(getFreshnessState("not-a-valid-date", baseNow)).toBe("unknown");
  });

  it("returns 'fresh' when date is within 7 days", () => {
    // 2 days ago
    const twoDaysAgo = new Date("2026-09-18T12:00:00Z").toISOString();
    expect(getFreshnessState(twoDaysAgo, baseNow)).toBe("fresh");

    // Exactly 7 days ago
    const exactlySevenDays = new Date(baseNow.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();
    expect(getFreshnessState(exactlySevenDays, baseNow)).toBe("fresh");
  });

  it("returns 'stale' when date is older than 7 days", () => {
    // 7 days and 1 second ago
    const olderThanSeven = new Date(baseNow.getTime() - (7 * 24 * 60 * 60 * 1000 + 1000)).toISOString();
    expect(getFreshnessState(olderThanSeven, baseNow)).toBe("stale");

    // 30 days ago
    const thirtyDaysAgo = new Date("2026-08-21T12:00:00Z").toISOString();
    expect(getFreshnessState(thirtyDaysAgo, baseNow)).toBe("stale");
  });
});

describe("formatCapturedDate", () => {
  const baseNow = new Date("2026-09-20T12:00:00Z");

  it("returns 'Fecha de actualización no disponible' when state is unknown", () => {
    const result = formatCapturedDate(null, baseNow);
    expect(result.state).toBe("unknown");
    expect(result.label).toBe("Fecha de actualización no disponible");
  });

  it("returns formatted date when state is fresh or stale", () => {
    const freshDate = "2026-09-18T12:00:00Z";
    const resultFresh = formatCapturedDate(freshDate, baseNow);
    expect(resultFresh.state).toBe("fresh");
    expect(resultFresh.label).not.toBe("Fecha de actualización no disponible");

    const staleDate = "2026-08-01T12:00:00Z";
    const resultStale = formatCapturedDate(staleDate, baseNow);
    expect(resultStale.state).toBe("stale");
    expect(resultStale.label).not.toBe("Fecha de actualización no disponible");
  });
});
