import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ProductDetailPage } from "./ProductDetailPage";
import * as productsApi from "../api/products";
import { ProductDetailOut, ProductPriceHistoryResponse } from "../types/api";

vi.mock("../api/products");

describe("ProductDetailPage component", () => {
  const mockProductDetail: ProductDetailOut = {
    id: "prod-detail-1",
    name: "Intel Core i7-14700K",
    slug: "intel-core-i7-14700k",
    brand: "Intel",
    model: "BX8071514700K",
    category: {
      id: "cat-1",
      name: "Procesadores",
      slug: "processors",
    },
    image_url: null,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
    stores: [
      {
        store_id: "store-1",
        store_name: "SercoPlus",
        product_url: "https://sercoplus.com/i7-14700k",
        external_sku: "SP-14700K",
        latest_price: {
          amount: "1720.00",
          currency: "PEN",
          availability: "in_stock",
          captured_at: "2026-09-18T10:00:00Z",
        },
      },
      {
        store_id: "store-2",
        store_name: "CyC Computer",
        product_url: "https://cyccomputer.pe/i7-14700k",
        external_sku: "CYC-14700K",
        latest_price: {
          amount: "1780.00",
          currency: "PEN",
          availability: "in_stock",
          captured_at: "2026-09-18T11:00:00Z",
        },
      },
    ],
  };

  const mockPriceHistory: ProductPriceHistoryResponse = {
    product_id: "prod-detail-1",
    series: [
      {
        store_id: "store-1",
        store_name: "SercoPlus",
        currency: "PEN",
        points: [
          { captured_at: "2026-08-01T10:00:00Z", price: "1850.00" },
          { captured_at: "2026-09-01T10:00:00Z", price: "1720.00" },
        ],
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("displays skeletons while loading detail and price history", () => {
    vi.spyOn(productsApi, "getProductById").mockImplementation(() => new Promise(() => {}));
    vi.spyOn(productsApi, "getPriceHistory").mockImplementation(() => new Promise(() => {}));

    render(<ProductDetailPage productId="prod-detail-1" onNavigate={vi.fn()} />);

    expect(screen.getByTestId("detail-skeleton")).toBeInTheDocument();
  });

  it("renders product name, category, model, and calculated lowest price", async () => {
    vi.spyOn(productsApi, "getProductById").mockResolvedValueOnce(mockProductDetail);
    vi.spyOn(productsApi, "getPriceHistory").mockResolvedValueOnce(mockPriceHistory);

    render(<ProductDetailPage productId="prod-detail-1" onNavigate={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Intel Core i7-14700K" })).toBeInTheDocument();
      expect(screen.getByText(/BX8071514700K/)).toBeInTheDocument();
      expect(screen.getAllByText(/1720\.00/).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/En SercoPlus/i)).toBeInTheDocument();
      expect(screen.getByText("Historial de Precios")).toBeInTheDocument();
    });
  });

  it("updates price history when switching time range filters (1M)", async () => {
    vi.spyOn(productsApi, "getProductById").mockResolvedValueOnce(mockProductDetail);
    const historySpy = vi
      .spyOn(productsApi, "getPriceHistory")
      .mockResolvedValue(mockPriceHistory);

    render(<ProductDetailPage productId="prod-detail-1" onNavigate={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("Historial de Precios")).toBeInTheDocument();
    });

    const oneMonthBtn = screen.getByRole("button", { name: "1 Mes" });
    fireEvent.click(oneMonthBtn);

    await waitFor(() => {
      // Expect second call to have from and to formatted as YYYY-MM-DD
      expect(historySpy).toHaveBeenCalledTimes(2);
      const callArgs = historySpy.mock.calls[1];
      expect(callArgs[0]).toBe("prod-detail-1");
      expect(callArgs[1]?.from).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(callArgs[1]?.to).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });
  });

  it("navigates back to catalog when clicking 'Volver al catálogo'", async () => {
    vi.spyOn(productsApi, "getProductById").mockResolvedValueOnce(mockProductDetail);
    vi.spyOn(productsApi, "getPriceHistory").mockResolvedValueOnce(mockPriceHistory);
    const onNavigate = vi.fn();

    render(<ProductDetailPage productId="prod-detail-1" onNavigate={onNavigate} />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Intel Core i7-14700K" })).toBeInTheDocument();
    });

    const backButton = screen.getByRole("button", { name: /Volver al catálogo/i });
    fireEvent.click(backButton);

    expect(onNavigate).toHaveBeenCalledWith("/products");
  });
});
