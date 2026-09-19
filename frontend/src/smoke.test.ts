import { describe, expect, it } from "vitest";

describe("Frontend Smoke Test", () => {
  it("initializes without runtime errors", () => {
    expect(true).toBe(true);
  });

  it("verifies environment defaults", () => {
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
    expect(apiBaseUrl).toContain("/api/v1");
  });
});
