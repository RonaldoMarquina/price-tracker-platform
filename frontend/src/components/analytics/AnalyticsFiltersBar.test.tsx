import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CategoryFilterItem, StoreFilterItem } from "../../types/analytics";
import { AnalyticsFiltersBar } from "./AnalyticsFiltersBar";

describe("AnalyticsFiltersBar", () => {
  const mockCategories: CategoryFilterItem[] = [
    { id: "cat-1", name: "Procesadores" },
    { id: "cat-2", name: "Tarjetas de Video" },
  ];

  const mockStores: StoreFilterItem[] = [
    { id: "store-1", name: "Memory Kings", is_active: true },
    { id: "store-2", name: "Sercoplus", is_active: false },
  ];

  it("renders category and store selects with options", () => {
    render(
      <AnalyticsFiltersBar
        categories={mockCategories}
        stores={mockStores}
        periods={["7d", "30d", "90d", "all"]}
        selectedCategory=""
        selectedStore=""
        selectedPeriod="30d"
        customFrom=""
        customTo=""
        isLoading={false}
        onCategoryChange={vi.fn()}
        onStoreChange={vi.fn()}
        onPeriodPresetChange={vi.fn()}
        onCustomDatesChange={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    const catSelect = screen.getByLabelText("Filtrar por categoría");
    expect(catSelect).toBeInTheDocument();
    expect(screen.getByText("Todas las categorías")).toBeInTheDocument();
    expect(screen.getByText("Procesadores")).toBeInTheDocument();
    expect(screen.getByText("Tarjetas de Video")).toBeInTheDocument();

    const storeSelect = screen.getByLabelText("Filtrar tendencias por tienda");
    expect(storeSelect).toBeInTheDocument();
    expect(screen.getByText("Todas las tiendas")).toBeInTheDocument();
    expect(screen.getByText("Memory Kings")).toBeInTheDocument();
    expect(screen.getByText("Sercoplus (Inactiva)")).toBeInTheDocument();
  });

  it("triggers onCategoryChange when a category is selected", () => {
    const onCategoryChange = vi.fn();
    render(
      <AnalyticsFiltersBar
        categories={mockCategories}
        stores={mockStores}
        periods={["7d", "30d"]}
        selectedCategory=""
        selectedStore=""
        selectedPeriod="30d"
        customFrom=""
        customTo=""
        isLoading={false}
        onCategoryChange={onCategoryChange}
        onStoreChange={vi.fn()}
        onPeriodPresetChange={vi.fn()}
        onCustomDatesChange={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("Filtrar por categoría"), {
      target: { value: "cat-1" },
    });
    expect(onCategoryChange).toHaveBeenCalledWith("cat-1");
  });

  it("triggers onPeriodPresetChange when clicking period tabs", () => {
    const onPeriodPresetChange = vi.fn();
    render(
      <AnalyticsFiltersBar
        categories={mockCategories}
        stores={mockStores}
        periods={["7d", "30d", "90d", "all"]}
        selectedCategory=""
        selectedStore=""
        selectedPeriod="30d"
        customFrom=""
        customTo=""
        isLoading={false}
        onCategoryChange={vi.fn()}
        onStoreChange={vi.fn()}
        onPeriodPresetChange={onPeriodPresetChange}
        onCustomDatesChange={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "7d" }));
    expect(onPeriodPresetChange).toHaveBeenCalledWith("7d");
  });

  it("shows custom date inputs when 'Personalizado' is selected", () => {
    const onCustomDatesChange = vi.fn();
    render(
      <AnalyticsFiltersBar
        categories={mockCategories}
        stores={mockStores}
        periods={["7d", "30d"]}
        selectedCategory=""
        selectedStore=""
        selectedPeriod="custom"
        customFrom="2026-09-01"
        customTo="2026-09-10"
        isLoading={false}
        onCategoryChange={vi.fn()}
        onStoreChange={vi.fn()}
        onPeriodPresetChange={vi.fn()}
        onCustomDatesChange={onCustomDatesChange}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Desde:")).toBeInTheDocument();
    expect(screen.getByLabelText("Hasta:")).toBeInTheDocument();
  });

  it("validates from <= to and prevents invalid date ranges", () => {
    const onCustomDatesChange = vi.fn();
    render(
      <AnalyticsFiltersBar
        categories={mockCategories}
        stores={mockStores}
        periods={["7d", "30d"]}
        selectedCategory=""
        selectedStore=""
        selectedPeriod="custom"
        customFrom=""
        customTo=""
        isLoading={false}
        onCategoryChange={vi.fn()}
        onStoreChange={vi.fn()}
        onPeriodPresetChange={vi.fn()}
        onCustomDatesChange={onCustomDatesChange}
        onRefresh={vi.fn()}
      />,
    );

    const fromInput = screen.getByLabelText("Desde:");
    const toInput = screen.getByLabelText("Hasta:");

    // Invalid range: from 2026-09-20, to 2026-09-10
    fireEvent.change(fromInput, { target: { value: "2026-09-20" } });
    fireEvent.change(toInput, { target: { value: "2026-09-10" } });

    expect(
      screen.getByText("La fecha inicial no puede ser posterior a la fecha final."),
    ).toBeInTheDocument();
    expect(onCustomDatesChange).not.toHaveBeenCalled();

    // Valid range: from 2026-09-01, to 2026-09-10
    fireEvent.change(fromInput, { target: { value: "2026-09-01" } });
    expect(
      screen.queryByText("La fecha inicial no puede ser posterior a la fecha final."),
    ).not.toBeInTheDocument();
    expect(onCustomDatesChange).toHaveBeenCalledWith("2026-09-01", "2026-09-10");
  });

  it("triggers onRefresh when clicking 'Actualizar'", () => {
    const onRefresh = vi.fn();
    render(
      <AnalyticsFiltersBar
        categories={mockCategories}
        stores={mockStores}
        periods={["7d", "30d"]}
        selectedCategory=""
        selectedStore=""
        selectedPeriod="30d"
        customFrom=""
        customTo=""
        isLoading={false}
        onCategoryChange={vi.fn()}
        onStoreChange={vi.fn()}
        onPeriodPresetChange={vi.fn()}
        onCustomDatesChange={vi.fn()}
        onRefresh={onRefresh}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /actualizar/i }));
    expect(onRefresh).toHaveBeenCalled();
  });
});
