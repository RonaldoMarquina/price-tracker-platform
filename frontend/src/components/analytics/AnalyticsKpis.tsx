import React from "react";
import { Award, CheckCircle2, DollarSign, TrendingDown } from "lucide-react";
import { AnalyticsSummaryResponse } from "../../types/analytics";
import { formatCurrencyPEN, formatPercentage } from "../../utils/formatters";
import { Skeleton } from "../common/Skeleton";

export interface AnalyticsKpisProps {
  summary: AnalyticsSummaryResponse | null;
  isLoading: boolean;
  error: string | null;
  onRetry?: () => void;
}

export const AnalyticsKpis: React.FC<AnalyticsKpisProps> = ({
  summary,
  isLoading,
  error,
  onRetry,
}) => {
  if (error) {
    return (
      <div className="module-error-box" role="alert">
        <span>Error al cargar los indicadores clave: {error}</span>
        {onRetry && (
          <button type="button" className="btn-retry" onClick={onRetry}>
            Reintentar
          </button>
        )}
      </div>
    );
  }

  if (isLoading || !summary) {
    return (
      <div className="analytics-kpis-grid" aria-busy="true" aria-label="Cargando indicadores clave">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="kpi-card">
            <div className="kpi-header">
              <Skeleton width="60%" height="1rem" />
              <Skeleton width="32px" height="32px" borderRadius="50%" />
            </div>
            <Skeleton width="80%" height="2rem" style={{ margin: "0.5rem 0" }} />
            <Skeleton width="50%" height="0.875rem" />
          </div>
        ))}
      </div>
    );
  }

  const { savings, most_competitive_store, freshness, comparable_products_count } = summary;

  return (
    <div className="analytics-kpis-grid" role="region" aria-label="Indicadores ejecutivos del mercado">
      {/* 1. Ahorro Promedio */}
      <div className="kpi-card" tabIndex={0}>
        <div className="kpi-header">
          <span className="kpi-title">Ahorro Promedio</span>
          <div
            className="kpi-icon-wrapper"
            style={{ backgroundColor: "#ecfdf5", color: "#059669" }}
            aria-hidden="true"
          >
            <TrendingDown size={18} />
          </div>
        </div>
        <div className="kpi-value" aria-label={`Ahorro promedio ${formatPercentage(savings.average_savings_percentage)}`}>
          {formatPercentage(savings.average_savings_percentage)}
        </div>
        <div className="kpi-subtitle">
          Promedio de {formatCurrencyPEN(savings.average_savings_amount)} por producto
        </div>
        <div className="kpi-badge-row">
          <span className="badge-savings">
            {comparable_products_count} productos comparables
          </span>
        </div>
      </div>

      {/* 2. Mayor Ahorro Detectado */}
      <div className="kpi-card" tabIndex={0}>
        <div className="kpi-header">
          <span className="kpi-title">Mayor Ahorro</span>
          <div
            className="kpi-icon-wrapper"
            style={{ backgroundColor: "#eff6ff", color: "#2563eb" }}
            aria-hidden="true"
          >
            <DollarSign size={18} />
          </div>
        </div>
        {savings.max_savings_product ? (
          <>
            <div className="kpi-value">
              {formatCurrencyPEN(savings.max_savings_product.savings_amount)}
            </div>
            <div
              className="kpi-subtitle"
              title={savings.max_savings_product.product_name}
              style={{
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {savings.max_savings_product.product_name}
            </div>
            <div className="kpi-badge-row" style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
              <span>{savings.max_savings_product.best_store} vs {savings.max_savings_product.worst_store}</span>
            </div>
          </>
        ) : (
          <>
            <div className="kpi-value" style={{ fontSize: "1.25rem", color: "var(--color-text-secondary)" }}>
              Sin brecha
            </div>
            <div className="kpi-subtitle">
              Requiere al menos 2 ofertas activas en stock
            </div>
          </>
        )}
      </div>

      {/* 3. Tienda Más Competitiva */}
      <div className="kpi-card" tabIndex={0}>
        <div className="kpi-header">
          <span className="kpi-title">Tienda Más Competitiva</span>
          <div
            className="kpi-icon-wrapper"
            style={{ backgroundColor: "#faf5ff", color: "#9333ea" }}
            aria-hidden="true"
          >
            <Award size={18} />
          </div>
        </div>
        {most_competitive_store ? (
          <>
            <div
              className="kpi-value"
              style={{ fontSize: "1.375rem" }}
              title={most_competitive_store.store_name}
            >
              {most_competitive_store.store_name}
            </div>
            <div className="kpi-subtitle">
              {formatPercentage(most_competitive_store.best_price_share_percentage)} de mejores precios
            </div>
            <div className="kpi-badge-row">
              <span
                style={{
                  fontSize: "0.75rem",
                  padding: "0.125rem 0.5rem",
                  borderRadius: "var(--radius-sm)",
                  backgroundColor: "#f3e8ff",
                  color: "#7e22ce",
                  fontWeight: 600,
                }}
              >
                {most_competitive_store.best_price_count} ofertas ganadoras
              </span>
            </div>
          </>
        ) : (
          <>
            <div className="kpi-value" style={{ fontSize: "1.25rem", color: "var(--color-text-secondary)" }}>
              Sin datos
            </div>
            <div className="kpi-subtitle">Sin ofertas en stock evaluadas</div>
          </>
        )}
      </div>

      {/* 4. Frescura de Datos */}
      <div className="kpi-card" tabIndex={0}>
        <div className="kpi-header">
          <span className="kpi-title">Calidad de Datos</span>
          <div
            className="kpi-icon-wrapper"
            style={{ backgroundColor: "#f0fdf4", color: "#16a34a" }}
            aria-hidden="true"
          >
            <CheckCircle2 size={18} />
          </div>
        </div>
        <div className="kpi-value">
          {formatPercentage(freshness.freshness_rate)}
        </div>
        <div className="kpi-subtitle">
          {freshness.fresh_count} de {freshness.total_active_associations} ofertas frescas (≤ 7 días)
        </div>
        <div className="kpi-badge-row">
          {freshness.stale_count > 0 && (
            <span
              style={{
                fontSize: "0.75rem",
                padding: "0.125rem 0.375rem",
                borderRadius: "var(--radius-sm)",
                backgroundColor: "#fef3c7",
                color: "#b45309",
              }}
            >
              {freshness.stale_count} obsoletas
            </span>
          )}
          {freshness.unknown_count > 0 && (
            <span
              style={{
                fontSize: "0.75rem",
                padding: "0.125rem 0.375rem",
                borderRadius: "var(--radius-sm)",
                backgroundColor: "#f1f5f9",
                color: "#64748b",
              }}
            >
              {freshness.unknown_count} sin fecha reciente
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
