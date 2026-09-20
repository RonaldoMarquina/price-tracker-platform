import React, { useState } from "react";
import { ArrowRight, Cpu, Tag } from "lucide-react";
import { ProductListItemOut } from "../../types/api";
import { Badge } from "../common/Badge";

export interface ProductCardProps {
  product: ProductListItemOut;
  onSelect: (productId: string) => void;
}

export const ProductCard: React.FC<ProductCardProps> = ({ product, onSelect }) => {
  const [imageError, setImageError] = useState(false);

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    onSelect(product.id);
  };

  return (
    <article
      className="card"
      style={{
        display: "flex",
        flexDirection: "column",
        padding: "1.25rem",
        cursor: "pointer",
        position: "relative",
      }}
      onClick={handleClick}
      data-testid={`product-card-${product.id}`}
    >
      {/* Badge Superior */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "0.75rem",
        }}
      >
        <Badge variant="primary">{product.category}</Badge>
        {product.brand && (
          <span
            style={{
              fontSize: "0.75rem",
              fontWeight: 600,
              color: "var(--color-text-secondary)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            {product.brand}
          </span>
        )}
      </div>

      {/* Imagen o Fallback */}
      <div
        style={{
          height: "150px",
          width: "100%",
          backgroundColor: "#f8fafc",
          borderRadius: "var(--radius-md)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
          marginBottom: "1rem",
          border: "1px solid #f1f5f9",
        }}
      >
        {product.image_url && !imageError ? (
          <img
            src={product.image_url}
            alt={product.name}
            onError={() => setImageError(true)}
            style={{
              maxWidth: "100%",
              maxHeight: "100%",
              objectFit: "contain",
              padding: "0.5rem",
            }}
          />
        ) : (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "0.5rem",
              color: "#94a3b8",
            }}
          >
            <Cpu size={36} strokeWidth={1.5} />
            <span style={{ fontSize: "0.75rem" }}>Sin imagen</span>
          </div>
        )}
      </div>

      {/* Nombre del Producto */}
      <h3
        style={{
          fontSize: "1rem",
          fontWeight: 600,
          color: "var(--color-text-dark)",
          marginBottom: "0.75rem",
          lineHeight: 1.35,
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          minHeight: "2.7rem",
        }}
        title={product.name}
      >
        {product.name}
      </h3>

      {/* Precio e Info de Tienda */}
      <div
        style={{
          marginTop: "auto",
          paddingTop: "0.875rem",
          borderTop: "1px solid var(--color-border)",
          display: "flex",
          flexDirection: "column",
          gap: "0.25rem",
        }}
      >
        {(() => {
          const offer = product.best_price
            ? {
                amount: product.best_price.amount,
                currency: product.best_price.currency,
                store: product.best_price.store_name,
                condition: product.best_price.price_condition,
              }
            : product.latest_price
            ? {
                amount: product.latest_price.amount,
                currency: product.latest_price.currency,
                store: product.latest_price.store,
                condition: null,
              }
            : null;

          if (offer) {
            return (
              <div>
                <span
                  style={{
                    fontSize: "0.75rem",
                    color: "var(--color-text-secondary)",
                    display: "block",
                  }}
                >
                  Mejor oferta:
                </span>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    flexWrap: "wrap",
                  }}
                >
                  <span
                    style={{
                      fontSize: "1.25rem",
                      fontWeight: 700,
                      color: "var(--color-price-down)",
                    }}
                  >
                    {offer.currency} {offer.amount}
                  </span>
                  {offer.condition === "cash_or_bank_transfer" && (
                    <Badge variant="warning" style={{ fontSize: "0.7rem", padding: "0.15rem 0.4rem" }}>
                      Efectivo / Transf.
                    </Badge>
                  )}
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.35rem",
                    fontSize: "0.8125rem",
                    color: "var(--color-text-secondary)",
                    marginTop: "0.15rem",
                  }}
                >
                  <Tag size={12} />
                  <span>En {offer.store}</span>
                </div>
              </div>
            );
          }

          return (
            <div
              style={{
                padding: "0.25rem 0",
                color: "var(--color-text-secondary)",
                fontSize: "0.875rem",
                fontStyle: "italic",
              }}
            >
              Sin oferta disponible
            </div>
          );
        })()}

        {/* Botón de acción */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            marginTop: "0.5rem",
          }}
        >
          <span
            style={{
              fontSize: "0.8125rem",
              fontWeight: 600,
              color: "var(--color-primary)",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.25rem",
            }}
          >
            Ver detalle <ArrowRight size={14} />
          </span>
        </div>
      </div>
    </article>
  );
};
