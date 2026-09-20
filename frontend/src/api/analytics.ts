/**
 * API client methods for the analytical dashboard endpoints.
 */

import {
  AnalyticsFiltersResponse,
  AnalyticsSummaryResponse,
  PriceSpreadResponse,
  PriceTrendsParams,
  PriceTrendsResponse,
  StoresCompetitivenessResponse,
} from "../types/analytics";
import { apiClient } from "./client";

export async function getAnalyticsFilters(
  signal?: AbortSignal,
): Promise<AnalyticsFiltersResponse> {
  return apiClient<AnalyticsFiltersResponse>("/analytics/filters", { signal });
}

export async function getAnalyticsSummary(
  categoryId?: string,
  signal?: AbortSignal,
): Promise<AnalyticsSummaryResponse> {
  const query = new URLSearchParams();
  if (categoryId?.trim()) {
    query.set("category_id", categoryId.trim());
  }

  const queryString = query.toString();
  const endpoint = `/analytics/summary${queryString ? `?${queryString}` : ""}`;
  return apiClient<AnalyticsSummaryResponse>(endpoint, { signal });
}

export async function getPriceSpread(
  categoryId?: string,
  limit?: number,
  signal?: AbortSignal,
): Promise<PriceSpreadResponse> {
  const query = new URLSearchParams();
  if (categoryId?.trim()) {
    query.set("category_id", categoryId.trim());
  }
  if (limit && limit > 0) {
    query.set("limit", limit.toString());
  }

  const queryString = query.toString();
  const endpoint = `/analytics/price-spread${queryString ? `?${queryString}` : ""}`;
  return apiClient<PriceSpreadResponse>(endpoint, { signal });
}

export async function getStoresCompetitiveness(
  categoryId?: string,
  signal?: AbortSignal,
): Promise<StoresCompetitivenessResponse> {
  const query = new URLSearchParams();
  if (categoryId?.trim()) {
    query.set("category_id", categoryId.trim());
  }

  const queryString = query.toString();
  const endpoint = `/analytics/stores-competitiveness${queryString ? `?${queryString}` : ""}`;
  return apiClient<StoresCompetitivenessResponse>(endpoint, { signal });
}

export async function getPriceTrends(
  params: PriceTrendsParams = {},
  signal?: AbortSignal,
): Promise<PriceTrendsResponse> {
  const query = new URLSearchParams();

  if (params.period) {
    query.set("period", params.period);
  }
  if (params.from_date) {
    query.set("from_date", params.from_date);
  }
  if (params.to_date) {
    query.set("to_date", params.to_date);
  }
  if (params.category_id?.trim()) {
    query.set("category_id", params.category_id.trim());
  }
  if (params.store_id?.trim()) {
    query.set("store_id", params.store_id.trim());
  }

  const queryString = query.toString();
  const endpoint = `/analytics/price-trends${queryString ? `?${queryString}` : ""}`;
  return apiClient<PriceTrendsResponse>(endpoint, { signal });
}
