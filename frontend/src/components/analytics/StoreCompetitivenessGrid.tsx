import React from "react";
import { CheckCircle, HelpCircle, Store as StoreIcon, XCircle } from "lucide-react";
import { StoreCompetitivenessItemOut } from "../../types/analytics";
import { formatPercentage } from "../../utils/formatters";
import { EmptyState } from "../common/EmptyState";
import { Skeleton } from "../common/Skeleton";

export interface StoreCompetitivenessGridProps {
  stores: StoreCompetitivenessItemOut[];
  isLoading: boolean;
  error: string | null;
  onRetry?: () => void;
}

export const StoreCompetitivenessGrid: React.FC<StoreCompetitivenessGridProps> = ({
  stores,
  isLoading,
  error,
  onRetry,
}) => {
  if (error) {
    return (
      <div className="analytics-section">
        <div className="section-header">
          <h2>
            <StoreIcon size={20} style={{ color: "var(--color-primary)" }} aria-hidden="true" />
            Competitividad y Cobertura por Tienda
          </h2>
        </div>
        <div className="module-error-box" role="alert">
          <span>Error al cargar la competitividad de tiendas: {error}</span>
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
    <section className="analytics-section" aria-labelledby="heading-store-competitiveness">
      <div className="section-header">
        <div>
          <h2 id="heading-store-competitiveness">
            <StoreIcon size={20} style={{ color: "var(--color-primary)" }} aria-hidden="true" />
            Competitividad y Cobertura por Tienda
          </h2>
          <p>
            Porcentaje de mejores precios (suman 100.00% entre tiendas activas) y tasas de disponibilidad.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="stores-grid" aria-busy="true" aria-label="Cargando competitividad de tiendas">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="store-card">
              <div className="store-card-header">
                <Skeleton width="60%" height="1.25rem" />
                <Skeleton width="20%" height="1rem" />
              </div>
              <Skeleton width="100%" height="8px" style={{ margin: "0.5rem 0" }} />
              <Skeleton width="40%" height="0.875rem" />
              <Skeleton width="100%" height="1.5rem" style={{ marginTop: "0.5rem" }} />
            </div>
          ))}
        </div>
      ) : stores.length === 0 ? (
        <EmptyState
          title="Sin datos de tiendas"
          message="No se encontraron tiendas asociadas a los productos de la selección actual."
        />
      ) : (
        <div className="stores-grid" role="list" aria-label="Listado de tiendas y competitividad">
          {stores.map((s) => {
            const shareNumber = parseFloat(s.best_price_share_percentage) || 0;

            return (
              <div
                key={s.store_id}
                className={`store-card ${!s.is_active ? "inactive" : ""}`}
                role="listitem"
                tabIndex={0}
              >
                {/* Header: Name and Status */}
                <div className="store-card-header">
                  <h3>{s.store_name}</h3>
                  {!s.is_active ? (
                    <span
                      style={{
                        fontSize: "0.6875rem",
                        padding: "0.125rem 0.375rem",
                        borderRadius: "var(--radius-sm)",
                        backgroundColor: "#f1f5f9",
                        color: "#64748b",
                        fontWeight: 600,
                      }}
                    >
                      Inactiva
                    </span>
                  ) : (
                    <span
                      style={{
                        fontSize: "0.8125rem",
                        fontWeight: 700,
                        color: shareNumber > 0 ? "var(--color-primary)" : "var(--color-text-secondary)",
                      }}
                    >
                      {formatPercentage(s.best_price_share_percentage)}
                    </span>
                  )}
                </div>

                {/* Progress Bar for Best Price Share */}
                <div className="share-bar-wrapper">
                  <div
                    className="share-bar-track"
                    role="progressbar"
                    aria-valuenow={shareNumber}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`Cuota de mejor precio: ${formatPercentage(s.best_price_share_percentage)}`}
                  >
                    <div
                      className="share-bar-fill"
                      style={{
                        width: `${Math.min(100, Math.max(0, shareNumber))}%`,
                        backgroundColor: s.is_active ? "var(--color-primary)" : "#cbd5e1",
                      }}
                    />
                  </div>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: "0.75rem",
                      color: "var(--color-text-secondary)",
                    }}
                  >
                    <span>{s.best_price_count} ofertas ganadoras</span>
                    <span>{s.observed_associations} / {s.total_associations} cubiertos</span>
                  </div>
                </div>

                {/* Availability Breakdown */}
                <div className="avail-breakdown">
                  <div
                    style={{ display: "flex", alignItems: "center", gap: "0.25rem", color: "#16a34a" }}
                    title={`${s.in_stock_count} en stock`}
                  >
                    <CheckCircle size={13} aria-hidden="true" />
                    <span>{formatPercentage(s.in_stock_percentage)}</span>
                  </div>
                  <div
                    style={{ display: "flex", alignItems: "center", gap: "0.25rem", color: "#dc2626" }}
                    title={`${s.out_of_stock_count} agotados`}
                  >
                    <XCircle size={13} aria-hidden="true" />
                    <span>{formatPercentage(s.out_of_stock_percentage)}</span>
                  </div>
                  <div
                    style={{ display: "flex", alignItems: "center", gap: "0.25rem", color: "#64748b" }}
                    title={`${s.unknown_count} desconocidos`}
                  >
                    <HelpCircle size={13} aria-hidden="true" />
                    <span>{formatPercentage(s.unknown_percentage)}</span>
                  </div>
                </div>

                {/* Price Conditions Badges */}
                {Object.keys(s.price_conditions).length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                    {s.price_conditions["cash_or_bank_transfer"] && (
                      <span
                        style={{
                          fontSize: "0.6875rem",
                          padding: "0.0625rem 0.375rem",
                          borderRadius: "var(--radius-sm)",
                          backgroundColor: "#fef3c7",
                          color: "#92400e",
                        }}
                      >
                        {s.price_conditions["cash_or_bank_transfer"]} Efectivo/Transf.
                      </span>
                    )}
                    {s.price_conditions["standard"] && (
                      <span
                        style={{
                          fontSize: "0.6875rem",
                          padding: "0.0625rem 0.375rem",
                          borderRadius: "var(--radius-sm)",
                          backgroundColor: "#f1f5f9",
                          color: "#475569",
                        }}
                      >
                        {s.price_conditions["standard"]} Estándar
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};
