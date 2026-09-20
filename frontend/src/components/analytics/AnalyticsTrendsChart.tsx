import React, { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { LineChart as ChartIcon } from "lucide-react";
import { DailyTrendPointOut } from "../../types/analytics";
import { formatCurrencyPEN } from "../../utils/formatters";
import { EmptyState } from "../common/EmptyState";
import { Skeleton } from "../common/Skeleton";

export interface AnalyticsTrendsChartProps {
  points: DailyTrendPointOut[];
  isLoading: boolean;
  error: string | null;
  onRetry?: () => void;
}

export const AnalyticsTrendsChart: React.FC<AnalyticsTrendsChartProps> = ({
  points,
  isLoading,
  error,
  onRetry,
}) => {
  const chartData = useMemo(() => {
    return points.map((pt) => {
      // Parse YYYY-MM-DD
      const [year, month, day] = pt.date.split("-").map(Number);
      const dateObj = new Date(year, month - 1, day);
      const label = new Intl.DateTimeFormat("es-PE", {
        month: "short",
        day: "numeric",
      }).format(dateObj);

      return {
        date: pt.date,
        label,
        avg: parseFloat(pt.average_price),
        median: parseFloat(pt.median_price),
        min: parseFloat(pt.min_price),
        max: parseFloat(pt.max_price),
        associations: pt.associations_count,
        products: pt.products_count,
      };
    });
  }, [points]);

  if (error) {
    return (
      <div className="analytics-section">
        <div className="section-header">
          <h2>
            <ChartIcon size={20} style={{ color: "var(--color-primary)" }} aria-hidden="true" />
            Evolución y Tendencias Diarias de Precios
          </h2>
        </div>
        <div className="module-error-box" role="alert">
          <span>Error al cargar las tendencias de precios: {error}</span>
          {onRetry && (
            <button type="button" className="btn-retry" onClick={onRetry}>
              Reintentar
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <section className="analytics-section" aria-labelledby="heading-trends">
      <div className="section-header">
        <div>
          <h2 id="heading-trends">
            <ChartIcon size={20} style={{ color: "var(--color-primary)" }} aria-hidden="true" />
            Evolución y Tendencias Diarias de Precios
          </h2>
          <p>
            Agregación diaria sin sesgo de muestreo: colapsa al último precio válido por producto y día.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div style={{ height: "320px", display: "flex", flexDirection: "column", gap: "1rem" }} aria-busy="true">
          <Skeleton width="100%" height="260px" />
          <Skeleton width="60%" height="1.5rem" />
        </div>
      ) : points.length === 0 ? (
        <EmptyState
          title="Sin datos históricos para este período"
          message="No se encontraron observaciones de precios en stock para los filtros y fechas seleccionados."
        />
      ) : (
        <>
          {/* Chart Container */}
          <div
            style={{ width: "100%", height: 320, minWidth: 0 }}
            role="region"
            aria-label="Gráfico de evolución de precios"
          >
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={chartData}
                margin={{ top: 10, right: 20, left: 10, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis
                  dataKey="label"
                  stroke="#64748b"
                  fontSize={12}
                  tickLine={false}
                  axisLine={{ stroke: "#cbd5e1" }}
                />
                <YAxis
                  stroke="#64748b"
                  fontSize={12}
                  tickLine={false}
                  axisLine={{ stroke: "#cbd5e1" }}
                  tickFormatter={(val) => `S/ ${val}`}
                  domain={["auto", "auto"]}
                />
                <Tooltip
                  formatter={(value: unknown, name?: unknown) => [
                    formatCurrencyPEN(
                      typeof value === "number" || typeof value === "string"
                        ? value
                        : null,
                    ),
                    String(name ?? ""),
                  ]}
                  labelFormatter={(_label, items) => {
                    if (items && items.length > 0) {
                      const payload = items[0].payload;
                      return `${payload.date} (${payload.products} productos, ${payload.associations} ofertas)`;
                    }
                    return "";
                  }}
                  contentStyle={{
                    backgroundColor: "var(--color-surface)",
                    borderRadius: "var(--radius-md)",
                    border: "1px solid var(--color-border)",
                    boxShadow: "var(--shadow-md)",
                    fontSize: "0.8125rem",
                  }}
                />
                <Legend
                  wrapperStyle={{ paddingTop: "10px", fontSize: "0.8125rem" }}
                  iconType="plainline"
                />

                {/* Serie Promedio: Línea continua azul con puntos circulares */}
                <Line
                  type="monotone"
                  dataKey="avg"
                  name="Precio Promedio (línea continua)"
                  stroke="#2563eb"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: "#2563eb", stroke: "#ffffff", strokeWidth: 1.5 }}
                  activeDot={{ r: 6 }}
                  connectNulls={false}
                />

                {/* Serie Mediana: Línea discontinua púrpura con puntos cuadrados */}
                <Line
                  type="monotone"
                  dataKey="median"
                  name="Precio Mediano (línea punteada)"
                  stroke="#9333ea"
                  strokeWidth={2.5}
                  strokeDasharray="6 4"
                  dot={{ r: 4, fill: "#9333ea", stroke: "#ffffff", strokeWidth: 1.5 }}
                  activeDot={{ r: 6 }}
                  connectNulls={false}
                />

                {/* Serie Mínimo: Línea verde fina */}
                <Line
                  type="monotone"
                  dataKey="min"
                  name="Precio Mínimo"
                  stroke="#16a34a"
                  strokeWidth={1.5}
                  strokeDasharray="2 2"
                  dot={{ r: 3, fill: "#16a34a" }}
                  connectNulls={false}
                />

                {/* Serie Máximo: Línea roja fina */}
                <Line
                  type="monotone"
                  dataKey="max"
                  name="Precio Máximo"
                  stroke="#dc2626"
                  strokeWidth={1.5}
                  strokeDasharray="2 2"
                  dot={{ r: 3, fill: "#dc2626" }}
                  connectNulls={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Accessible Data Summary Table below chart */}
          <div className="table-responsive chart-summary-table">
            <table className="analytics-table" aria-label="Tabla de datos de la serie temporal de precios">
              <caption style={{ textAlign: "left", padding: "0.5rem 0", fontWeight: 600, color: "var(--color-text-dark)" }}>
                Resumen de datos históricos diarios
              </caption>
              <thead>
                <tr>
                  <th scope="col">Fecha</th>
                  <th scope="col">Promedio</th>
                  <th scope="col">Mediana</th>
                  <th scope="col">Mínimo</th>
                  <th scope="col">Máximo</th>
                  <th scope="col">Productos</th>
                  <th scope="col">Ofertas</th>
                </tr>
              </thead>
              <tbody>
                {points.map((pt) => (
                  <tr key={pt.date}>
                    <td>{pt.date}</td>
                    <td style={{ fontWeight: 600, color: "#2563eb" }}>{formatCurrencyPEN(pt.average_price)}</td>
                    <td style={{ fontWeight: 600, color: "#9333ea" }}>{formatCurrencyPEN(pt.median_price)}</td>
                    <td style={{ color: "#16a34a" }}>{formatCurrencyPEN(pt.min_price)}</td>
                    <td style={{ color: "#dc2626" }}>{formatCurrencyPEN(pt.max_price)}</td>
                    <td>{pt.products_count}</td>
                    <td>{pt.associations_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
};
