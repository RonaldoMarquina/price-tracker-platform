import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ProductCard } from "./ProductCard";
import { ProductListItemOut } from "../../types/api";

describe("ProductCard component", () => {
  const mockProduct: ProductListItemOut = {
    id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    name: "AMD Ryzen 7 7800X3D",
    brand: "AMD",
    category: "Procesadores",
    image_url: "https://example.com/images/ryzen.jpg",
    latest_price: {
      amount: "1850.00",
      currency: "PEN",
      store: "Impacto",
    },
  };

  it("renders product name, category badge, brand and latest price correctly", () => {
    const handleSelect = vi.fn();
    render(<ProductCard product={mockProduct} onSelect={handleSelect} />);

    expect(screen.getByText("AMD Ryzen 7 7800X3D")).toBeInTheDocument();
    expect(screen.getByText("Procesadores")).toBeInTheDocument();
    expect(screen.getByText("AMD")).toBeInTheDocument();
    expect(screen.getByText("PEN 1850.00")).toBeInTheDocument();
    expect(screen.getByText(/Impacto/)).toBeInTheDocument();
  });

  it("renders authoritative best_price with cash_or_bank_transfer badge", () => {
    const productWithBestPrice: ProductListItemOut = {
      ...mockProduct,
      best_price: {
        amount: "1799.00",
        currency: "PEN",
        store_id: "store-uuid-1",
        store_name: "Computer Shop",
        price_condition: "cash_or_bank_transfer",
        captured_at: new Date().toISOString(),
      },
    };
    render(<ProductCard product={productWithBestPrice} onSelect={vi.fn()} />);

    expect(screen.getByText("PEN 1799.00")).toBeInTheDocument();
    expect(screen.getByText(/Computer Shop/)).toBeInTheDocument();
    expect(screen.getByText("Efectivo / Transf.")).toBeInTheDocument();
  });

  it("renders fallback message when no price offer is available", () => {
    const productWithoutPrice: ProductListItemOut = {
      ...mockProduct,
      best_price: null,
      latest_price: null,
    };
    render(<ProductCard product={productWithoutPrice} onSelect={vi.fn()} />);

    expect(screen.getByText("Sin oferta disponible")).toBeInTheDocument();
  });

  it("triggers onSelect callback with product ID when clicked", () => {
    const handleSelect = vi.fn();
    render(<ProductCard product={mockProduct} onSelect={handleSelect} />);

    const card = screen.getByTestId(`product-card-${mockProduct.id}`);
    fireEvent.click(card);

    expect(handleSelect).toHaveBeenCalledWith(mockProduct.id);
  });

  it("renders 'Disponible en 1 tienda' and 'Oferta registrada:' without 'Mejor precio:' for single offer", () => {
    const singleOfferProduct: ProductListItemOut = {
      ...mockProduct,
      active_offers_count: 1,
      has_multiple_offers: false,
      best_price: {
        amount: "1850.00",
        currency: "PEN",
        store_id: "store-uuid-1",
        store_name: "NECS Ayacucho",
        price_condition: "standard",
        captured_at: new Date().toISOString(),
      },
    };
    render(<ProductCard product={singleOfferProduct} onSelect={vi.fn()} />);

    expect(screen.getByText("Disponible en 1 tienda")).toBeInTheDocument();
    expect(screen.getByText("Oferta registrada:")).toBeInTheDocument();
    expect(screen.queryByText("Mejor precio:")).not.toBeInTheDocument();
  });

  it("renders 'Disponible en 2 tiendas' and 'Mejor precio:' when multiple offers are active", () => {
    const multiOfferProduct: ProductListItemOut = {
      ...mockProduct,
      active_offers_count: 2,
      has_multiple_offers: true,
      best_price: {
        amount: "1799.00",
        currency: "PEN",
        store_id: "store-uuid-1",
        store_name: "Memory Kings",
        price_condition: "standard",
        captured_at: new Date().toISOString(),
      },
    };
    render(<ProductCard product={multiOfferProduct} onSelect={vi.fn()} />);

    expect(screen.getByText("Disponible en 2 tiendas")).toBeInTheDocument();
    expect(screen.getByText("Mejor precio:")).toBeInTheDocument();
  });

  it("switches to local SVG placeholder fallback when image onError fires", () => {
    render(<ProductCard product={mockProduct} onSelect={vi.fn()} />);

    const img = screen.getByAltText(mockProduct.name);
    expect(img).toBeInTheDocument();

    fireEvent.error(img);

    expect(screen.getByText("Sin imagen")).toBeInTheDocument();
  });
});
