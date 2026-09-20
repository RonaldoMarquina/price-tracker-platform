import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalyticsSummaryResponse } from "../../types/analytics";
import { AnalyticsKpis } from "./AnalyticsKpis";

describe("AnalyticsKpis", () => {
  const mockSummary: AnalyticsSummaryResponse = {
    as_of: "2026-09-20T20:00:00Z",
    category_id: null,
    total_products_tracked: 38,
    products_with_valid_offer_count: 13,
    comparable_products_count: 5,
    savings: {
      average_savings_amount: "17.61",
      average_savings_percentage: "8.39",
      max_savings_product: {
        product_id: "prod-1",
        product_name: 'Monitor ASUS VY279HGR 27" IPS',
        best_price: "392.00",
        best_store: "Memory Kings",
        best_price_condition: null,
        worst_price: "430.00",
        worst_store: "NECS Ayacucho",
        worst_price_condition: null,
        savings_amount: "38.00",
        savings_percentage: "8.84",
      },
    },
    most_competitive_store: {
      store_id: "store-1",
      store_name: "Memory Kings",
      best_price_count: 9,
      best_price_share_percentage: "69.23",
    },
    freshness: {
      total_active_associations: 42,
      fresh_count: 28,
      stale_count: 2,
      unknown_count: 12,
      no_observation_count: 12,
      freshness_rate: "66.67",
    },
  };

  it("renders all 4 cards with formatted values", () => {
    render(<AnalyticsKpis summary={mockSummary} isLoading={false} error={null} />);

    // Card 1: Ahorro Promedio
    expect(screen.getByText("Ahorro Promedio")).toBeInTheDocument();
    expect(screen.getByText("8.39%")).toBeInTheDocument();
    expect(screen.getByText(/5 productos comparables/i)).toBeInTheDocument();

    // Card 2: Mayor Ahorro
    expect(screen.getByText("Mayor Ahorro")).toBeInTheDocument();
    expect(screen.getByText(/38/)).toBeInTheDocument();
    expect(screen.getByText(/Monitor ASUS/i)).toBeInTheDocument();

    // Card 3: Tienda Más Competitiva
    expect(screen.getByText("Tienda Más Competitiva")).toBeInTheDocument();
    expect(screen.getByText("Memory Kings")).toBeInTheDocument();
    expect(screen.getByText(/69.23%/)).toBeInTheDocument();

    // Card 4: Calidad de Datos
    expect(screen.getByText("Calidad de Datos")).toBeInTheDocument();
    expect(screen.getByText("66.67%")).toBeInTheDocument();
    expect(screen.getByText(/28 de 42 ofertas frescas/i)).toBeInTheDocument();
    expect(screen.getByText(/2 obsoletas/i)).toBeInTheDocument();
  });

  it("handles null max_savings_product and null most_competitive_store", () => {
    const emptySummary: AnalyticsSummaryResponse = {
      ...mockSummary,
      savings: {
        average_savings_amount: "0.00",
        average_savings_percentage: "0.00",
        max_savings_product: null,
      },
      most_competitive_store: null,
    };

    render(<AnalyticsKpis summary={emptySummary} isLoading={false} error={null} />);

    expect(screen.getByText("Sin brecha")).toBeInTheDocument();
    expect(screen.getByText("Sin datos")).toBeInTheDocument();
  });

  it("renders loading skeleton when isLoading is true", () => {
    render(<AnalyticsKpis summary={null} isLoading={true} error={null} />);
    expect(screen.getByLabelText("Cargando indicadores clave")).toBeInTheDocument();
  });

  it("renders error box and calls onRetry when error is present", () => {
    const onRetry = vi.fn();
    render(<AnalyticsKpis summary={null} isLoading={false} error="Fallo de red" onRetry={onRetry} />);

    expect(screen.getByText(/Error al cargar los indicadores clave: Fallo de red/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalled();
  });
});
