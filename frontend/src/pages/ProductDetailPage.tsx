import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Cpu, Tag, TrendingDown } from "lucide-react";
import { getPriceHistory, getProductById } from "../api/products";
import { Badge } from "../components/common/Badge";
import { ErrorAlert } from "../components/common/ErrorAlert";
import { Skeleton } from "../components/common/Skeleton";
import { PriceChart } from "../components/chart/PriceChart";
import { StoreTable } from "../components/product/StoreTable";
import {
  PriceHistoryParams,
  ProductDetailOut,
  ProductPriceHistoryResponse,
} from "../types/api";

export interface ProductDetailPageProps {
  productId: string;
  onNavigate: (path: string) => void;
}

export const ProductDetailPage: React.FC<ProductDetailPageProps> = ({
  productId,
  onNavigate,
}) => {
  const [product, setProduct] = useState<ProductDetailOut | null>(null);
  const [history, setHistory] = useState<ProductPriceHistoryResponse | null>(null);
  const [isLoadingProduct, setIsLoadingProduct] = useState<boolean>(true);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(true);
  const [productError, setProductError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // Time range filter: "1M" | "3M" | "ALL"
  const [selectedRange, setSelectedRange] = useState<"1M" | "3M" | "ALL">("ALL");
  const [selectedStoreId, setSelectedStoreId] = useState<string | undefined>(undefined);
  const [imageError, setImageError] = useState<boolean>(false);

  // Helper to format ISO date string (YYYY-MM-DD)
  const formatDateParam = (date: Date): string => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  };

  const calculateDateRange = useCallback((range: "1M" | "3M" | "ALL"): { from?: string; to?: string } => {
    if (range === "ALL") return {};
    const today = new Date();
    const to = formatDateParam(today);
    const past = new Date(today);
    if (range === "1M") {
      past.setDate(past.getDate() - 30);
    } else if (range === "3M") {
      past.setDate(past.getDate() - 90);
    }
    const from = formatDateParam(past);
    return { from, to };
  }, []);

  const loadProductDetail = useCallback(async () => {
    setIsLoadingProduct(true);
    setProductError(null);
    try {
      const data = await getProductById(productId);
      setProduct(data);
    } catch (err) {
      setProductError(err instanceof Error ? err.message : "Error al cargar detalle del producto.");
    } finally {
      setIsLoadingProduct(false);
    }
  }, [productId]);

  const loadHistory = useCallback(async () => {
    setIsLoadingHistory(true);
    setHistoryError(null);
    try {
      const { from, to } = calculateDateRange(selectedRange);
      const params: PriceHistoryParams = {
        store_id: selectedStoreId,
        from,
        to,
      };
      const data = await getPriceHistory(productId, params);
      setHistory(data);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : "Error al cargar historial de precios.");
    } finally {
      setIsLoadingHistory(false);
    }
  }, [calculateDateRange, productId, selectedRange, selectedStoreId]);

  useEffect(() => {
    loadProductDetail();
  }, [loadProductDetail]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // Compute lowest price across available stores
  const lowestPriceInfo = useMemo(() => {
    if (!product || !product.stores || product.stores.length === 0) return null;
    let minAmount = Infinity;
    let minStore = "";
    let currency = "PEN";

    product.stores.forEach((s) => {
      if (s.latest_price?.amount) {
        const val = parseFloat(s.latest_price.amount);
        if (!isNaN(val) && val < minAmount) {
          minAmount = val;
          minStore = s.store_name;
          currency = s.latest_price.currency;
        }
      }
    });

    if (minAmount === Infinity) return null;
    return {
      amount: minAmount.toFixed(2),
      store: minStore,
      currency,
    };
  }, [product]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2.5rem" }}>
      {/* Breadcrumb & Botón Volver */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <button
          type="button"
          onClick={() => onNavigate("/products")}
          className="btn btn-outline btn-sm"
        >
          <ArrowLeft size={16} />
          Volver al catálogo
        </button>

        {product && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              fontSize: "0.8125rem",
              color: "var(--color-text-secondary)",
            }}
          >
            <span>Inicio</span>
            <span>/</span>
            <span>{product.category.name}</span>
            <span>/</span>
            <span style={{ fontWeight: 600, color: "var(--color-text-dark)" }}>{product.name}</span>
          </div>
        )}
      </div>

      {/* Ficha Principal del Producto */}
      {isLoadingProduct ? (
        <div
          className="card"
          style={{
            padding: "2rem",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: "2rem",
          }}
          data-testid="detail-skeleton"
        >
          <Skeleton height="260px" borderRadius="var(--radius-lg)" />
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <Skeleton width="30%" height="1.5rem" borderRadius="var(--radius-full)" />
            <Skeleton width="80%" height="2rem" />
            <Skeleton width="40%" height="1rem" />
            <Skeleton width="60%" height="3rem" style={{ marginTop: "1rem" }} />
          </div>
        </div>
      ) : productError ? (
        <ErrorAlert message={productError} onRetry={loadProductDetail} />
      ) : product ? (
        <div
          className="card"
          style={{
            padding: "2rem",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: "2.5rem",
            alignItems: "center",
          }}
          data-testid="product-detail"
        >
          {/* Imagen */}
          <div
            style={{
              height: "280px",
              backgroundColor: "#f8fafc",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--color-border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              overflow: "hidden",
            }}
          >
            {product.image_url && !imageError ? (
              <img
                src={product.image_url}
                alt={product.name}
                onError={() => setImageError(true)}
                style={{
                  maxWidth: "90%",
                  maxHeight: "90%",
                  objectFit: "contain",
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
                <Cpu size={56} strokeWidth={1.5} />
                <span style={{ fontSize: "0.875rem" }}>Sin imagen disponible</span>
              </div>
            )}
          </div>

          {/* Detalles Técnicos y Precio */}
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <Badge variant="primary">{product.category.name}</Badge>
              {product.brand && (
                <span
                  style={{
                    fontSize: "0.8125rem",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    color: "var(--color-text-secondary)",
                  }}
                >
                  {product.brand}
                </span>
              )}
            </div>

            <h1
              style={{
                fontSize: "1.75rem",
                fontWeight: 800,
                color: "var(--color-text-dark)",
                lineHeight: 1.25,
                letterSpacing: "-0.02em",
              }}
            >
              {product.name}
            </h1>

            {product.model && (
              <p style={{ fontSize: "0.875rem", color: "var(--color-text-secondary)" }}>
                Modelo: <strong style={{ color: "var(--color-text-dark)" }}>{product.model}</strong>
              </p>
            )}

            {/* Mejor Precio Destacado */}
            {lowestPriceInfo ? (
              <div
                style={{
                  marginTop: "0.5rem",
                  padding: "1.25rem",
                  backgroundColor: "#f0fdf4",
                  border: "1px solid #bbf7d0",
                  borderRadius: "var(--radius-md)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "1rem",
                }}
              >
                <div>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      color: "#166534",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.35rem",
                      marginBottom: "0.25rem",
                    }}
                  >
                    <TrendingDown size={14} />
                    Mejor precio actual
                  </span>
                  <div
                    style={{
                      fontSize: "1.75rem",
                      fontWeight: 800,
                      color: "var(--color-price-down)",
                    }}
                  >
                    {lowestPriceInfo.currency} {lowestPriceInfo.amount}
                  </div>
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.35rem",
                    color: "#15803d",
                    fontSize: "0.875rem",
                    fontWeight: 600,
                  }}
                >
                  <Tag size={16} />
                  <span>En {lowestPriceInfo.store}</span>
                </div>
              </div>
            ) : (
              <div
                style={{
                  marginTop: "0.5rem",
                  padding: "1rem",
                  backgroundColor: "#f8fafc",
                  borderRadius: "var(--radius-md)",
                  color: "var(--color-text-secondary)",
                  fontSize: "0.875rem",
                  fontStyle: "italic",
                }}
              >
                No se registran precios vigentes para este producto.
              </div>
            )}
          </div>
        </div>
      ) : null}

      {/* Sección 1: Comparativa de Tiendas */}
      {product && (
        <section>
          <div style={{ marginBottom: "1rem" }}>
            <h2
              style={{
                fontSize: "1.25rem",
                fontWeight: 700,
                color: "var(--color-text-dark)",
                marginBottom: "0.25rem",
              }}
            >
              Comparativa de Precios por Tienda
            </h2>
            <p style={{ fontSize: "0.875rem", color: "var(--color-text-secondary)" }}>
              Precios y disponibilidad reportados por cada establecimiento comercial
            </p>
          </div>

          <StoreTable stores={product.stores} />
        </section>
      )}

      {/* Sección 2: Gráfico Histórico */}
      <section>
        {isLoadingHistory ? (
          <div
            className="card"
            style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1rem" }}
          >
            <Skeleton width="40%" height="1.5rem" />
            <Skeleton height="280px" borderRadius="var(--radius-md)" />
          </div>
        ) : historyError ? (
          <ErrorAlert message={historyError} onRetry={loadHistory} />
        ) : history ? (
          <PriceChart
            history={history}
            selectedRange={selectedRange}
            selectedStoreId={selectedStoreId}
            onRangeChange={setSelectedRange}
            onStoreChange={setSelectedStoreId}
          />
        ) : null}
      </section>
    </div>
  );
};
