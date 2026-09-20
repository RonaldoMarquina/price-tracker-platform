/**
 * TypeScript interfaces reflecting analytical OpenAPI contracts.
 * Matches backend schemas from app/schemas/analytics.py.
 */

export type PeriodPreset = "7d" | "30d" | "90d" | "all";

export interface CategoryFilterItem {
  id: string;
  name: string;
}

export interface StoreFilterItem {
  id: string;
  name: string;
  is_active: boolean;
}

export interface AnalyticsFiltersResponse {
  categories: CategoryFilterItem[];
  stores: StoreFilterItem[];
  periods: PeriodPreset[];
}

export interface OfferSnapshotOut {
  amount: string;
  currency: string;
  store_id: string;
  store_name: string;
  price_condition: "standard" | "cash_or_bank_transfer" | null;
  captured_at: string;
}

export interface MaxSavingsProductOut {
  product_id: string;
  product_name: string;
  best_price: string;
  best_store: string;
  best_price_condition: "standard" | "cash_or_bank_transfer" | null;
  worst_price: string;
  worst_store: string;
  worst_price_condition: "standard" | "cash_or_bank_transfer" | null;
  savings_amount: string;
  savings_percentage: string;
}

export interface SavingsSummaryOut {
  average_savings_amount: string;
  average_savings_percentage: string;
  max_savings_product: MaxSavingsProductOut | null;
}

export interface MostCompetitiveStoreOut {
  store_id: string;
  store_name: string;
  best_price_count: number;
  best_price_share_percentage: string;
}

export interface DataFreshnessOut {
  total_active_associations: number;
  fresh_count: number;
  stale_count: number;
  unknown_count: number;
  no_observation_count: number;
  freshness_rate: string;
}

export interface AnalyticsSummaryResponse {
  as_of: string;
  category_id: string | null;
  total_products_tracked: number;
  products_with_valid_offer_count: number;
  comparable_products_count: number;
  savings: SavingsSummaryOut;
  most_competitive_store: MostCompetitiveStoreOut | null;
  freshness: DataFreshnessOut;
}

export interface PriceSpreadItemOut {
  product_id: string;
  product_name: string;
  category_name: string;
  best_offer: OfferSnapshotOut;
  worst_offer: OfferSnapshotOut;
  savings_amount: string;
  savings_percentage: string;
  valid_offers_count: number;
}

export interface PriceSpreadResponse {
  as_of: string;
  category_id: string | null;
  total_comparable_products: number;
  limit: number;
  items: PriceSpreadItemOut[];
}

export interface StoreCompetitivenessItemOut {
  store_id: string;
  store_name: string;
  is_active: boolean;
  total_associations: number;
  observed_associations: number;
  no_observation_count: number;
  best_price_count: number;
  best_price_share_percentage: string;
  in_stock_count: number;
  in_stock_percentage: string;
  out_of_stock_count: number;
  out_of_stock_percentage: string;
  unknown_count: number;
  unknown_percentage: string;
  price_conditions: Record<string, number>;
}

export interface StoresCompetitivenessResponse {
  as_of: string;
  category_id: string | null;
  products_with_valid_offer_count: number;
  stores: StoreCompetitivenessItemOut[];
}

export interface DailyTrendPointOut {
  date: string; // YYYY-MM-DD
  average_price: string;
  median_price: string;
  min_price: string;
  max_price: string;
  associations_count: number;
  products_count: number;
}

export interface PriceTrendsResponse {
  as_of: string;
  period: PeriodPreset | null;
  from_date: string | null;
  to_date: string | null;
  category_id: string | null;
  store_id: string | null;
  points: DailyTrendPointOut[];
}

export interface PriceTrendsParams {
  period?: PeriodPreset;
  from_date?: string; // ISO UTC
  to_date?: string;   // ISO UTC
  category_id?: string;
  store_id?: string;
}
