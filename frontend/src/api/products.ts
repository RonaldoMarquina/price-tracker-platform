import {
  PriceHistoryParams,
  ProductDetailOut,
  ProductFilterParams,
  ProductListResponse,
  ProductPriceHistoryResponse,
} from "../types/api";
import { apiClient } from "./client";

export async function getProducts(params: ProductFilterParams = {}): Promise<ProductListResponse> {
  const query = new URLSearchParams();

  if (params.q?.trim()) {
    query.set("q", params.q.trim());
  }
  if (params.category?.trim()) {
    query.set("category", params.category.trim());
  }
  if (params.page && params.page > 0) {
    query.set("page", params.page.toString());
  }
  if (params.page_size && params.page_size > 0) {
    query.set("page_size", params.page_size.toString());
  }

  const queryString = query.toString();
  const endpoint = `/products${queryString ? `?${queryString}` : ""}`;
  return apiClient<ProductListResponse>(endpoint);
}

export async function getProductById(productId: string): Promise<ProductDetailOut> {
  return apiClient<ProductDetailOut>(`/products/${productId}`);
}

export async function getPriceHistory(
  productId: string,
  params: PriceHistoryParams = {},
): Promise<ProductPriceHistoryResponse> {
  const query = new URLSearchParams();

  if (params.store_id) {
    query.set("store_id", params.store_id);
  }
  if (params.from) {
    query.set("from", params.from);
  }
  if (params.to) {
    query.set("to", params.to);
  }

  const queryString = query.toString();
  const endpoint = `/products/${productId}/price-history${queryString ? `?${queryString}` : ""}`;
  return apiClient<ProductPriceHistoryResponse>(endpoint);
}
