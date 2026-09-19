import React, { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ProductPriceHistoryResponse } from "../../types/api";

const STORE_COLORS = [
  "#2563eb", // blue
  "#16a34a", // green
  "#d97706", // amber
  "#9333ea", // purple
  "#0284c7", // light blue
  "#dc2626", // red
];

export interface PriceChartProps {
  history: ProductPriceHistoryResponse;
  selectedRange: "1M" | "3M" | "ALL";
  selectedStoreId?: string;
  onRangeChange: (range: "1M" | "3M" | "ALL") => void;
  onStoreChange: (storeId?: string) => void;
}

export const PriceChart: React.FC<PriceChartProps> = ({
  history,
  selectedRange,
  selectedStoreId,
  onRangeChange,
  onStoreChange,
}) => {
  // Transform and align time-series data for Recharts
  const { chartData, storeNames, currency } = useMemo(() => {
    if (!history || !history.series || history.series.length === 0) {
      return { chartData: [], storeNames: [], currency: "PEN" };
    }

    const seriesList = history.series;
    const names: string[] = [];
    let detectedCurrency = "PEN";

    // Map timestamp -> { timestamp, date, [storeName]: price }
    const timeMap = new Map<string, { timestamp: number; dateStr: string; [key: string]: unknown }>();

    seriesList.forEach((s) => {
      names.push(s.store_name);
      if (s.currency) detectedCurrency = s.currency;

      s.points.forEach((pt) => {
        const d = new Date(pt.captured_at);
        const timeKey = pt.captured_at; // use exact timestamp as key

        if (!timeMap.has(timeKey)) {
          timeMap.set(timeKey, {
            timestamp: d.getTime(),
            dateStr: new Intl.DateTimeFormat("es-PE", {
              month: "short",
              day: "numeric",
              year: "numeric",
            }).format(d),
          });
        }

        const entry = timeMap.get(timeKey)!;
        entry[s.store_name] = parseFloat(pt.price);
      });
    });

    const sortedData = Array.from(timeMap.values()).sort((a, b) => a.timestamp - b.timestamp);

    return {
      chartData: sortedData,
      storeNames: names,
      currency: detectedCurrency,
    };
  }, [history]);

  const hasData = chartData.length > 0;

  return (
    <div
      style={{
        backgroundColor: "var(--color-surface)",
        borderRadius: "var(--radius-lg)",
        border: "1px solid var(--color-border)",
        padding: "1.5rem",
      }}
    >
      {/* Header con controles de rango y tienda */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
          marginBottom: "1.5rem",
        }}
      >
        <div>
          <h3
            style={{
              fontSize: "1.125rem",
              fontWeight: 600,
              color: "var(--color-text-dark)",
              marginBottom: "0.25rem",
            }}
          >
            Historial de Precios
          </h3>
          <p style={{ fontSize: "0.8125rem", color: "var(--color-text-secondary)" }}>
            Evolución de precios observados en tiendas ({currency})
          </p>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.75rem" }}>
          {/* Selector de tienda */}
          {history.series.length > 1 && (
            <select
              value={selectedStoreId || ""}
              onChange={(e) => onStoreChange(e.target.value ? e.target.value : undefined)}
              style={{
                padding: "0.375rem 0.75rem",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                backgroundColor: "var(--color-surface)",
                fontSize: "0.8125rem",
                color: "var(--color-text-dark)",
              }}
              data-testid="store-filter-select"
            >
              <option value="">Todas las tiendas</option>
              {history.series.map((s) => (
                <option key={s.store_id} value={s.store_id}>
                  {s.store_name}
                </option>
              ))}
            </select>
          )}

          {/* Botones de rango temporal */}
          <div
            style={{
              display: "flex",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              overflow: "hidden",
            }}
          >
            <button
              type="button"
              onClick={() => onRangeChange("1M")}
              className={`btn btn-sm ${selectedRange === "1M" ? "btn-primary" : "btn-outline"}`}
              style={{ borderRadius: 0, border: "none" }}
            >
              1 Mes
            </button>
            <button
              type="button"
              onClick={() => onRangeChange("3M")}
              className={`btn btn-sm ${selectedRange === "3M" ? "btn-primary" : "btn-outline"}`}
              style={{
                borderRadius: 0,
                borderLeft: "1px solid var(--color-border)",
                borderRight: "1px solid var(--color-border)",
              }}
            >
              3 Meses
            </button>
            <button
              type="button"
              onClick={() => onRangeChange("ALL")}
              className={`btn btn-sm ${selectedRange === "ALL" ? "btn-primary" : "btn-outline"}`}
              style={{ borderRadius: 0, border: "none" }}
            >
              Todo
            </button>
          </div>
        </div>
      </div>

      {/* Gráfico Recharts */}
      {hasData ? (
        <div style={{ width: "100%", height: "340px" }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis
                dataKey="dateStr"
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
                tickFormatter={(val: number) => `${currency} ${val}`}
                domain={["auto", "auto"]}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#ffffff",
                  border: "1px solid #e2e8f0",
                  borderRadius: "8px",
                  boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
                  fontSize: "13px",
                }}
                formatter={(value: unknown) => {
                  const num = typeof value === "number" ? value : Number(value);
                  return !isNaN(num) ? `${currency} ${num.toFixed(2)}` : String(value ?? "");
                }}
              />
              <Legend wrapperStyle={{ paddingTop: "12px", fontSize: "13px" }} />
              {storeNames.map((name, index) => (
                <Line
                  key={name}
                  type="monotone"
                  dataKey={name}
                  name={name}
                  stroke={STORE_COLORS[index % STORE_COLORS.length]}
                  strokeWidth={2.5}
                  dot={{ r: 4, strokeWidth: 2 }}
                  activeDot={{ r: 6 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div
          style={{
            height: "240px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: "#f8fafc",
            borderRadius: "var(--radius-md)",
            border: "1px dashed var(--color-border)",
            color: "var(--color-text-secondary)",
            fontSize: "0.875rem",
          }}
        >
          No hay observaciones de precios registradas en el período seleccionado.
        </div>
      )}
    </div>
  );
};
