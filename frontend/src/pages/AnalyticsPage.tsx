import React, { useCallback, useEffect, useRef, useState } from "react";
import { BarChart3, Clock } from "lucide-react";
import {
  getAnalyticsFilters,
  getAnalyticsSummary,
  getPriceSpread,
  getPriceTrends,
  getStoresCompetitiveness,
} from "../api/analytics";
import { AnalyticsFiltersBar } from "../components/analytics/AnalyticsFiltersBar";
import { AnalyticsKpis } from "../components/analytics/AnalyticsKpis";
import { AnalyticsTrendsChart } from "../components/analytics/AnalyticsTrendsChart";
import { PriceSpreadTable } from "../components/analytics/PriceSpreadTable";
import { StoreCompetitivenessGrid } from "../components/analytics/StoreCompetitivenessGrid";
import {
  AnalyticsFiltersResponse,
  AnalyticsSummaryResponse,
  PeriodPreset,
  PriceSpreadResponse,
  PriceTrendsResponse,
  StoresCompetitivenessResponse,
} from "../types/analytics";
import { formatAnalyticsAsOf } from "../utils/formatters";
import "../components/analytics/analytics.css";

export interface AnalyticsPageProps {
  onNavigate: (path: string) => void;
}

export const AnalyticsPage: React.FC<AnalyticsPageProps> = ({ onNavigate }) => {
  // Read initial filter values from URL query string
  const parseUrlParams = () => {
    const params = new URLSearchParams(window.location.search);
    const category = params.get("category") || "";
    const store = params.get("store") || "";
    const periodParam = params.get("period") as PeriodPreset | null;
    const fromParam = params.get("from") || "";
    const toParam = params.get("to") || "";

    const isCustom = Boolean(fromParam && toParam);
    const validPresets: PeriodPreset[] = ["7d", "30d", "90d", "all"];
    const period: PeriodPreset | "custom" = isCustom
      ? "custom"
      : periodParam && validPresets.includes(periodParam)
      ? periodParam
      : "30d";

    return {
      category,
      store,
      period,
      customFrom: fromParam,
      customTo: toParam,
    };
  };

  const initial = parseUrlParams();

  // Filter States
  const [selectedCategory, setSelectedCategory] = useState<string>(initial.category);
  const [selectedStore, setSelectedStore] = useState<string>(initial.store);
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodPreset | "custom">(initial.period);
  const [customFrom, setCustomFrom] = useState<string>(initial.customFrom);
  const [customTo, setCustomTo] = useState<string>(initial.customTo);

  // Module Independent States
  const [filtersData, setFiltersData] = useState<AnalyticsFiltersResponse>({
    categories: [],
    stores: [],
    periods: ["7d", "30d", "90d", "all"],
  });
  const [filtersLoading, setFiltersLoading] = useState<boolean>(true);

  const [summaryData, setSummaryData] = useState<AnalyticsSummaryResponse | null>(null);
  const [summaryLoading, setSummaryLoading] = useState<boolean>(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const [spreadData, setSpreadData] = useState<PriceSpreadResponse | null>(null);
  const [spreadLoading, setSpreadLoading] = useState<boolean>(true);
  const [spreadError, setSpreadError] = useState<string | null>(null);

  const [storesData, setStoresData] = useState<StoresCompetitivenessResponse | null>(null);
  const [storesLoading, setStoresLoading] = useState<boolean>(true);
  const [storesError, setStoresError] = useState<string | null>(null);

  const [trendsData, setTrendsData] = useState<PriceTrendsResponse | null>(null);
  const [trendsLoading, setTrendsLoading] = useState<boolean>(true);
  const [trendsError, setTrendsError] = useState<string | null>(null);

  // Request race-condition controllers and IDs ("Latest Request Wins")
  const summaryReqId = useRef(0);
  const summaryAbort = useRef<AbortController | null>(null);

  const spreadReqId = useRef(0);
  const spreadAbort = useRef<AbortController | null>(null);

  const storesReqId = useRef(0);
  const storesAbort = useRef<AbortController | null>(null);

  const trendsReqId = useRef(0);
  const trendsAbort = useRef<AbortController | null>(null);

  const isMounted = useRef(true);

  // Synchronize state changes to URL
  const updateUrl = useCallback(
    (newFilters: {
      category: string;
      store: string;
      period: PeriodPreset | "custom";
      from: string;
      to: string;
    }) => {
      const searchParams = new URLSearchParams();
      if (newFilters.category.trim()) {
        searchParams.set("category", newFilters.category.trim());
      }
      if (newFilters.store.trim()) {
        searchParams.set("store", newFilters.store.trim());
      }

      if (newFilters.period === "custom") {
        if (newFilters.from.trim()) searchParams.set("from", newFilters.from.trim());
        if (newFilters.to.trim()) searchParams.set("to", newFilters.to.trim());
      } else {
        if (newFilters.period !== "30d") {
          searchParams.set("period", newFilters.period);
        }
      }

      const queryString = searchParams.toString();
      const newRelativePath = `${window.location.pathname}${queryString ? `?${queryString}` : ""}`;
      window.history.pushState({}, "", newRelativePath);
    },
    [],
  );

  // 1. Fetch Filters (Only once on mount)
  const fetchFilters = useCallback(async () => {
    try {
      setFiltersLoading(true);
      const res = await getAnalyticsFilters();
      if (isMounted.current) {
        setFiltersData(res);
      }
    } catch {
      // Keep defaults if failed
    } finally {
      if (isMounted.current) {
        setFiltersLoading(false);
      }
    }
  }, []);

  // 2. Fetch Summary
  const fetchSummary = useCallback(async (catId: string) => {
    if (summaryAbort.current) summaryAbort.current.abort();
    summaryAbort.current = new AbortController();
    const currentId = ++summaryReqId.current;

    setSummaryLoading(true);
    setSummaryError(null);

    try {
      const res = await getAnalyticsSummary(catId, summaryAbort.current.signal);
      if (isMounted.current && currentId === summaryReqId.current) {
        setSummaryData(res);
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      if (isMounted.current && currentId === summaryReqId.current) {
        setSummaryError(err instanceof Error ? err.message : "Error al cargar resumen");
      }
    } finally {
      if (isMounted.current && currentId === summaryReqId.current) {
        setSummaryLoading(false);
      }
    }
  }, []);

  // 3. Fetch Price Spread
  const fetchSpread = useCallback(async (catId: string) => {
    if (spreadAbort.current) spreadAbort.current.abort();
    spreadAbort.current = new AbortController();
    const currentId = ++spreadReqId.current;

    setSpreadLoading(true);
    setSpreadError(null);

    try {
      const res = await getPriceSpread(catId, 10, spreadAbort.current.signal);
      if (isMounted.current && currentId === spreadReqId.current) {
        setSpreadData(res);
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      if (isMounted.current && currentId === spreadReqId.current) {
        setSpreadError(err instanceof Error ? err.message : "Error al cargar dispersión");
      }
    } finally {
      if (isMounted.current && currentId === spreadReqId.current) {
        setSpreadLoading(false);
      }
    }
  }, []);

  // 4. Fetch Stores Competitiveness
  const fetchStores = useCallback(async (catId: string) => {
    if (storesAbort.current) storesAbort.current.abort();
    storesAbort.current = new AbortController();
    const currentId = ++storesReqId.current;

    setStoresLoading(true);
    setStoresError(null);

    try {
      const res = await getStoresCompetitiveness(catId, storesAbort.current.signal);
      if (isMounted.current && currentId === storesReqId.current) {
        setStoresData(res);
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      if (isMounted.current && currentId === storesReqId.current) {
        setStoresError(err instanceof Error ? err.message : "Error al cargar competitividad");
      }
    } finally {
      if (isMounted.current && currentId === storesReqId.current) {
        setStoresLoading(false);
      }
    }
  }, []);

  // 5. Fetch Trends
  const fetchTrends = useCallback(
    async (
      catId: string,
      storeId: string,
      period: PeriodPreset | "custom",
      from: string,
      to: string,
    ) => {
      // Do not query if custom is selected but missing one of the dates or from > to
      if (period === "custom") {
        if (!from || !to || from > to) {
          return;
        }
      }

      if (trendsAbort.current) trendsAbort.current.abort();
      trendsAbort.current = new AbortController();
      const currentId = ++trendsReqId.current;

      setTrendsLoading(true);
      setTrendsError(null);

      try {
        const fromIso = period === "custom" && from ? `${from}T00:00:00Z` : undefined;
        const toIso = period === "custom" && to ? `${to}T23:59:59Z` : undefined;

        const res = await getPriceTrends(
          {
            category_id: catId || undefined,
            store_id: storeId || undefined,
            period: period !== "custom" ? period : undefined,
            from_date: fromIso,
            to_date: toIso,
          },
          trendsAbort.current.signal,
        );

        if (isMounted.current && currentId === trendsReqId.current) {
          setTrendsData(res);
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") return;
        if (isMounted.current && currentId === trendsReqId.current) {
          setTrendsError(err instanceof Error ? err.message : "Error al cargar tendencias");
        }
      } finally {
        if (isMounted.current && currentId === trendsReqId.current) {
          setTrendsLoading(false);
        }
      }
    },
    [],
  );

  // Initial Load on mount
  useEffect(() => {
    isMounted.current = true;
    fetchFilters();
    fetchSummary(selectedCategory);
    fetchSpread(selectedCategory);
    fetchStores(selectedCategory);
    fetchTrends(selectedCategory, selectedStore, selectedPeriod, customFrom, customTo);

    // Popstate listener to restore filters on browser navigation
    const handlePopState = () => {
      const parsed = parseUrlParams();
      setSelectedCategory(parsed.category);
      setSelectedStore(parsed.store);
      setSelectedPeriod(parsed.period);
      setCustomFrom(parsed.customFrom);
      setCustomTo(parsed.customTo);

      fetchSummary(parsed.category);
      fetchSpread(parsed.category);
      fetchStores(parsed.category);
      fetchTrends(parsed.category, parsed.store, parsed.period, parsed.customFrom, parsed.customTo);
    };

    window.addEventListener("popstate", handlePopState);

    return () => {
      isMounted.current = false;
      window.removeEventListener("popstate", handlePopState);
      if (summaryAbort.current) summaryAbort.current.abort();
      if (spreadAbort.current) spreadAbort.current.abort();
      if (storesAbort.current) storesAbort.current.abort();
      if (trendsAbort.current) trendsAbort.current.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run only on mount

  // Handler: Change Category (reloads summary, spread, stores, trends - NOT filters)
  const handleCategoryChange = (catId: string) => {
    setSelectedCategory(catId);
    updateUrl({
      category: catId,
      store: selectedStore,
      period: selectedPeriod,
      from: customFrom,
      to: customTo,
    });
    fetchSummary(catId);
    fetchSpread(catId);
    fetchStores(catId);
    fetchTrends(catId, selectedStore, selectedPeriod, customFrom, customTo);
  };

  // Handler: Change Store (reloads ONLY trends)
  const handleStoreChange = (storeId: string) => {
    setSelectedStore(storeId);
    updateUrl({
      category: selectedCategory,
      store: storeId,
      period: selectedPeriod,
      from: customFrom,
      to: customTo,
    });
    fetchTrends(selectedCategory, storeId, selectedPeriod, customFrom, customTo);
  };

  // Handler: Change Period Preset (reloads ONLY trends)
  const handlePeriodPresetChange = (p: PeriodPreset) => {
    setSelectedPeriod(p);
    setCustomFrom("");
    setCustomTo("");
    updateUrl({
      category: selectedCategory,
      store: selectedStore,
      period: p,
      from: "",
      to: "",
    });
    fetchTrends(selectedCategory, selectedStore, p, "", "");
  };

  // Handler: Change Custom Dates (reloads ONLY trends if both dates are valid)
  const handleCustomDatesChange = (from: string, to: string) => {
    setSelectedPeriod("custom");
    setCustomFrom(from);
    setCustomTo(to);
    updateUrl({
      category: selectedCategory,
      store: selectedStore,
      period: "custom",
      from,
      to,
    });
    if (from && to && from <= to) {
      fetchTrends(selectedCategory, selectedStore, "custom", from, to);
    }
  };

  // Handler: Refresh Button (reloads the 4 analytical modules, keeps filters)
  const handleRefresh = () => {
    fetchSummary(selectedCategory);
    fetchSpread(selectedCategory);
    fetchStores(selectedCategory);
    fetchTrends(selectedCategory, selectedStore, selectedPeriod, customFrom, customTo);
  };

  return (
    <div className="analytics-container">
      {/* Header */}
      <header className="analytics-header">
        <div className="analytics-title-group">
          <h1 style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
            <BarChart3 size={28} style={{ color: "var(--color-primary)" }} aria-hidden="true" />
            <span>Dashboard Analítico</span>
          </h1>
          <p>Inteligencia de mercado, ahorro y competitividad de componentes tecnológicos en Perú.</p>
        </div>
        <div className="analytics-actions">
          <div className="analytics-meta-badge" role="status" aria-label="Fecha de corte de datos">
            <Clock size={14} aria-hidden="true" />
            <span>{formatAnalyticsAsOf(summaryData?.as_of)}</span>
          </div>
        </div>
      </header>

      {/* Filters Bar */}
      <AnalyticsFiltersBar
        categories={filtersData.categories}
        stores={filtersData.stores}
        periods={filtersData.periods}
        selectedCategory={selectedCategory}
        selectedStore={selectedStore}
        selectedPeriod={selectedPeriod}
        customFrom={customFrom}
        customTo={customTo}
        isLoading={filtersLoading}
        onCategoryChange={handleCategoryChange}
        onStoreChange={handleStoreChange}
        onPeriodPresetChange={handlePeriodPresetChange}
        onCustomDatesChange={handleCustomDatesChange}
        onRefresh={handleRefresh}
      />

      {/* 1. KPIs */}
      <AnalyticsKpis
        summary={summaryData}
        isLoading={summaryLoading}
        error={summaryError}
        onRetry={() => fetchSummary(selectedCategory)}
      />

      {/* 2. Price Spread Ranking Table */}
      <PriceSpreadTable
        items={spreadData?.items || []}
        isLoading={spreadLoading}
        error={spreadError}
        onNavigate={onNavigate}
        onRetry={() => fetchSpread(selectedCategory)}
      />

      {/* 3. Store Competitiveness Grid */}
      <StoreCompetitivenessGrid
        stores={storesData?.stores || []}
        isLoading={storesLoading}
        error={storesError}
        onRetry={() => fetchStores(selectedCategory)}
      />

      {/* 4. Trends Chart */}
      <AnalyticsTrendsChart
        points={trendsData?.points || []}
        isLoading={trendsLoading}
        error={trendsError}
        onRetry={() =>
          fetchTrends(selectedCategory, selectedStore, selectedPeriod, customFrom, customTo)
        }
      />
    </div>
  );
};
