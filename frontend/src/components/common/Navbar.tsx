import React from "react";
import { Cpu, Layers } from "lucide-react";

interface NavbarProps {
  currentPath: string;
  onNavigate: (path: string) => void;
}

export const Navbar: React.FC<NavbarProps> = ({ currentPath, onNavigate }) => {
  const handleNavClick = (e: React.MouseEvent<HTMLAnchorElement>, path: string) => {
    e.preventDefault();
    onNavigate(path);
  };

  return (
    <header
      style={{
        backgroundColor: "var(--color-surface)",
        borderBottom: "1px solid var(--color-border)",
        position: "sticky",
        top: 0,
        zIndex: 40,
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "1rem 1.5rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <a
          href="/"
          onClick={(e) => handleNavClick(e, "/")}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.625rem",
            fontWeight: 700,
            fontSize: "1.25rem",
            color: "var(--color-text-dark)",
          }}
        >
          <div
            style={{
              width: "36px",
              height: "36px",
              backgroundColor: "var(--color-primary)",
              color: "#ffffff",
              borderRadius: "var(--radius-md)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Cpu size={20} />
          </div>
          <span style={{ letterSpacing: "-0.02em" }}>PriceTrack</span>
        </a>

        <nav style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
          <a
            href="/"
            onClick={(e) => handleNavClick(e, "/")}
            style={{
              fontSize: "0.9375rem",
              fontWeight: currentPath === "/" ? 600 : 500,
              color: currentPath === "/" ? "var(--color-primary)" : "var(--color-text-secondary)",
              transition: "color 0.15s ease",
            }}
          >
            Inicio
          </a>
          <a
            href="/products"
            onClick={(e) => handleNavClick(e, "/products")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.375rem",
              fontSize: "0.9375rem",
              fontWeight: currentPath.startsWith("/products") ? 600 : 500,
              color:
                currentPath.startsWith("/products")
                  ? "var(--color-primary)"
                  : "var(--color-text-secondary)",
              transition: "color 0.15s ease",
            }}
          >
            <Layers size={16} />
            Catálogo
          </a>
        </nav>
      </div>
    </header>
  );
};
