import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StoreCompetitivenessItemOut } from "../../types/analytics";
import { StoreCompetitivenessGrid } from "./StoreCompetitivenessGrid";

describe("StoreCompetitivenessGrid", () => {
  const mockStores: StoreCompetitivenessItemOut[] = [
    {
      store_id: "store-1",
      store_name: "Memory Kings",
      is_active: true,
      total_associations: 10,
      observed_associations: 9,
      no_observation_count: 1,
      best_price_count: 7,
      best_price_share_percentage: "70.00",
      in_stock_count: 8,
      in_stock_percentage: "80.00",
      out_of_stock_count: 1,
      out_of_stock_percentage: "10.00",
      unknown_count: 1,
      unknown_percentage: "10.00",
      price_conditions: {
        standard: 9,
      },
    },
    {
      store_id: "store-2",
      store_name: "Sercoplus",
      is_active: false,
      total_associations: 5,
      observed_associations: 5,
      no_observation_count: 0,
      best_price_count: 0,
      best_price_share_percentage: "0.00",
      in_stock_count: 2,
      in_stock_percentage: "40.00",
      out_of_stock_count: 3,
      out_of_stock_percentage: "60.00",
      unknown_count: 0,
      unknown_percentage: "0.00",
      price_conditions: {
        standard: 5,
      },
    },
  ];

  it("renders active and inactive stores with correct metrics and badges", () => {
    render(
      <StoreCompetitivenessGrid
        stores={mockStores}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getByText("Memory Kings")).toBeInTheDocument();
    expect(screen.getByText("70.00%")).toBeInTheDocument();
    expect(screen.getByText(/7 ofertas ganadoras/i)).toBeInTheDocument();
    expect(screen.getByText(/9 \/ 10 cubiertos/i)).toBeInTheDocument();

    // Sercoplus (inactive)
    expect(screen.getByText("Sercoplus")).toBeInTheDocument();
    expect(screen.getByText("Inactiva")).toBeInTheDocument();
  });

  it("renders empty state when stores list is empty", () => {
    render(
      <StoreCompetitivenessGrid
        stores={[]}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getByText("Sin datos de tiendas")).toBeInTheDocument();
  });

  it("renders loading skeletons when isLoading is true", () => {
    render(
      <StoreCompetitivenessGrid
        stores={[]}
        isLoading={true}
        error={null}
      />,
    );

    expect(screen.getByLabelText("Cargando competitividad de tiendas")).toBeInTheDocument();
  });

  it("renders error box and calls onRetry when error occurs", () => {
    const onRetry = vi.fn();
    render(
      <StoreCompetitivenessGrid
        stores={[]}
        isLoading={false}
        error="Fallo al cargar tiendas"
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText(/Error al cargar la competitividad de tiendas: Fallo al cargar tiendas/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalled();
  });
});
