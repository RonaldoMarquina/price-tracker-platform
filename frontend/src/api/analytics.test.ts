import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getAnalyticsFilters,
  getAnalyticsSummary,
  getPriceSpread,
  getPriceTrends,
  getStoresCompetitiveness,
} from "./analytics";

describe("analytics API client", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("getAnalyticsFilters calls /analytics/filters", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ categories: [], stores: [], periods: ["7d", "30d"] }),
    });

    const result = await getAnalyticsFilters();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/analytics/filters"),
      expect.objectContaining({ headers: expect.anything() }),
    );
    expect(result.periods).toEqual(["7d", "30d"]);
  });

  it("getAnalyticsSummary passes category_id and signal", async () => {
    const controller = new AbortController();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ total_products_tracked: 10 }),
    });

    const result = await getAnalyticsSummary("cat-123", controller.signal);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/analytics/summary?category_id=cat-123"),
      expect.objectContaining({ signal: controller.signal }),
    );
    expect(result.total_products_tracked).toBe(10);
  });

  it("getPriceSpread passes category_id and limit", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ items: [] }),
    });

    await getPriceSpread("cat-456", 25);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/analytics/price-spread?category_id=cat-456&limit=25"),
      expect.anything(),
    );
  });

  it("getStoresCompetitiveness calls /analytics/stores-competitiveness", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ stores: [] }),
    });

    await getStoresCompetitiveness();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/analytics\/stores-competitiveness$/),
      expect.anything(),
    );
  });

  it("getPriceTrends serializes period, dates, and store_id", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ points: [] }),
    });

    await getPriceTrends({
      period: "90d",
      category_id: "cat-abc",
      store_id: "store-xyz",
    });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/analytics/price-trends");
    expect(calledUrl).toContain("period=90d");
    expect(calledUrl).toContain("category_id=cat-abc");
    expect(calledUrl).toContain("store_id=store-xyz");
  });
});
