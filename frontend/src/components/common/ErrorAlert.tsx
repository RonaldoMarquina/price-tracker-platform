import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export interface ErrorAlertProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export const ErrorAlert: React.FC<ErrorAlertProps> = ({
  title = "Ocurrió un error al cargar la información",
  message,
  onRetry,
}) => {
  return (
    <div
      role="alert"
      style={{
        padding: "1.5rem",
        backgroundColor: "#fef2f2",
        border: "1px solid #fecaca",
        borderRadius: "var(--radius-lg)",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: "0.875rem" }}>
        <div
          style={{
            color: "var(--color-price-up)",
            flexShrink: 0,
            marginTop: "2px",
          }}
        >
          <AlertTriangle size={22} />
        </div>
        <div>
          <h4
            style={{
              fontSize: "1rem",
              fontWeight: 600,
              color: "#991b1b",
              marginBottom: "0.25rem",
            }}
          >
            {title}
          </h4>
          <p style={{ fontSize: "0.875rem", color: "#b91c1c", lineHeight: 1.4 }}>
            {message}
          </p>
        </div>
      </div>
      {onRetry && (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            type="button"
            onClick={onRetry}
            className="btn btn-outline btn-sm"
            style={{
              borderColor: "#fca5a5",
              color: "#991b1b",
              backgroundColor: "#ffffff",
            }}
          >
            <RefreshCw size={14} />
            Reintentar
          </button>
        </div>
      )}
    </div>
  );
};
