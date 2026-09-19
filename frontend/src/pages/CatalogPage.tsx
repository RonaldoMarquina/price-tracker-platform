import React, { useCallback, useEffect, useState } from "react";
import { Layers } from "lucide-react";
import { getProducts } from "../api/products";
import { EmptyState } from "../components/common/EmptyState";
import { ErrorAlert } from "../components/common/ErrorAlert";
import { ProductCardSkeleton } from "../components/common/Skeleton";
import { ProductGrid } from "../components/product/ProductGrid";
import { CategoryFilter } from "../features/CategoryFilter";
import { Pagination } from "../features/Pagination";
import { SearchBar } from "../features/SearchBar";
import { CATEGORY_ALIASES, ProductListItemOut } from "../types/api";

const normalizeCategory = (slug?: string): string | undefined => {
  if (!slug?.trim()) return undefined;
  const lower = slug.trim().toLowerCase();
  return CATEGORY_ALIASES[lower] || lower;
};

export interface CatalogPageProps {
  initialQuery?: string;
  initialCategory?: string;
  initialPage?: number;
  onNavigate: (path: string) => void;
  updateUrlParams: (params: { q?: string; category?: string; page?: number }) => void;
}

export const CatalogPage: React.FC<CatalogPageProps> = ({
  initialQuery = "",
  initialCategory = "",
  initialPage = 1,
  onNavigate,
  updateUrlParams,
}) => {
  const [query, setQuery] = useState(initialQuery);
  const [category, setCategory] = useState<string | undefined>(normalizeCategory(initialCategory));
  const [page, setPage] = useState(initialPage);
  const pageSize = 12;

  const [products, setProducts] = useState<ProductListItemOut[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Sync internal state when external props change (e.g. browser back/forward)
  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  useEffect(() => {
    setCategory(normalizeCategory(initialCategory));
  }, [initialCategory]);

  useEffect(() => {
    setPage(initialPage);
  }, [initialPage]);

  const loadProducts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getProducts({
        q: query || undefined,
        category: category || undefined,
        page,
        page_size: pageSize,
      });
      setProducts(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar el catálogo de productos.");
    } finally {
      setIsLoading(false);
    }
  }, [query, category, page]);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  const handleSearchChange = (newQuery: string) => {
    setQuery(newQuery);
    setPage(1);
    updateUrlParams({ q: newQuery, category, page: 1 });
  };

  const handleCategoryChange = (newCategory?: string) => {
    const normalized = normalizeCategory(newCategory);
    setCategory(normalized);
    setPage(1);
    updateUrlParams({ q: query, category: normalized, page: 1 });
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    updateUrlParams({ q: query, category, page: newPage });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleResetFilters = () => {
    setQuery("");
    setCategory(undefined);
    setPage(1);
    updateUrlParams({ q: "", category: undefined, page: 1 });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
      {/* Header del Catálogo */}
      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            color: "var(--color-text-secondary)",
            fontSize: "0.875rem",
            marginBottom: "0.5rem",
          }}
        >
          <a
            href="/"
            onClick={(e) => {
              e.preventDefault();
              onNavigate("/");
            }}
            style={{ color: "var(--color-primary)" }}
          >
            Inicio
          </a>
          <span>/</span>
          <span>Catálogo</span>
        </div>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: "1rem",
          }}
        >
          <h1
            style={{
              fontSize: "1.875rem",
              fontWeight: 700,
              color: "var(--color-text-dark)",
              display: "flex",
              alignItems: "center",
              gap: "0.625rem",
            }}
          >
            <Layers size={26} color="var(--color-primary)" />
            Catálogo de Componentes
          </h1>

          {!isLoading && !error && (
            <span
              style={{
                fontSize: "0.875rem",
                color: "var(--color-text-secondary)",
                fontWeight: 500,
              }}
              data-testid="total-count"
            >
              {total} {total === 1 ? "producto encontrado" : "productos encontrados"}
            </span>
          )}
        </div>
      </div>

      {/* Barra de Filtros y Búsqueda */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
          backgroundColor: "var(--color-surface)",
          padding: "1.25rem",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--color-border)",
        }}
      >
        <SearchBar
          value={query}
          onChange={handleSearchChange}
          placeholder="Filtrar por nombre o modelo..."
        />
        <CategoryFilter selectedCategory={category} onSelectCategory={handleCategoryChange} />
      </div>

      {/* Resultados / Estados */}
      {isLoading ? (
        <div className="product-grid" data-testid="catalog-skeletons">
          {Array.from({ length: 8 }).map((_, i) => (
            <ProductCardSkeleton key={i} />
          ))}
        </div>
      ) : error ? (
        <ErrorAlert message={error} onRetry={loadProducts} />
      ) : products.length === 0 ? (
        <EmptyState
          title="No se encontraron productos"
          message="No encontramos componentes que coincidan con los filtros aplicados. Prueba buscando con otro nombre o restablece los filtros."
          onReset={handleResetFilters}
        />
      ) : (
        <>
          <ProductGrid
            products={products}
            onSelectProduct={(id) => onNavigate(`/products/${id}`)}
          />
          <Pagination
            currentPage={page}
            pageSize={pageSize}
            totalItems={total}
            onPageChange={handlePageChange}
          />
        </>
      )}
    </div>
  );
};
