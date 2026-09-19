import React, { useEffect, useState } from "react";
import { ArrowRight, CircuitBoard, Cpu, Fan, HardDrive, Monitor, Zap } from "lucide-react";
import { getProducts } from "../api/products";
import { ErrorAlert } from "../components/common/ErrorAlert";
import { ProductCardSkeleton } from "../components/common/Skeleton";
import { ProductGrid } from "../components/product/ProductGrid";
import { SearchBar } from "../features/SearchBar";
import { ProductListItemOut } from "../types/api";

export interface HomePageProps {
  onNavigate: (path: string) => void;
}

export const HomePage: React.FC<HomePageProps> = ({ onNavigate }) => {
  const [products, setProducts] = useState<ProductListItemOut[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSampleProducts = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getProducts({ page: 1, page_size: 4 });
      setProducts(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar productos iniciales.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSampleProducts();
  }, []);

  const handleSearch = (query: string) => {
    if (query.trim()) {
      onNavigate(`/products?q=${encodeURIComponent(query.trim())}`);
    }
  };

  const handleCategoryClick = (categorySlug: string) => {
    onNavigate(`/products?category=${encodeURIComponent(categorySlug)}`);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "3.5rem" }}>
      {/* Hero Section */}
      <section
        style={{
          textAlign: "center",
          padding: "3rem 1rem 1.5rem",
          maxWidth: "800px",
          margin: "0 auto",
        }}
      >
        <span
          style={{
            display: "inline-block",
            fontSize: "0.8125rem",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "var(--color-primary)",
            backgroundColor: "#eff6ff",
            padding: "0.25rem 0.75rem",
            borderRadius: "var(--radius-full)",
            marginBottom: "1rem",
          }}
        >
          Comparador de Hardware y Componentes
        </span>
        <h1
          style={{
            fontSize: "clamp(2rem, 4vw, 2.75rem)",
            fontWeight: 800,
            lineHeight: 1.2,
            color: "var(--color-text-dark)",
            marginBottom: "1rem",
            letterSpacing: "-0.03em",
          }}
        >
          Encuentra el mejor precio para tu próxima PC
        </h1>
        <p
          style={{
            fontSize: "1.125rem",
            color: "var(--color-text-secondary)",
            lineHeight: 1.6,
            marginBottom: "2rem",
          }}
        >
          Rastreo de precios históricos y comparativa entre tiendas para que compres en el mejor momento.
        </p>

        {/* Buscador Destacado */}
        <div style={{ maxWidth: "600px", margin: "0 auto 1.5rem" }}>
          <SearchBar value="" onChange={handleSearch} placeholder="Buscar procesador, tarjeta gráfica, RAM..." />
        </div>

        {/* Categorías Rápidas */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexWrap: "wrap",
            gap: "0.75rem",
          }}
        >
          <button
            type="button"
            onClick={() => handleCategoryClick("procesadores")}
            className="btn btn-outline btn-sm"
            style={{ borderRadius: "var(--radius-full)" }}
          >
            <Cpu size={15} />
            Procesadores
          </button>
          <button
            type="button"
            onClick={() => handleCategoryClick("tarjetas-de-video")}
            className="btn btn-outline btn-sm"
            style={{ borderRadius: "var(--radius-full)" }}
          >
            <Monitor size={15} />
            Tarjetas de Video
          </button>
          <button
            type="button"
            onClick={() => handleCategoryClick("memorias-ram")}
            className="btn btn-outline btn-sm"
            style={{ borderRadius: "var(--radius-full)" }}
          >
            <HardDrive size={15} />
            Memorias RAM
          </button>
          <button
            type="button"
            onClick={() => handleCategoryClick("placas-madre")}
            className="btn btn-outline btn-sm"
            style={{ borderRadius: "var(--radius-full)" }}
          >
            <CircuitBoard size={15} />
            Placas Madre
          </button>
          <button
            type="button"
            onClick={() => handleCategoryClick("fuentes-de-poder")}
            className="btn btn-outline btn-sm"
            style={{ borderRadius: "var(--radius-full)" }}
          >
            <Zap size={15} />
            Fuentes de Poder
          </button>
          <button
            type="button"
            onClick={() => handleCategoryClick("refrigeracion")}
            className="btn btn-outline btn-sm"
            style={{ borderRadius: "var(--radius-full)" }}
          >
            <Fan size={15} />
            Refrigeración
          </button>
        </div>
      </section>

      {/* Sección de Muestra del Catálogo */}
      <section>
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            marginBottom: "1.5rem",
            borderBottom: "1px solid var(--color-border)",
            paddingBottom: "0.75rem",
          }}
        >
          <div>
            <h2
              style={{
                fontSize: "1.5rem",
                fontWeight: 700,
                color: "var(--color-text-dark)",
                letterSpacing: "-0.02em",
              }}
            >
              Productos del catálogo
            </h2>
            <p style={{ fontSize: "0.875rem", color: "var(--color-text-secondary)" }}>
              Explora los primeros componentes registrados en la plataforma
            </p>
          </div>
          <button
            type="button"
            onClick={() => onNavigate("/products")}
            className="btn btn-outline btn-sm"
          >
            Ver catálogo completo <ArrowRight size={14} />
          </button>
        </div>

        {isLoading ? (
          <div className="product-grid" data-testid="sample-skeletons">
            {Array.from({ length: 4 }).map((_, i) => (
              <ProductCardSkeleton key={i} />
            ))}
          </div>
        ) : error ? (
          <ErrorAlert message={error} onRetry={fetchSampleProducts} />
        ) : products.length > 0 ? (
          <ProductGrid
            products={products}
            onSelectProduct={(id) => onNavigate(`/products/${id}`)}
          />
        ) : (
          <p style={{ color: "var(--color-text-secondary)", textAlign: "center", padding: "2rem" }}>
            El catálogo aún no cuenta con productos disponibles.
          </p>
        )}
      </section>
    </div>
  );
};
