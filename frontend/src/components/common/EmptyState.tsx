import React from "react";
import { SearchX } from "lucide-react";

export interface EmptyStateProps {
  title?: string;
  message?: string;
  onReset?: () => void;
  actionText?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = "No se encontraron productos",
  message = "No hay resultados para los filtros seleccionados. Intenta con otros términos o restablece la búsqueda.",
  onReset,
  actionText = "Restablecer filtros",
}) => {
  return (
    <div
      style={{
        padding: "3.5rem 1.5rem",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        backgroundColor: "var(--color-surface)",
        borderRadius: "var(--radius-lg)",
        border: "1px dashed var(--color-border)",
      }}
    >
      <div
        style={{
          width: "56px",
          height: "56px",
          borderRadius: "var(--radius-full)",
          backgroundColor: "#f1f5f9",
          color: "var(--color-text-secondary)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: "1rem",
        }}
      >
        <SearchX size={28} />
      </div>
      <h3
        style={{
          fontSize: "1.25rem",
          fontWeight: 600,
          color: "var(--color-text-dark)",
          marginBottom: "0.5rem",
        }}
      >
        {title}
      </h3>
      <p
        style={{
          fontSize: "0.9375rem",
          color: "var(--color-text-secondary)",
          maxWidth: "420px",
          marginBottom: onReset ? "1.5rem" : "0",
          lineHeight: 1.5,
        }}
      >
        {message}
      </p>
      {onReset && (
        <button type="button" onClick={onReset} className="btn btn-primary btn-sm">
          {actionText}
        </button>
      )}
    </div>
  );
};
