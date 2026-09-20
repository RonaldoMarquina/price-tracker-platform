import React, { useState } from "react";
import { Calendar, Filter, RefreshCw, Store as StoreIcon } from "lucide-react";
import {
  CategoryFilterItem,
  PeriodPreset,
  StoreFilterItem,
} from "../../types/analytics";

export interface AnalyticsFiltersBarProps {
  categories: CategoryFilterItem[];
  stores: StoreFilterItem[];
  periods: PeriodPreset[];
  selectedCategory: string;
  selectedStore: string;
  selectedPeriod: PeriodPreset | "custom";
  customFrom: string;
  customTo: string;
  isLoading: boolean;
  onCategoryChange: (categoryId: string) => void;
  onStoreChange: (storeId: string) => void;
  onPeriodPresetChange: (period: PeriodPreset) => void;
  onCustomDatesChange: (from: string, to: string) => void;
  onRefresh: () => void;
}

export const AnalyticsFiltersBar: React.FC<AnalyticsFiltersBarProps> = ({
  categories,
  stores,
  periods,
  selectedCategory,
  selectedStore,
  selectedPeriod,
  customFrom,
  customTo,
  isLoading,
  onCategoryChange,
  onStoreChange,
  onPeriodPresetChange,
  onCustomDatesChange,
  onRefresh,
}) => {
  const [localFrom, setLocalFrom] = useState(customFrom);
  const [localTo, setLocalTo] = useState(customTo);
  const [dateError, setDateError] = useState<string | null>(null);

  const handlePeriodTabClick = (p: PeriodPreset | "custom") => {
    if (p === "custom") {
      // If switching to custom, validate if dates are already present
      if (localFrom && localTo) {
        if (localFrom > localTo) {
          setDateError("La fecha inicial no puede ser posterior a la fecha final.");
        } else {
          setDateError(null);
          onCustomDatesChange(localFrom, localTo);
        }
      }
    } else {
      setDateError(null);
      onPeriodPresetChange(p);
    }
  };

  const handleDateChange = (from: string, to: string) => {
    setLocalFrom(from);
    setLocalTo(to);

    if (from && to) {
      if (from > to) {
        setDateError("La fecha inicial no puede ser posterior a la fecha final.");
      } else {
        setDateError(null);
        onCustomDatesChange(from, to);
      }
    } else {
      setDateError(null);
    }
  };

  return (
    <nav className="analytics-filters-bar" aria-label="Filtros del dashboard analítico">
      <div className="filters-row">
        {/* Left Side: Category and Store Filters */}
        <div className="filters-left">
          {/* Category Filter */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Filter size={16} style={{ color: "var(--color-text-secondary)" }} aria-hidden="true" />
            <select
              id="analytics-category-filter"
              aria-label="Filtrar por categoría"
              className="filter-select"
              value={selectedCategory}
              onChange={(e) => onCategoryChange(e.target.value)}
              disabled={isLoading}
            >
              <option value="">Todas las categorías</option>
              {categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
            </select>
          </div>

          {/* Store Filter (for trends) */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <StoreIcon size={16} style={{ color: "var(--color-text-secondary)" }} aria-hidden="true" />
            <select
              id="analytics-store-filter"
              aria-label="Filtrar tendencias por tienda"
              className="filter-select"
              value={selectedStore}
              onChange={(e) => onStoreChange(e.target.value)}
              disabled={isLoading}
            >
              <option value="">Todas las tiendas</option>
              {stores.map((s) => (
                <option
                  key={s.id}
                  value={s.id}
                  disabled={!s.is_active}
                >
                  {s.name} {!s.is_active ? "(Inactiva)" : ""}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Right Side: Period Tabs & Refresh */}
        <div className="filters-right">
          <div className="period-tabs" role="tablist" aria-label="Selección de período temporal">
            {periods.map((p) => (
              <button
                key={p}
                type="button"
                role="tab"
                aria-selected={selectedPeriod === p}
                className={`period-tab-btn ${selectedPeriod === p ? "active" : ""}`}
                onClick={() => handlePeriodTabClick(p)}
                disabled={isLoading}
              >
                {p === "all" ? "Histórico" : p}
              </button>
            ))}
            <button
              type="button"
              role="tab"
              aria-selected={selectedPeriod === "custom"}
              className={`period-tab-btn ${selectedPeriod === "custom" ? "active" : ""}`}
              onClick={() => handlePeriodTabClick("custom")}
              disabled={isLoading}
            >
              Personalizado
            </button>
          </div>

          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={onRefresh}
            disabled={isLoading}
            aria-label="Actualizar datos del dashboard"
            title="Actualizar datos"
            style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
          >
            <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} aria-hidden="true" />
            <span>Actualizar</span>
          </button>
        </div>
      </div>

      {/* Custom Date Range Row when 'custom' is active */}
      {selectedPeriod === "custom" && (
        <div className="custom-date-row" role="region" aria-label="Rango de fechas personalizado">
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Calendar size={15} style={{ color: "var(--color-primary)" }} aria-hidden="true" />
            <span>Rango de fechas:</span>
          </div>

          <div className="date-input-group">
            <label htmlFor="analytics-from-date" style={{ fontSize: "0.75rem" }}>
              Desde:
            </label>
            <input
              id="analytics-from-date"
              type="date"
              className="date-input"
              value={localFrom}
              onChange={(e) => handleDateChange(e.target.value, localTo)}
              disabled={isLoading}
            />
          </div>

          <div className="date-input-group">
            <label htmlFor="analytics-to-date" style={{ fontSize: "0.75rem" }}>
              Hasta:
            </label>
            <input
              id="analytics-to-date"
              type="date"
              className="date-input"
              value={localTo}
              onChange={(e) => handleDateChange(localFrom, e.target.value)}
              disabled={isLoading}
            />
          </div>

          {dateError && (
            <span className="date-error-text" role="alert">
              {dateError}
            </span>
          )}
        </div>
      )}
    </nav>
  );
};
