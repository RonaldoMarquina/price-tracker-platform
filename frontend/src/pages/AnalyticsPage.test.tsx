import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as analyticsApi from "../api/analytics";
import {
  AnalyticsFiltersResponse,
  AnalyticsSummaryResponse,
  PriceSpreadResponse,
  PriceTrendsResponse,
  StoresCompetitivenessResponse,
} from "../types/analytics";
import { AnalyticsPage } from "./AnalyticsPage";

describe("AnalyticsPage Integration", () => {
  const mockFilters: AnalyticsFiltersResponse = {
    categories: [
      { id: "cat-1", name: "Procesadores" },
      { id: "cat-2", name: "Placas Madre" },
    ],
    stores: [
      { id: "store-1", name: "Memory Kings", is_active: true },
      { id: "store-2", name: "Sercoplus", is_active: false },
    ],
    periods: ["7d", "30d", "90d", "all"],
  };

  const mockSummary: AnalyticsSummaryResponse = {
    as_of: "2026-09-20T20:00:00Z",
    category_id: null,
    total_products_tracked: 20,
    products_with_valid_offer_count: 10,
    comparable_products_count: 4,
    savings: {
      average_savings_amount: "50.00",
      average_savings_percentage: "12.50",
      max_savings_product: {
        product_id: "prod-1",
        product_name: "Ryzen 7 5800X",
        best_price: "850.00",
        best_store: "Memory Kings",
        best_price_condition: null,
        worst_price: "950.00",
        worst_store: "NECS Ayacucho",
        worst_price_condition: null,
        savings_amount: "100.00",
        savings_percentage: "10.53",
      },
    },
    most_competitive_store: {
      store_id: "store-1",
      store_name: "Memory Kings",
      best_price_count: 6,
      best_price_share_percentage: "60.00",
    },
    freshness: {
      total_active_associations: 30,
      fresh_count: 25,
      stale_count: 1,
      unknown_count: 4,
      no_observation_count: 4,
      freshness_rate: "83.33",
    },
  };

  const mockSpread: PriceSpreadResponse = {
    as_of: "2026-09-20T20:00:00Z",
    category_id: null,
    total_comparable_products: 1,
    limit: 10,
    items: [
      {
        product_id: "prod-1",
        product_name: "Ryzen 7 5800X",
        category_name: "Procesadores",
        best_offer: {
          amount: "850.00",
          currency: "PEN",
          store_id: "store-1",
          store_name: "Memory Kings",
          price_condition: "standard",
          captured_at: "2026-09-20T10:00:00Z",
        },
        worst_offer: {
          amount: "950.00",
          currency: "PEN",
          store_id: "store-2",
          store_name: "NECS Ayacucho",
          price_condition: "standard",
          captured_at: "2026-09-20T10:00:00Z",
        },
        savings_amount: "100.00",
        savings_percentage: "10.53",
        valid_offers_count: 2,
      },
    ],
  };

  const mockStores: StoresCompetitivenessResponse = {
    as_of: "2026-09-20T20:00:00Z",
    category_id: null,
    products_with_valid_offer_count: 10,
    stores: [
      {
        store_id: "store-1",
        store_name: "Memory Kings",
        is_active: true,
        total_associations: 15,
        observed_associations: 14,
        no_observation_count: 1,
        best_price_count: 6,
        best_price_share_percentage: "100.00",
        in_stock_count: 12,
        in_stock_percentage: "85.71",
        out_of_stock_count: 2,
        out_of_stock_percentage: "14.29",
        unknown_count: 0,
        unknown_percentage: "0.00",
        price_conditions: { standard: 14 },
      },
    ],
  };

  const mockTrends: PriceTrendsResponse = {
    as_of: "2026-09-20T20:00:00Z",
    period: "30d",
    from_date: null,
    to_date: null,
    category_id: null,
    store_id: null,
    points: [
      {
        date: "2026-09-19",
        average_price: "900.00",
        median_price: "900.00",
        min_price: "850.00",
        max_price: "950.00",
        associations_count: 2,
        products_count: 1,
      },
    ],
  };

  beforeEach(() => {
    vi.spyOn(analyticsApi, "getAnalyticsFilters").mockResolvedValue(mockFilters);
    vi.spyOn(analyticsApi, "getAnalyticsSummary").mockResolvedValue(mockSummary);
    vi.spyOn(analyticsApi, "getPriceSpread").mockResolvedValue(mockSpread);
    vi.spyOn(analyticsApi, "getStoresCompetitiveness").mockResolvedValue(mockStores);
    vi.spyOn(analyticsApi, "getPriceTrends").mockResolvedValue(mockTrends);

    // Reset window.location
    window.history.pushState({}, "", "/analytics");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads all 5 endpoints on initial mount and displays Peruvian local timestamp", async () => {
    render(<AnalyticsPage onNavigate={vi.fn()} />);

    // Check header and Peruvian time
    expect(screen.getByText("Dashboard Analítico")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Datos calculados al 20\/09\/2026 15:00 — hora de Perú/i)).toBeInTheDocument();
    });

    // Check 5 endpoints called once
    expect(analyticsApi.getAnalyticsFilters).toHaveBeenCalledTimes(1);
    expect(analyticsApi.getAnalyticsSummary).toHaveBeenCalledTimes(1);
    expect(analyticsApi.getPriceSpread).toHaveBeenCalledTimes(1);
    expect(analyticsApi.getStoresCompetitiveness).toHaveBeenCalledTimes(1);
    expect(analyticsApi.getPriceTrends).toHaveBeenCalledTimes(1);

    // Check rendered components
    expect(screen.getByText("12.50%")).toBeInTheDocument();
    expect(screen.getAllByText("Ryzen 7 5800X").length).toBeGreaterThanOrEqual(1);
  });

  it("selectively updates endpoints on category change (does NOT re-call filters)", async () => {
    render(<AnalyticsPage onNavigate={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("12.50%")).toBeInTheDocument());

    const catSelect = screen.getByLabelText("Filtrar por categoría");
    fireEvent.change(catSelect, { target: { value: "cat-1" } });

    // Summary, spread, stores and trends must be called with cat-1
    await waitFor(() => {
      expect(analyticsApi.getAnalyticsSummary).toHaveBeenCalledWith("cat-1", expect.anything());
    });

    expect(analyticsApi.getAnalyticsSummary).toHaveBeenCalledTimes(2);
    expect(analyticsApi.getPriceSpread).toHaveBeenCalledTimes(2);
    expect(analyticsApi.getStoresCompetitiveness).toHaveBeenCalledTimes(2);
    expect(analyticsApi.getPriceTrends).toHaveBeenCalledTimes(2);

    // Filters must still be called ONLY ONCE
    expect(analyticsApi.getAnalyticsFilters).toHaveBeenCalledTimes(1);
  });

  it("selectively updates ONLY price-trends on period change", async () => {
    render(<AnalyticsPage onNavigate={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("12.50%")).toBeInTheDocument());

    const tab7d = screen.getByRole("tab", { name: "7d" });
    fireEvent.click(tab7d);

    await waitFor(() => {
      expect(analyticsApi.getPriceTrends).toHaveBeenCalledWith(
        expect.objectContaining({ period: "7d" }),
        expect.anything(),
      );
    });

    // Trends called second time
    expect(analyticsApi.getPriceTrends).toHaveBeenCalledTimes(2);

    // Summary, Spread, Stores, Filters counts MUST NOT INCREASE
    expect(analyticsApi.getAnalyticsSummary).toHaveBeenCalledTimes(1);
    expect(analyticsApi.getPriceSpread).toHaveBeenCalledTimes(1);
    expect(analyticsApi.getStoresCompetitiveness).toHaveBeenCalledTimes(1);
    expect(analyticsApi.getAnalyticsFilters).toHaveBeenCalledTimes(1);
  });

  it("selectively updates ONLY price-trends on store change", async () => {
    render(<AnalyticsPage onNavigate={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("12.50%")).toBeInTheDocument());

    const storeSelect = screen.getByLabelText("Filtrar tendencias por tienda");
    fireEvent.change(storeSelect, { target: { value: "store-1" } });

    await waitFor(() => {
      expect(analyticsApi.getPriceTrends).toHaveBeenCalledWith(
        expect.objectContaining({ store_id: "store-1" }),
        expect.anything(),
      );
    });

    expect(analyticsApi.getPriceTrends).toHaveBeenCalledTimes(2);
    expect(analyticsApi.getAnalyticsSummary).toHaveBeenCalledTimes(1);
  });

  it("reloads the 4 analytical modules on 'Actualizar' click", async () => {
    render(<AnalyticsPage onNavigate={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("12.50%")).toBeInTheDocument());

    const refreshBtn = screen.getByRole("button", { name: /actualizar/i });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(analyticsApi.getAnalyticsSummary).toHaveBeenCalledTimes(2);
    });

    expect(analyticsApi.getPriceSpread).toHaveBeenCalledTimes(2);
    expect(analyticsApi.getStoresCompetitiveness).toHaveBeenCalledTimes(2);
    expect(analyticsApi.getPriceTrends).toHaveBeenCalledTimes(2);

    // Filters must still be called only once
    expect(analyticsApi.getAnalyticsFilters).toHaveBeenCalledTimes(1);
  });

  it("handles race conditions between rapid category changes (latest request wins)", async () => {
    let resolveCat1: (val: AnalyticsSummaryResponse) => void = () => {};
    let resolveCat2: (val: AnalyticsSummaryResponse) => void = () => {};

    const summaryMock = vi.spyOn(analyticsApi, "getAnalyticsSummary").mockImplementation((catId) => {
      if (catId === "cat-1") {
        return new Promise((resolve) => {
          resolveCat1 = resolve;
        });
      }
      if (catId === "cat-2") {
        return new Promise((resolve) => {
          resolveCat2 = resolve;
        });
      }
      return Promise.resolve(mockSummary);
    });

    render(<AnalyticsPage onNavigate={vi.fn()} />);
    await waitFor(() => expect(summaryMock).toHaveBeenCalledTimes(1));

    const catSelect = screen.getByLabelText("Filtrar por categoría");

    // Rapid selection: cat-1 then cat-2
    fireEvent.change(catSelect, { target: { value: "cat-1" } });
    fireEvent.change(catSelect, { target: { value: "cat-2" } });

    // Resolve cat-2 FIRST with 25.00%
    const summaryCat2: AnalyticsSummaryResponse = {
      ...mockSummary,
      savings: { ...mockSummary.savings, average_savings_percentage: "25.00" },
    };
    resolveCat2(summaryCat2);

    await waitFor(() => {
      expect(screen.getByText("25.00%")).toBeInTheDocument();
    });

    // Now resolve cat-1 LATER with 5.00% (stale response)
    const summaryCat1: AnalyticsSummaryResponse = {
      ...mockSummary,
      savings: { ...mockSummary.savings, average_savings_percentage: "5.00" },
    };
    resolveCat1(summaryCat1);

    // Assert that cat-2's data is RETAINED and NOT overwritten by the stale cat-1 response
    expect(screen.getByText("25.00%")).toBeInTheDocument();
    expect(screen.queryByText("5.00%")).not.toBeInTheDocument();
  });

  it("isolates module errors without breaking the rest of the dashboard", async () => {
    // Make only getPriceTrends fail
    vi.spyOn(analyticsApi, "getPriceTrends").mockRejectedValue(new Error("Timeout en tendencias"));

    render(<AnalyticsPage onNavigate={vi.fn()} />);



    await waitFor(() => {
      expect(screen.getByText("12.50%")).toBeInTheDocument();
      expect(screen.getAllByText("Ryzen 7 5800X").length).toBeGreaterThanOrEqual(1);
    });

    // Trends section shows error and retry button
    expect(screen.getByText(/Error al cargar las tendencias de precios: Timeout en tendencias/i)).toBeInTheDocument();

    // Now mock recovery and click Reintentar
    vi.spyOn(analyticsApi, "getPriceTrends").mockResolvedValueOnce(mockTrends);
    const retryButtons = screen.getAllByRole("button", { name: "Reintentar" });
    fireEvent.click(retryButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Resumen de datos históricos diarios")).toBeInTheDocument();
    });

    // Verify summary was NOT re-fetched during trends retry
    expect(analyticsApi.getAnalyticsSummary).toHaveBeenCalledTimes(1);
  });
});
