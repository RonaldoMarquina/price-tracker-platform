import React from "react";

export const Footer: React.FC = () => {
  return (
    <footer
      style={{
        backgroundColor: "var(--color-surface)",
        borderTop: "1px solid var(--color-border)",
        padding: "2rem 1.5rem",
        marginTop: "auto",
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
          textAlign: "center",
          color: "var(--color-text-secondary)",
          fontSize: "0.875rem",
        }}
      >
        <p>
          <strong>PriceTrack</strong> — Portal académico y funcional para rastrear precios históricos de
          componentes tecnológicos.
        </p>
        <p style={{ fontSize: "0.8125rem", color: "#94a3b8" }}>
          Datos recopilados con fines de monitoreo comparativo • Construido con React 18, FastAPI y PostgreSQL.
        </p>
      </div>
    </footer>
  );
};
