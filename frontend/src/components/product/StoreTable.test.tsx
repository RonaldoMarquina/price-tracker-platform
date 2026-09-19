import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StoreTable } from "./StoreTable";
import { ProductStoreOut } from "../../types/api";

describe("StoreTable component", () => {
  const mockStores: ProductStoreOut[] = [
    {
      store_id: "11111111-2222-3333-4444-555555555555",
      store_name: "Memory Kings",
      product_url: "https://www.memorykings.com.pe/producto/123",
      external_sku: "MK-7800X3D",
      latest_price: {
        amount: "1899.00",
        currency: "PEN",
        availability: "in_stock",
        captured_at: "2026-09-18T15:30:00Z",
      },
    },
    {
      store_id: "22222222-3333-4444-5555-666666666666",
      store_name: "Tienda Sin Enlace",
      product_url: "", // Invalid/empty URL
      external_sku: null,
      latest_price: {
        amount: "1920.00",
        currency: "PEN",
        availability: "out_of_stock",
        captured_at: "2026-09-18T16:00:00Z",
      },
    },
  ];

  it("renders store names, prices, and availability badges", () => {
    render(<StoreTable stores={mockStores} />);

    expect(screen.getByText("Memory Kings")).toBeInTheDocument();
    expect(screen.getByText("PEN 1899.00")).toBeInTheDocument();
    expect(screen.getByText("Disponible")).toBeInTheDocument();

    expect(screen.getByText("Tienda Sin Enlace")).toBeInTheDocument();
    expect(screen.getByText("PEN 1920.00")).toBeInTheDocument();
    expect(screen.getByText("Agotado")).toBeInTheDocument();
  });

  it("shows 'Ir a la tienda' link ONLY for stores with valid product_url", () => {
    render(<StoreTable stores={mockStores} />);

    const links = screen.getAllByRole("link", { name: /Ir a la tienda/i });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "https://www.memorykings.com.pe/producto/123");
    expect(links[0]).toHaveAttribute("target", "_blank");

    // The store with empty URL should show 'No disponible'
    expect(screen.getByText("No disponible")).toBeInTheDocument();
  });

  it("renders informative notice when stores list is empty", () => {
    render(<StoreTable stores={[]} />);
    expect(screen.getByText(/No hay tiendas vinculadas a este componente/i)).toBeInTheDocument();
  });
});
