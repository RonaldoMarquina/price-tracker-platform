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

  it("renders fallback message when latest_price is null", () => {
    const productWithoutPrice: ProductListItemOut = {
      ...mockProduct,
      latest_price: null,
    };
    render(<ProductCard product={productWithoutPrice} onSelect={vi.fn()} />);

    expect(screen.getByText("Sin precio registrado")).toBeInTheDocument();
  });

  it("triggers onSelect callback with product ID when clicked", () => {
    const handleSelect = vi.fn();
    render(<ProductCard product={mockProduct} onSelect={handleSelect} />);

    const card = screen.getByTestId(`product-card-${mockProduct.id}`);
    fireEvent.click(card);

    expect(handleSelect).toHaveBeenCalledWith(mockProduct.id);
  });
});
