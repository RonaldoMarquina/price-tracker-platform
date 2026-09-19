import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CatalogPage } from "./CatalogPage";
import * as productsApi from "../api/products";
import { ProductListResponse } from "../types/api";

vi.mock("../api/products");

describe("CatalogPage component", () => {
  const mockResponse: ProductListResponse = {
    items: [
      {
        id: "prod-1",
        name: "AMD Ryzen 5 5600X",
        brand: "AMD",
        category: "Procesadores",
        image_url: null,
        latest_price: {
          amount: "650.00",
          currency: "PEN",
          store: "Impacto",
        },
      },
      {
        id: "prod-2",
        name: "NVIDIA GeForce RTX 4060",
        brand: "NVIDIA",
        category: "Tarjetas de Video",
        image_url: null,
        latest_price: {
          amount: "1450.00",
          currency: "PEN",
          store: "Memory Kings",
        },
      },
    ],
    page: 1,
    page_size: 12,
    total: 2,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("displays skeletons while loading products", () => {
    vi.spyOn(productsApi, "getProducts").mockImplementation(
      () => new Promise(() => {}), // Pending promise
    );

    render(
      <CatalogPage
        onNavigate={vi.fn()}
        updateUrlParams={vi.fn()}
      />,
    );

    expect(screen.getByTestId("catalog-skeletons")).toBeInTheDocument();
  });

  it("renders product cards and total count when API returns results", async () => {
    vi.spyOn(productsApi, "getProducts").mockResolvedValueOnce(mockResponse);

    render(
      <CatalogPage
        onNavigate={vi.fn()}
        updateUrlParams={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("AMD Ryzen 5 5600X")).toBeInTheDocument();
      expect(screen.getByText("NVIDIA GeForce RTX 4060")).toBeInTheDocument();
      expect(screen.getByText("2 productos encontrados")).toBeInTheDocument();
    });
  });

  it("displays EmptyState with reset button when API returns zero products", async () => {
    const emptyResponse: ProductListResponse = {
      items: [],
      page: 1,
      page_size: 12,
      total: 0,
    };
    vi.spyOn(productsApi, "getProducts").mockResolvedValueOnce(emptyResponse);
    const updateUrlParams = vi.fn();

    render(
      <CatalogPage
        initialQuery="nonexistent"
        onNavigate={vi.fn()}
        updateUrlParams={updateUrlParams}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("No se encontraron productos")).toBeInTheDocument();
    });

    const resetButton = screen.getByRole("button", { name: /Restablecer filtros/i });
    fireEvent.click(resetButton);

    expect(updateUrlParams).toHaveBeenCalledWith({
      q: "",
      category: undefined,
      page: 1,
    });
  });

  it("displays ErrorAlert when API call fails and allows retry", async () => {
    const getProductsSpy = vi
      .spyOn(productsApi, "getProducts")
      .mockRejectedValueOnce(new Error("Fallo de red en la API"))
      .mockResolvedValueOnce(mockResponse);

    render(
      <CatalogPage
        onNavigate={vi.fn()}
        updateUrlParams={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Fallo de red en la API")).toBeInTheDocument();
    });

    const retryButton = screen.getByRole("button", { name: /Reintentar/i });
    fireEvent.click(retryButton);

    await waitFor(() => {
      expect(screen.getByText("AMD Ryzen 5 5600X")).toBeInTheDocument();
    });
    expect(getProductsSpy).toHaveBeenCalledTimes(2);
  });

  it("filters by category when clicking category button", async () => {
    vi.spyOn(productsApi, "getProducts").mockResolvedValue(mockResponse);
    const updateUrlParams = vi.fn();

    render(
      <CatalogPage
        onNavigate={vi.fn()}
        updateUrlParams={updateUrlParams}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("AMD Ryzen 5 5600X")).toBeInTheDocument();
    });

    const categoryBtn = screen.getByTestId("category-btn-procesadores");
    fireEvent.click(categoryBtn);

    expect(updateUrlParams).toHaveBeenCalledWith({
      q: "",
      category: "procesadores",
      page: 1,
    });
  });
});
