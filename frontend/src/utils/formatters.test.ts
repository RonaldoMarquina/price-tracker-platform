import { describe, expect, it } from "vitest";
import {
  formatAnalyticsAsOf,
  formatCurrencyPEN,
  formatPercentage,
} from "./formatters";

describe("formatAnalyticsAsOf", () => {
  it("formats valid UTC ISO date into Lima time (America/Lima, UTC-5)", () => {
    // 2026-09-20T20:49:03.329777Z is 15:49 in America/Lima
    const result = formatAnalyticsAsOf("2026-09-20T20:49:03.329777Z");
    expect(result).toBe("Datos calculados al 20/09/2026 15:49 — hora de Perú");
  });

  it("handles midnight crossing correctly in Lima timezone", () => {
    // 2026-09-21T02:30:00Z is 2026-09-20 21:30 in America/Lima
    const result = formatAnalyticsAsOf("2026-09-21T02:30:00Z");
    expect(result).toBe("Datos calculados al 20/09/2026 21:30 — hora de Perú");
  });

  it("returns 'Fecha de cálculo no disponible' for null, undefined, empty or invalid dates", () => {
    expect(formatAnalyticsAsOf(null)).toBe("Fecha de cálculo no disponible");
    expect(formatAnalyticsAsOf(undefined)).toBe("Fecha de cálculo no disponible");
    expect(formatAnalyticsAsOf("")).toBe("Fecha de cálculo no disponible");
    expect(formatAnalyticsAsOf("not-a-date")).toBe("Fecha de cálculo no disponible");
  });
});

describe("formatCurrencyPEN", () => {
  it("formats string and numeric amounts into PEN", () => {
    expect(formatCurrencyPEN("102.50")).toContain("102");
    expect(formatCurrencyPEN(2500)).toContain("2");
    expect(formatCurrencyPEN(null)).toBe("S/ --");
    expect(formatCurrencyPEN(undefined)).toBe("S/ --");
    expect(formatCurrencyPEN("invalid")).toBe("S/ --");
  });
});

describe("formatPercentage", () => {
  it("formats percentages with 2 decimals", () => {
    expect(formatPercentage("8.3912")).toBe("8.39%");
    expect(formatPercentage(69.23)).toBe("69.23%");
    expect(formatPercentage(null)).toBe("0.00%");
    expect(formatPercentage(undefined)).toBe("0.00%");
  });
});
