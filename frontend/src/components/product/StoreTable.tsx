import React from "react";
import { ExternalLink, Store as StoreIcon } from "lucide-react";
import { ProductStoreOut } from "../../types/api";
import { Badge } from "../common/Badge";
import { formatCapturedDate } from "../../utils/freshness";

export interface StoreTableProps {
  stores: ProductStoreOut[];
}

export const StoreTable: React.FC<StoreTableProps> = ({ stores }) => {
  const getAvailabilityBadge = (avail: string | null) => {
    if (!avail) {
      return <span style={{ color: "var(--color-text-secondary)", fontSize: "0.8125rem" }}>—</span>;
    }
    const lower = avail.toLowerCase();
    if (lower.includes("agotado") || lower.includes("out_of_stock")) {
      return <Badge variant="danger">Agotado</Badge>;
    }
    if (lower.includes("disponible") || lower.includes("in_stock") || lower === "stock") {
      return <Badge variant="success">Disponible</Badge>;
    }
    if (lower.includes("consultar") || lower.includes("unknown")) {
      return <Badge variant="warning">Consultar disponibilidad</Badge>;
    }
    return <Badge variant="default">{avail}</Badge>;
  };

  const isValidUrl = (url?: string): boolean => {
    if (!url) return false;
    try {
      const parsed = new URL(url);
      return parsed.protocol === "http:" || parsed.protocol === "https:";
    } catch {
      return false;
    }
  };

  if (!stores || stores.length === 0) {
    return (
      <div
        style={{
          padding: "2rem",
          backgroundColor: "var(--color-surface)",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--color-border)",
          textAlign: "center",
          color: "var(--color-text-secondary)",
          fontSize: "0.9375rem",
        }}
      >
        No hay tiendas vinculadas a este componente actualmente.
      </div>
    );
  }

  return (
    <div
      style={{
        backgroundColor: "var(--color-surface)",
        borderRadius: "var(--radius-lg)",
        border: "1px solid var(--color-border)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          overflowX: "auto",
        }}
      >
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            textAlign: "left",
            fontSize: "0.875rem",
          }}
        >
          <thead>
            <tr
              style={{
                backgroundColor: "#f8fafc",
                borderBottom: "1px solid var(--color-border)",
                color: "var(--color-text-secondary)",
                fontSize: "0.75rem",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              <th style={{ padding: "0.875rem 1.25rem" }}>Tienda</th>
              <th style={{ padding: "0.875rem 1.25rem" }}>Disponibilidad</th>
              <th style={{ padding: "0.875rem 1.25rem" }}>Último Precio</th>
              <th style={{ padding: "0.875rem 1.25rem" }}>Fecha Observación</th>
              <th style={{ padding: "0.875rem 1.25rem", textAlign: "right" }}>Acción</th>
            </tr>
          </thead>
          <tbody>
            {stores.map((store) => {
              const hasValidUrl = isValidUrl(store.product_url);
              const isStoreActive = store.is_store_active !== false;

              return (
                <tr
                  key={store.store_id}
                  style={{
                    borderBottom: "1px solid var(--color-border)",
                    transition: "background-color 0.15s ease",
                    backgroundColor: isStoreActive ? "transparent" : "#fcfcfd",
                    opacity: isStoreActive ? 1 : 0.85,
                  }}
                >
                  <td style={{ padding: "1rem 1.25rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <div
                        style={{
                          width: "28px",
                          height: "28px",
                          borderRadius: "var(--radius-sm)",
                          backgroundColor: isStoreActive ? "#eff6ff" : "#f1f5f9",
                          color: isStoreActive ? "var(--color-primary)" : "#94a3b8",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        <StoreIcon size={16} />
                      </div>
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <span style={{ fontWeight: 600, color: "var(--color-text-dark)" }}>
                            {store.store_name}
                          </span>
                          {!isStoreActive && (
                            <Badge variant="default" style={{ fontSize: "0.7rem" }}>
                              Desactivada
                            </Badge>
                          )}
                        </div>
                        {store.external_sku && (
                          <div style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                            SKU: {store.external_sku}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: "1rem 1.25rem" }}>
                    {getAvailabilityBadge(store.latest_price?.availability ?? null)}
                  </td>
                  <td style={{ padding: "1rem 1.25rem" }}>
                    {store.latest_price?.amount ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                        <span
                          style={{
                            fontWeight: 700,
                            fontSize: "1.05rem",
                            color: isStoreActive ? "var(--color-price-down)" : "var(--color-text-secondary)",
                          }}
                        >
                          {store.latest_price.currency} {store.latest_price.amount}
                        </span>
                        <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                          {store.latest_price.is_provisional && (
                            <Badge variant="default" style={{ fontSize: "0.7rem" }}>
                              Precio referencial
                            </Badge>
                          )}
                          {store.latest_price.price_condition === "cash_or_bank_transfer" && (
                            <Badge variant="warning" style={{ fontSize: "0.7rem" }}>
                              Efectivo / Transferencia
                            </Badge>
                          )}
                        </div>
                      </div>
                    ) : (
                      <span style={{ color: "var(--color-text-secondary)" }}>Sin precio</span>
                    )}
                  </td>
                  <td style={{ padding: "1rem 1.25rem" }}>
                    {(() => {
                      const { state, label } = formatCapturedDate(store.latest_price?.captured_at);
                      if (state === "unknown") {
                        return (
                          <span
                            style={{
                              color: "var(--color-text-secondary)",
                              fontSize: "0.8125rem",
                              fontStyle: "italic",
                            }}
                          >
                            Fecha de actualización no disponible
                          </span>
                        );
                      }
                      if (state === "stale") {
                        return (
                          <span
                            style={{
                              color: "#b45309",
                              fontSize: "0.8125rem",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.35rem",
                            }}
                            title="Datos observados hace más de 7 días"
                          >
                            {label}
                            <Badge variant="warning" style={{ fontSize: "0.65rem", padding: "0.1rem 0.35rem" }}>
                              Desactualizado
                            </Badge>
                          </span>
                        );
                      }
                      return (
                        <span style={{ color: "var(--color-text-secondary)", fontSize: "0.8125rem" }}>
                          {label}
                        </span>
                      );
                    })()}
                  </td>
                  <td style={{ padding: "1rem 1.25rem", textAlign: "right" }}>
                    {isStoreActive && hasValidUrl ? (
                      <a
                        href={store.product_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn btn-outline btn-sm"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.35rem",
                        }}
                      >
                        Ir a la tienda
                        <ExternalLink size={14} />
                      </a>
                    ) : !isStoreActive ? (
                      <span
                        style={{
                          fontSize: "0.8125rem",
                          color: "var(--color-text-secondary)",
                          fontStyle: "italic",
                        }}
                      >
                        Tienda no disponible
                      </span>
                    ) : (
                      <span
                        style={{
                          fontSize: "0.8125rem",
                          color: "var(--color-text-secondary)",
                          fontStyle: "italic",
                        }}
                      >
                        No disponible
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
