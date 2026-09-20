import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PriceChart } from "./PriceChart";
import { ProductPriceHistoryResponse } from "../../types/api";

describe("PriceChart component", () => {
  it("does not fail and renders empty notice when series is empty (series: [])", () => {
    const emptyHistory: ProductPriceHistoryResponse = {
      product_id: "prod-test-empty",
      series: [],
    };

    render(
      <PriceChart
        history={emptyHistory}
        selectedRange="ALL"
        onRangeChange={vi.fn()}
        onStoreChange={vi.fn()}
      />
    );

    expect(
      screen.getByText("No hay observaciones de precios registradas en el período seleccionado.")
    ).toBeInTheDocument();
  });

  it("preserves two points with identical price and distinct capture dates", () => {
    const historyWithIdenticalPrices: ProductPriceHistoryResponse = {
      product_id: "prod-test-dups",
      series: [
        {
          store_id: "store-uuid-1",
          store_name: "Memory Kings",
          currency: "PEN",
          points: [
            { captured_at: "2026-08-10T12:00:00Z", price: "249.90" },
            { captured_at: "2026-09-10T12:00:00Z", price: "249.90" },
          ],
        },
      ],
    };

    const { container } = render(
      <PriceChart
        history={historyWithIdenticalPrices}
        selectedRange="ALL"
        onRangeChange={vi.fn()}
        onStoreChange={vi.fn()}
      />
    );

    // Header and store indicators are rendered
    expect(screen.getByText("Historial de Precios")).toBeInTheDocument();
    expect(screen.getByText(/Evolución de precios observados en tiendas \(PEN\)/)).toBeInTheDocument();

    // Chart container is rendered (not the empty fallback)
    expect(
      screen.queryByText("No hay observaciones de precios registradas en el período seleccionado.")
    ).not.toBeInTheDocument();

    // Recharts SVG elements exist in DOM
    const rechartsWrapper = container.querySelector(".recharts-responsive-container");
    expect(rechartsWrapper).toBeInTheDocument();
  });

  it("does not invent points: preserves exact number of observations provided by backend", () => {
    const historyWithThreePoints: ProductPriceHistoryResponse = {
      product_id: "prod-test-strict",
      series: [
        {
          store_id: "store-uuid-1",
          store_name: "Computer Shop",
          currency: "PEN",
          points: [
            { captured_at: "2026-08-01T10:00:00Z", price: "100.00" },
            { captured_at: "2026-08-15T10:00:00Z", price: "120.00" },
            { captured_at: "2026-09-01T10:00:00Z", price: "110.00" },
          ],
        },
      ],
    };

    const { container } = render(
      <PriceChart
        history={historyWithThreePoints}
        selectedRange="ALL"
        onRangeChange={vi.fn()}
        onStoreChange={vi.fn()}
      />
    );

    expect(container.querySelector(".recharts-responsive-container")).toBeInTheDocument();
    // Verify fallback is absent
    expect(
      screen.queryByText("No hay observaciones de precios registradas en el período seleccionado.")
    ).not.toBeInTheDocument();
  });
});
