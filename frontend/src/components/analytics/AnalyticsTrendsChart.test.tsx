import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DailyTrendPointOut } from "../../types/analytics";
import { AnalyticsTrendsChart } from "./AnalyticsTrendsChart";

describe("AnalyticsTrendsChart", () => {
  const mockPoints: DailyTrendPointOut[] = [
    {
      date: "2026-09-18",
      average_price: "920.50",
      median_price: "720.00",
      min_price: "185.00",
      max_price: "2499.00",
      associations_count: 6,
      products_count: 6,
    },
    {
      date: "2026-09-19",
      average_price: "850.00",
      median_price: "710.00",
      min_price: "180.00",
      max_price: "2450.00",
      associations_count: 7,
      products_count: 5,
    },
  ];

  it("renders chart and summary table when multiple points are provided", () => {
    render(
      <AnalyticsTrendsChart
        points={mockPoints}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getByText("Evolución y Tendencias Diarias de Precios")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Gráfico de evolución de precios" })).toBeInTheDocument();

    // Summary table
    expect(screen.getByText("Resumen de datos históricos diarios")).toBeInTheDocument();
    expect(screen.getByText("2026-09-18")).toBeInTheDocument();
    expect(screen.getByText("2026-09-19")).toBeInTheDocument();
    expect(screen.getByText(/920.50/)).toBeInTheDocument();
    expect(screen.getByText(/850.00/)).toBeInTheDocument();
  });

  it("handles a single data point gracefully", () => {
    const singlePoint: DailyTrendPointOut[] = [mockPoints[0]];

    render(
      <AnalyticsTrendsChart
        points={singlePoint}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getByRole("region", { name: "Gráfico de evolución de precios" })).toBeInTheDocument();
    expect(screen.getByText("2026-09-18")).toBeInTheDocument();
    expect(screen.queryByText("2026-09-19")).not.toBeInTheDocument();
  });

  it("renders empty state when points array is empty", () => {
    render(
      <AnalyticsTrendsChart
        points={[]}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getByText("Sin datos históricos para este período")).toBeInTheDocument();
  });

  it("renders loading skeleton when isLoading is true", () => {
    render(
      <AnalyticsTrendsChart
        points={[]}
        isLoading={true}
        error={null}
      />,
    );

    expect(screen.getByText("Evolución y Tendencias Diarias de Precios")).toBeInTheDocument();
  });

  it("renders error box and calls onRetry when error occurs", () => {
    const onRetry = vi.fn();
    render(
      <AnalyticsTrendsChart
        points={[]}
        isLoading={false}
        error="Fallo al cargar tendencias"
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText(/Error al cargar las tendencias de precios: Fallo al cargar tendencias/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalled();
  });
});
