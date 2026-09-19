/**
 * TypeScript interfaces reflecting OpenAPI schemas from FastAPI backend.
 * Sourced strictly from /openapi.json & docs/API_SPEC.md.
 */

export interface LatestPriceOut {
  amount: string;
  currency: string;
  store: string;
}

export interface ProductListItemOut {
  id: string;
  name: string;
  brand: string | null;
  category: string;
  image_url: string | null;
  latest_price: LatestPriceOut | null;
}

export interface ProductListResponse {
  items: ProductListItemOut[];
  page: number;
  page_size: number;
  total: number;
}

export interface CategoryOut {
  id: string;
  name: string;
  slug: string;
}

export interface StoreProductPriceOut {
  amount: string;
  currency: string;
  availability: string | null;
  captured_at: string;
}

export interface ProductStoreOut {
  store_id: string;
  store_name: string;
  product_url: string;
  external_sku: string | null;
  latest_price: StoreProductPriceOut | null;
}

export interface ProductDetailOut {
  id: string;
  name: string;
  slug: string;
  brand: string | null;
  model: string | null;
  category: CategoryOut;
  image_url: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  stores: ProductStoreOut[];
}

export interface PricePointOut {
  captured_at: string;
  price: string;
}

export interface StorePriceSeriesOut {
  store_id: string;
  store_name: string;
  currency: string;
  points: PricePointOut[];
}

export interface ProductPriceHistoryResponse {
  product_id: string;
  series: StorePriceSeriesOut[];
}

export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    request_id?: string;
    details?: unknown;
  };
}

export interface ProductFilterParams {
  q?: string;
  category?: string;
  page?: number;
  page_size?: number;
}

export interface PriceHistoryParams {
  store_id?: string;
  from?: string; // YYYY-MM-DD
  to?: string;   // YYYY-MM-DD
}

export const CATEGORY_ALIASES: Record<string, string> = {
  processors: "procesadores",
  cpu: "procesadores",
  "graphics-cards": "tarjetas-de-video",
  gpu: "tarjetas-de-video",
  "ram-memory": "memorias-ram",
  ram: "memorias-ram",
  motherboards: "placas-madre",
  motherboard: "placas-madre",
  "placa-madre": "placas-madre",
  "power-supplies": "fuentes-de-poder",
  psu: "fuentes-de-poder",
  cooling: "refrigeracion",
  coolers: "refrigeracion",
  "refrigeracion-liquida": "refrigeracion",
  "refrigeracion-aire": "refrigeracion",
};

