import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { App } from "./App";
import * as productsApi from "./api/products";

vi.mock("./api/products");

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
});
