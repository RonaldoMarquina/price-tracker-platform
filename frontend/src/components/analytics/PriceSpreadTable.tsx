import React from "react";
import { ArrowDownRight, ExternalLink, TrendingDown } from "lucide-react";
import { PriceSpreadItemOut } from "../../types/analytics";
import { formatCurrencyPEN, formatPercentage } from "../../utils/formatters";
import { EmptyState } from "../common/EmptyState";
import { Skeleton } from "../common/Skeleton";

export interface PriceSpreadTableProps {
  items: PriceSpreadItemOut[];
  isLoading: boolean;
  error: string | null;
  onNavigate: (path: string) => void;
  onRetry?: () => void;
}

export const PriceSpreadTable: React.FC<PriceSpreadTableProps> = ({
  items,
  isLoading,
  error,
  onNavigate,
  onRetry,
}) => {
  if (error) {
    return (
      <div className="analytics-section">
        <div className="section-header">
          <h2>
            <TrendingDown size={20} style={{ color: "var(--color-primary)" }} aria-hidden="true" />
            Dispersión de Precios y Oportunidades de Ahorro
          </h2>
        </div>
        <div className="module-error-box" role="alert">
          <span>Error al cargar el ranking de ahorro: {error}</span>
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
    <section className="analytics-section" aria-labelledby="heading-price-spread">
      <div className="section-header">
        <div>
          <h2 id="heading-price-spread">
            <TrendingDown size={20} style={{ color: "var(--color-primary)" }} aria-hidden="true" />
            Dispersión de Precios y Oportunidades de Ahorro
          </h2>
          <p>
            Productos ordenados por la mayor diferencia monetaria entre su mejor y peor oferta en stock.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="table-responsive" aria-busy="true" aria-label="Cargando tabla de dispersión">
          <table className="analytics-table">
            <thead>
              <tr>
                <th>Producto</th>
                <th>Mejor Oferta</th>
                <th>Peor Oferta</th>
                <th>Ahorro Potencial</th>
                <th>Ofertas</th>
              </tr>
            </thead>
            <tbody>
              {[1, 2, 3, 4, 5].map((i) => (
                <tr key={i}>
                  <td>
                    <Skeleton width="70%" height="1.25rem" />
                    <Skeleton width="40%" height="0.75rem" style={{ marginTop: "0.25rem" }} />
                  </td>
                  <td><Skeleton width="5rem" height="1.25rem" /></td>
                  <td><Skeleton width="5rem" height="1.25rem" /></td>
                  <td><Skeleton width="6rem" height="1.25rem" /></td>
                  <td><Skeleton width="2rem" height="1.25rem" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title="Sin dispersión de precios detectada"
          message="No se encontraron productos con al menos dos ofertas activas en stock para la selección actual."
        />
      ) : (
        <div className="table-responsive">
          <table className="analytics-table" aria-label="Ranking de dispersión de precios">
            <thead>
              <tr>
                <th scope="col">Producto</th>
                <th scope="col">Mejor Oferta</th>
                <th scope="col">Peor Oferta</th>
                <th scope="col">Ahorro Potencial</th>
                <th scope="col">Ofertas</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.product_id}>
                  {/* Producto */}
                  <td>
                    <a
                      href={`/products/${item.product_id}`}
                      className="product-link"
                      onClick={(e) => {
                        e.preventDefault();
                        onNavigate(`/products/${item.product_id}`);
                      }}
                      title={`Ver historial de ${item.product_name}`}
                    >
                      <span>{item.product_name}</span>
                      <ExternalLink size={12} style={{ marginLeft: "0.25rem", verticalAlign: "middle" }} aria-hidden="true" />
                    </a>
                    <div style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)", marginTop: "0.125rem" }}>
                      {item.category_name}
                    </div>
                  </td>

                  {/* Mejor Oferta */}
                  <td>
                    <div style={{ fontWeight: 700, color: "var(--color-price-down)" }}>
                      {formatCurrencyPEN(item.best_offer.amount)}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                      {item.best_offer.store_name}
                    </div>
                    {item.best_offer.price_condition === "cash_or_bank_transfer" && (
                      <span
                        style={{
                          display: "inline-block",
                          fontSize: "0.6875rem",
                          padding: "0.0625rem 0.375rem",
                          borderRadius: "var(--radius-sm)",
                          backgroundColor: "#fef3c7",
                          color: "#92400e",
                          marginTop: "0.125rem",
                        }}
                      >
                        Efectivo/Transf.
                      </span>
                    )}
                  </td>

                  {/* Peor Oferta */}
                  <td>
                    <div style={{ fontWeight: 600, color: "var(--color-price-up)" }}>
                      {formatCurrencyPEN(item.worst_offer.amount)}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                      {item.worst_offer.store_name}
                    </div>
                    {item.worst_offer.price_condition === "cash_or_bank_transfer" && (
                      <span
                        style={{
                          display: "inline-block",
                          fontSize: "0.6875rem",
                          padding: "0.0625rem 0.375rem",
                          borderRadius: "var(--radius-sm)",
                          backgroundColor: "#fef3c7",
                          color: "#92400e",
                          marginTop: "0.125rem",
                        }}
                      >
                        Efectivo/Transf.
                      </span>
                    )}
                  </td>

                  {/* Ahorro Potencial */}
                  <td>
                    <div className="badge-savings">
                      <ArrowDownRight size={14} aria-hidden="true" />
                      <span>{formatCurrencyPEN(item.savings_amount)}</span>
                      <span>({formatPercentage(item.savings_percentage)})</span>
                    </div>
                  </td>

                  {/* Ofertas válidas */}
                  <td>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: "28px",
                        height: "28px",
                        borderRadius: "var(--radius-full)",
                        backgroundColor: "var(--color-bg)",
                        fontSize: "0.8125rem",
                        fontWeight: 600,
                        color: "var(--color-text-secondary)",
                      }}
                    >
                      {item.valid_offers_count}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
