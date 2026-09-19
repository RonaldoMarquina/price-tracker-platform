import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

export interface PaginationProps {
  currentPage: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  pageSize,
  totalItems,
  onPageChange,
}) => {
  const totalPages = Math.ceil(totalItems / pageSize);

  if (totalPages <= 1) {
    return null;
  }

  // Generate page numbers to show
  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      if (currentPage <= 4) {
        pages.push(1, 2, 3, 4, 5, "...", totalPages);
      } else if (currentPage >= totalPages - 3) {
        pages.push(1, "...", totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
      } else {
        pages.push(1, "...", currentPage - 1, currentPage, currentPage + 1, "...", totalPages);
      }
    }
    return pages;
  };

  return (
    <nav
      aria-label="Paginación del catálogo"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "0.35rem",
        marginTop: "2.5rem",
      }}
      data-testid="pagination-nav"
    >
      <button
        type="button"
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage <= 1}
        className="btn btn-outline btn-sm"
        style={{ padding: "0.375rem 0.625rem" }}
        aria-label="Página anterior"
      >
        <ChevronLeft size={16} />
        <span style={{ display: "none" }}>Anterior</span>
      </button>

      {getPageNumbers().map((pageItem, idx) => {
        if (typeof pageItem === "string") {
          return (
            <span
              key={`ellipsis-${idx}`}
              style={{
                padding: "0.375rem 0.5rem",
                color: "var(--color-text-secondary)",
                fontSize: "0.875rem",
              }}
            >
              ...
            </span>
          );
        }

        const isCurrent = pageItem === currentPage;
        return (
          <button
            key={pageItem}
            type="button"
            onClick={() => onPageChange(pageItem)}
            className={`btn btn-sm ${isCurrent ? "btn-primary" : "btn-outline"}`}
            style={{
              minWidth: "36px",
              padding: "0.375rem 0.5rem",
              fontWeight: isCurrent ? 700 : 500,
            }}
            aria-current={isCurrent ? "page" : undefined}
          >
            {pageItem}
          </button>
        );
      })}

      <button
        type="button"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage >= totalPages}
        className="btn btn-outline btn-sm"
        style={{ padding: "0.375rem 0.625rem" }}
        aria-label="Página siguiente"
      >
        <ChevronRight size={16} />
        <span style={{ display: "none" }}>Siguiente</span>
      </button>
    </nav>
  );
};
