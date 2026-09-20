import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PriceSpreadItemOut } from "../../types/analytics";
import { PriceSpreadTable } from "./PriceSpreadTable";

describe("PriceSpreadTable", () => {
  const mockItems: PriceSpreadItemOut[] = [
    {
      product_id: "prod-1",
      product_name: "AMD Ryzen 7 5800X",
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
        price_condition: "cash_or_bank_transfer",
        captured_at: "2026-09-20T10:00:00Z",
      },
      savings_amount: "100.00",
      savings_percentage: "10.53",
      valid_offers_count: 3,
    },
  ];

  it("renders product row with details and navigates on link click", () => {
    const onNavigate = vi.fn();
    render(
      <PriceSpreadTable
        items={mockItems}
        isLoading={false}
        error={null}
        onNavigate={onNavigate}
      />,
    );

    expect(screen.getByText("AMD Ryzen 7 5800X")).toBeInTheDocument();
    expect(screen.getByText("Procesadores")).toBeInTheDocument();
    expect(screen.getByText(/850/)).toBeInTheDocument();
    expect(screen.getByText(/950/)).toBeInTheDocument();
    expect(screen.getByText(/100/)).toBeInTheDocument();
    expect(screen.getByText(/10.53%/)).toBeInTheDocument();
    expect(screen.getByText("Efectivo/Transf.")).toBeInTheDocument();

    fireEvent.click(screen.getByText("AMD Ryzen 7 5800X"));
    expect(onNavigate).toHaveBeenCalledWith("/products/prod-1");
  });

  it("renders empty state when items is empty", () => {
    render(
      <PriceSpreadTable
        items={[]}
        isLoading={false}
        error={null}
        onNavigate={vi.fn()}
      />,
    );

    expect(screen.getByText("Sin dispersión de precios detectada")).toBeInTheDocument();
  });

  it("renders loading skeleton when isLoading is true", () => {
    render(
      <PriceSpreadTable
        items={[]}
        isLoading={true}
        error={null}
        onNavigate={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Cargando tabla de dispersión")).toBeInTheDocument();
  });

  it("renders error box and calls onRetry when error occurs", () => {
    const onRetry = vi.fn();
    render(
      <PriceSpreadTable
        items={[]}
        isLoading={false}
        error="Error al cargar tabla"
        onNavigate={vi.fn()}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText(/Error al cargar el ranking de ahorro: Error al cargar tabla/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalled();
  });
});
