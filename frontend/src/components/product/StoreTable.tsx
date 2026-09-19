import React from "react";
import { ExternalLink, Store as StoreIcon } from "lucide-react";
import { ProductStoreOut } from "../../types/api";
import { Badge } from "../common/Badge";

export interface StoreTableProps {
  stores: ProductStoreOut[];
}

export const StoreTable: React.FC<StoreTableProps> = ({ stores }) => {
  const formatDate = (isoString?: string) => {
    if (!isoString) return "—";
    try {
      const d = new Date(isoString);
      return new Intl.DateTimeFormat("es-PE", {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(d);
    } catch {
      return isoString;
    }
  };

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
              return (
                <tr
                  key={store.store_id}
                  style={{
                    borderBottom: "1px solid var(--color-border)",
                    transition: "background-color 0.15s ease",
                  }}
                >
                  <td style={{ padding: "1rem 1.25rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <div
                        style={{
                          width: "28px",
                          height: "28px",
                          borderRadius: "var(--radius-sm)",
                          backgroundColor: "#eff6ff",
                          color: "var(--color-primary)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        <StoreIcon size={16} />
                      </div>
                      <div>
                        <div style={{ fontWeight: 600, color: "var(--color-text-dark)" }}>
                          {store.store_name}
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
                    {store.latest_price ? (
                      <span
                        style={{
                          fontWeight: 700,
                          fontSize: "1.05rem",
                          color: "var(--color-price-down)",
                        }}
                      >
                        {store.latest_price.currency} {store.latest_price.amount}
                      </span>
                    ) : (
                      <span style={{ color: "var(--color-text-secondary)" }}>Sin precio</span>
                    )}
                  </td>
                  <td style={{ padding: "1rem 1.25rem", color: "var(--color-text-secondary)" }}>
                    {formatDate(store.latest_price?.captured_at)}
                  </td>
                  <td style={{ padding: "1rem 1.25rem", textAlign: "right" }}>
                    {hasValidUrl ? (
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
