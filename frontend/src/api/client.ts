import { ApiErrorResponse } from "../types/api";

const envApiUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "");
const BASE_URL = envApiUrl ?? (import.meta.env.DEV ? "http://localhost:8000/api/v1" : "/api/v1");

export class ApiError extends Error {
  statusCode: number;
  code?: string;
  requestId?: string;

  constructor(message: string, statusCode: number, code?: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.code = code;
    this.requestId = requestId;
  }
}

export async function apiClient<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;

  const defaultHeaders: HeadersInit = {
    Accept: "application/json",
  };

  const response = await fetch(url, {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let errorMessage = `Error HTTP ${response.status}: ${response.statusText}`;
    let errorCode: string | undefined;
    let requestId: string | undefined;

    try {
      const errorJson = (await response.json()) as ApiErrorResponse;
      if (errorJson?.error?.message) {
        errorMessage = errorJson.error.message;
        errorCode = errorJson.error.code;
        requestId = errorJson.error.request_id;
      }
    } catch {
      // Ignorar fallo de parseo JSON en respuesta con error
    }

    throw new ApiError(errorMessage, response.status, errorCode, requestId);
  }

  return response.json() as Promise<T>;
}
