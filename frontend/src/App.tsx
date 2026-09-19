import React from "react";

export const App: React.FC = () => {
  return (
    <main
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        padding: "2rem",
        textAlign: "center",
      }}
    >
      <div
        style={{
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: "12px",
          padding: "2.5rem 3rem",
          maxWidth: "600px",
          boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.3)",
        }}
      >
        <span
          style={{
            display: "inline-block",
            fontSize: "0.85rem",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            color: "#38bdf8",
            marginBottom: "0.75rem",
          }}
        >
          Incremento 0
        </span>
        <h1 style={{ fontSize: "2rem", marginBottom: "1rem", color: "#f8fafc" }}>
          Price Tracker Platform
        </h1>
        <p style={{ color: "#94a3b8", fontSize: "1.05rem", lineHeight: "1.6" }}>
          Estructura base del frontend inicializada correctamente. Lista para el catálogo y el
          historial de precios.
        </p>
      </div>
    </main>
  );
};

export default App;
