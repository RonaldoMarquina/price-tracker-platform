import React, { useEffect, useState } from "react";
import { Footer } from "./components/common/Footer";
import { Navbar } from "./components/common/Navbar";
import { CatalogPage } from "./pages/CatalogPage";
import { HomePage } from "./pages/HomePage";
import { ProductDetailPage } from "./pages/ProductDetailPage";

export const App: React.FC = () => {
  const [currentLocation, setCurrentLocation] = useState({
    pathname: window.location.pathname,
    search: window.location.search,
  });

  useEffect(() => {
    const handlePopState = () => {
      setCurrentLocation({
        pathname: window.location.pathname,
        search: window.location.search,
      });
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigate = (to: string) => {
    const url = new URL(to, window.location.origin);
    window.history.pushState({}, "", url.toString());
    setCurrentLocation({
      pathname: url.pathname,
      search: url.search,
    });
    window.scrollTo(0, 0);
  };

  const updateUrlParams = (params: { q?: string; category?: string; page?: number }) => {
    const searchParams = new URLSearchParams();
    if (params.q?.trim()) searchParams.set("q", params.q.trim());
    if (params.category?.trim()) searchParams.set("category", params.category.trim());
    if (params.page && params.page > 1) searchParams.set("page", params.page.toString());

    const queryString = searchParams.toString();
    const newRelativePath = `${window.location.pathname}${queryString ? `?${queryString}` : ""}`;
    window.history.pushState({}, "", newRelativePath);
    setCurrentLocation({
      pathname: window.location.pathname,
      search: queryString ? `?${queryString}` : "",
    });
  };

  // Route matching
  const renderCurrentRoute = () => {
    const { pathname, search } = currentLocation;
    const searchParams = new URLSearchParams(search);

    // Detail route: /products/:id
    const productDetailMatch = pathname.match(/^\/products\/([^/]+)$/);
    if (productDetailMatch) {
      const productId = productDetailMatch[1];
      return <ProductDetailPage productId={productId} onNavigate={navigate} />;
    }

    // Catalog route: /products
    if (pathname === "/products" || pathname.startsWith("/products/")) {
      const q = searchParams.get("q") || "";
      const category = searchParams.get("category") || "";
      const pageStr = searchParams.get("page");
      const page = pageStr ? parseInt(pageStr, 10) || 1 : 1;

      return (
        <CatalogPage
          initialQuery={q}
          initialCategory={category}
          initialPage={page}
          onNavigate={navigate}
          updateUrlParams={updateUrlParams}
        />
      );
    }

    // Home route: /
    return <HomePage onNavigate={navigate} />;
  };

  return (
    <div className="app-container">
      <Navbar currentPath={currentLocation.pathname} onNavigate={navigate} />
      <main className="main-content">{renderCurrentRoute()}</main>
      <Footer />
    </div>
  );
};

export default App;
