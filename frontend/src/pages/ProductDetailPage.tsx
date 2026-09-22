import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft, Clock, Cpu, Tag, TrendingDown } from "lucide-react";
import { getPriceHistory, getProductById } from "../api/products";
import { Badge } from "../components/common/Badge";
import { ErrorAlert } from "../components/common/ErrorAlert";
import { Skeleton } from "../components/common/Skeleton";
import { PriceChart } from "../components/chart/PriceChart";
import { StoreTable } from "../components/product/StoreTable";
import { formatCapturedDate } from "../utils/freshness";
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

  // Authoritative best price from backend (with legacy store scanning fallback for tests)
  const bestOffer = useMemo(() => {
    if (product?.best_price) {
      return {
        amount: product.best_price.amount,
        store: product.best_price.store_name,
        currency: product.best_price.currency,
        condition: product.best_price.price_condition,
        capturedAt: product.best_price.captured_at,
      };
    }
    if (!product || !product.stores || product.stores.length === 0) return null;
    let minAmount = Infinity;
    let minStore = "";
    let currency = "PEN";
    let capturedAt: string | undefined;

    product.stores.forEach((s) => {
      if (
        s.is_store_active !== false &&
        s.latest_price?.amount &&
        (s.latest_price.availability === "in_stock" || !s.latest_price.availability)
      ) {
        const val = parseFloat(s.latest_price.amount);
        if (!isNaN(val) && val < minAmount) {
          minAmount = val;
          minStore = s.store_name;
          currency = s.latest_price.currency || "PEN";
          capturedAt = s.latest_price.captured_at;
        }
      }
    });

    if (minAmount === Infinity) return null;
    return {
      amount: minAmount.toFixed(2),
      store: minStore,
      currency,
      condition: null,
      capturedAt,
    };
  }, [product]);

  const calculatedActiveOffersCount = useMemo(() => {
    if (product?.active_offers_count !== undefined) {
      return product.active_offers_count;
    }
    if (!product?.stores) return 0;
    return product.stores.filter(
      (s) =>
        s.is_store_active !== false &&
        s.latest_price?.amount &&
        (s.latest_price.availability === "in_stock" || !s.latest_price.availability)
    ).length;
  }, [product]);

  const hasMultipleOffers = useMemo(() => {
    if (product?.has_multiple_offers !== undefined) {
      return product.has_multiple_offers;
    }
    return calculatedActiveOffersCount >= 2;
  }, [product, calculatedActiveOffersCount]);

  const sortedStores = useMemo(() => {
    if (!product?.stores) return [];
    if (!hasMultipleOffers) return product.stores;
    return [...product.stores].sort((a, b) => {
      const aInStock =
        a.is_store_active !== false &&
        a.latest_price?.availability === "in_stock" &&
        a.latest_price?.amount;
      const bInStock =
        b.is_store_active !== false &&
        b.latest_price?.availability === "in_stock" &&
        b.latest_price?.amount;
      if (aInStock && !bInStock) return -1;
      if (!aInStock && bInStock) return 1;
      if (aInStock && bInStock) {
        return parseFloat(a.latest_price!.amount!) - parseFloat(b.latest_price!.amount!);
      }
      return 0;
    });
  }, [product?.stores, hasMultipleOffers]);

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
              {calculatedActiveOffersCount > 0 && (
                <span
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 600,
                    backgroundColor: hasMultipleOffers ? "#eff6ff" : "#f1f5f9",
                    color: hasMultipleOffers ? "#1d4ed8" : "#475569",
                    padding: "0.2rem 0.55rem",
                    borderRadius: "var(--radius-full)",
                  }}
                >
                  {hasMultipleOffers
                    ? `Disponible en ${calculatedActiveOffersCount} tiendas`
                    : "Disponible en 1 tienda"}
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
            {bestOffer ? (
              <div
                style={{
                  marginTop: "0.5rem",
                  padding: "1.25rem",
                  backgroundColor: "#f0fdf4",
                  border: "1px solid #bbf7d0",
                  borderRadius: "var(--radius-md)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
                }}
              >
                <div
                  style={{
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
                        color: hasMultipleOffers ? "#166534" : "#1e40af",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.35rem",
                        marginBottom: "0.25rem",
                      }}
                    >
                      {hasMultipleOffers ? (
                        <>
                          <TrendingDown size={14} />
                          Mejor precio actual
                        </>
                      ) : (
                        <>
                          <Tag size={14} />
                          Oferta registrada
                        </>
                      )}
                    </span>
                    <div
                      style={{
                        fontSize: "1.75rem",
                        fontWeight: 800,
                        color: "var(--color-price-down)",
                      }}
                    >
                      {bestOffer.currency} {bestOffer.amount}
                    </div>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "flex-end",
                      gap: "0.35rem",
                    }}
                  >
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
                      <span>En {bestOffer.store}</span>
                    </div>
                    {bestOffer.condition === "cash_or_bank_transfer" && (
                      <Badge variant="warning">Precio en efectivo o transferencia</Badge>
                    )}
                  </div>
                </div>

                {/* Freshness state */}
                {(() => {
                  const { state, label } = formatCapturedDate(bestOffer.capturedAt);
                  if (state === "unknown") {
                    return (
                      <div
                        style={{
                          fontSize: "0.8125rem",
                          color: "var(--color-text-secondary)",
                          borderTop: "1px solid #dcfce7",
                          paddingTop: "0.5rem",
                          fontStyle: "italic",
                        }}
                      >
                        Fecha de actualización no disponible
                      </div>
                    );
                  }
                  if (state === "stale") {
                    return (
                      <div
                        style={{
                          fontSize: "0.8125rem",
                          color: "#b45309",
                          borderTop: "1px solid #fed7aa",
                          paddingTop: "0.5rem",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.35rem",
                        }}
                      >
                        <AlertTriangle size={14} />
                        <span>Advertencia: datos observados hace más de 7 días ({label})</span>
                      </div>
                    );
                  }
                  return (
                    <div
                      style={{
                        fontSize: "0.8125rem",
                        color: "#166534",
                        borderTop: "1px solid #dcfce7",
                        paddingTop: "0.5rem",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.35rem",
                      }}
                    >
                      <Clock size={13} />
                      <span>Actualizado recientemente: {label}</span>
                    </div>
                  );
                })()}
              </div>
            ) : (
              <div
                style={{
                  marginTop: "0.5rem",
                  padding: "1rem",
                  backgroundColor: "#f8fafc",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--color-border)",
                  color: "var(--color-text-secondary)",
                  fontSize: "0.875rem",
                  fontStyle: "italic",
                }}
              >
                No se registran ofertas vigentes en stock para este producto.
              </div>
            )}
          </div>
        </div>
      ) : null}

      {/* Sección 1: Comparativa u Ofertas por Tienda */}
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
              {hasMultipleOffers
                ? "Comparativa de Precios por Tienda"
                : "Ofertas por Tienda"}
            </h2>
            <p style={{ fontSize: "0.875rem", color: "var(--color-text-secondary)" }}>
              {hasMultipleOffers
                ? "Precios y disponibilidad reportados por cada establecimiento comercial ordenados por mejor precio"
                : "Precios y disponibilidad reportados por cada establecimiento comercial"}
            </p>
          </div>

          <StoreTable stores={sortedStores} />
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
