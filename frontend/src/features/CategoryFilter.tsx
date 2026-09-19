import React from "react";
import { CATEGORY_ALIASES } from "../types/api";

export interface CategoryOption {
  label: string;
  slug?: string;
}

const DEFAULT_CATEGORIES: CategoryOption[] = [
  { label: "Todos", slug: undefined },
  { label: "Procesadores", slug: "procesadores" },
  { label: "Tarjetas de Video", slug: "tarjetas-de-video" },
  { label: "Memorias RAM", slug: "memorias-ram" },
  { label: "Placas Madre", slug: "placas-madre" },
  { label: "Fuentes de Poder", slug: "fuentes-de-poder" },
  { label: "Refrigeración", slug: "refrigeracion" },
];

export interface CategoryFilterProps {
  selectedCategory?: string;
  onSelectCategory: (categorySlug?: string) => void;
  categories?: CategoryOption[];
}

export const CategoryFilter: React.FC<CategoryFilterProps> = ({
  selectedCategory,
  onSelectCategory,
  categories = DEFAULT_CATEGORIES,
}) => {
  const normalizedSelected = selectedCategory
    ? CATEGORY_ALIASES[selectedCategory.toLowerCase()] || selectedCategory.toLowerCase()
    : undefined;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.5rem",
        overflowX: "auto",
        paddingBottom: "0.25rem",
      }}
      data-testid="category-filter"
    >
      {categories.map((cat) => {
        const isSelected = normalizedSelected === cat.slug;
        return (
          <button
            key={cat.slug || "all"}
            type="button"
            onClick={() => onSelectCategory(cat.slug)}
            className={`btn btn-sm ${isSelected ? "btn-primary" : "btn-outline"}`}
            style={{
              whiteSpace: "nowrap",
              borderRadius: "var(--radius-full)",
              padding: "0.375rem 1rem",
              fontSize: "0.8125rem",
            }}
            data-testid={`category-btn-${cat.slug || "all"}`}
          >
            {cat.label}
          </button>
        );
      })}
    </div>
  );
};
