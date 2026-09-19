import React, { useEffect, useState } from "react";
import { Search, X } from "lucide-react";

export interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  value,
  onChange,
  placeholder = "Buscar componentes (ej. Ryzen 7, RTX 4070, DDR5)...",
  autoFocus = false,
}) => {
  const [internalValue, setInternalValue] = useState(value);

  useEffect(() => {
    setInternalValue(value);
  }, [value]);

  useEffect(() => {
    const handler = setTimeout(() => {
      if (internalValue !== value) {
        onChange(internalValue);
      }
    }, 350);

    return () => clearTimeout(handler);
  }, [internalValue, onChange, value]);

  const handleClear = () => {
    setInternalValue("");
    onChange("");
  };

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        display: "flex",
        alignItems: "center",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: "1rem",
          color: "var(--color-text-secondary)",
          display: "flex",
          alignItems: "center",
          pointerEvents: "none",
        }}
      >
        <Search size={18} />
      </div>

      <input
        type="text"
        value={internalValue}
        onChange={(e) => setInternalValue(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        style={{
          width: "100%",
          padding: "0.75rem 2.75rem 0.75rem 2.75rem",
          fontSize: "0.9375rem",
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--color-border)",
          backgroundColor: "var(--color-surface)",
          color: "var(--color-text-dark)",
          outline: "none",
          transition: "border-color 0.15s ease, box-shadow 0.15s ease",
        }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = "var(--color-primary)";
          e.currentTarget.style.boxShadow = "0 0 0 3px rgba(37, 99, 235, 0.12)";
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = "var(--color-border)";
          e.currentTarget.style.boxShadow = "none";
        }}
        data-testid="search-input"
      />

      {internalValue && (
        <button
          type="button"
          onClick={handleClear}
          aria-label="Limpiar búsqueda"
          style={{
            position: "absolute",
            right: "0.875rem",
            background: "none",
            border: "none",
            color: "var(--color-text-secondary)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            padding: "0.25rem",
            borderRadius: "var(--radius-full)",
          }}
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
};
