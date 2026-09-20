import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { App } from "./App";
import * as analyticsApi from "./api/analytics";
import * as productsApi from "./api/products";

vi.mock("./api/products");
vi.mock("./api/analytics");

describe("App component and client navigation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.pushState({}, "", "/");
    vi.spyOn(productsApi, "getProducts").mockResolvedValue({
      items: [],
      page: 1,
      page_size: 4,
      total: 0,
    });
    vi.spyOn(analyticsApi, "getAnalyticsFilters").mockResolvedValue({
      categories: [],
      stores: [],
      periods: ["7d", "30d", "90d", "all"],
    });
    vi.spyOn(analyticsApi, "getAnalyticsSummary").mockResolvedValue({
      as_of: "2026-09-20T20:00:00Z",
      category_id: null,
      total_products_tracked: 0,
      products_with_valid_offer_count: 0,
      comparable_products_count: 0,
      savings: {
        average_savings_amount: "0.00",
        average_savings_percentage: "0.00",
        max_savings_product: null,
      },
      most_competitive_store: null,
      freshness: {
        total_active_associations: 0,
        fresh_count: 0,
        stale_count: 0,
        unknown_count: 0,
        no_observation_count: 0,
        freshness_rate: "0.00",
      },
    });
    vi.spyOn(analyticsApi, "getPriceSpread").mockResolvedValue({
      as_of: "2026-09-20T20:00:00Z",
      category_id: null,
      total_comparable_products: 0,
      limit: 10,
      items: [],
    });
    vi.spyOn(analyticsApi, "getStoresCompetitiveness").mockResolvedValue({
      as_of: "2026-09-20T20:00:00Z",
      category_id: null,
      products_with_valid_offer_count: 0,
      stores: [],
    });
    vi.spyOn(analyticsApi, "getPriceTrends").mockResolvedValue({
      as_of: "2026-09-20T20:00:00Z",
      period: "30d",
      from_date: null,
      to_date: null,
      category_id: null,
      store_id: null,
      points: [],
    });
  });

  it("renders Navbar, Footer and Home page by default", async () => {
    render(<App />);

    expect(screen.getAllByText("PriceTrack").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Encuentra el mejor precio para tu próxima PC/i)).toBeInTheDocument();
    expect(screen.getByText(/Portal académico y funcional/i)).toBeInTheDocument();
  });

  it("renders catalog page when navigating to /products", async () => {
    window.history.pushState({}, "", "/products");
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Catálogo de Componentes")).toBeInTheDocument();
    });
  });

  it("renders analytics page when clicking 'Analítica' in Navbar", async () => {
    render(<App />);

    const analyticsLink = screen.getByRole("link", { name: /analítica/i });
    expect(analyticsLink).toBeInTheDocument();

    analyticsLink.click();

    await waitFor(() => {
      expect(screen.getByText("Dashboard Analítico")).toBeInTheDocument();
    });
  });
});
