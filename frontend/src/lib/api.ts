/**
 * Shared API client for Elevare Workforce OS frontend.
 *
 * - Access token lives in localStorage (per the auth model agreed with the
 *   backend: refresh token in an httpOnly cookie, access token here).
 * - Every request sends credentials: "include" so the httpOnly refresh
 *   cookie travels with it.
 * - Error shape matches 05_API_DESIGN.md exactly:
 *     { code, status, message, details: [{ field, message }] }
 *
 * NEXT_PUBLIC_API_URL is intentionally blank until Emmanuel hosts the
 * backend (see .env.example). Calls will fail with a clear error until
 * it's set — that's expected, not a bug.
 */

const ACCESS_TOKEN_KEY = "elevare_access_token";

export interface ApiErrorDetail {
  field: string;
  message: string;
}

export interface ApiErrorBody {
  code: string;
  status: string;
  message: string;
  details: ApiErrorDetail[];
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: ApiErrorDetail[];

  constructor(httpStatus: number, body: ApiErrorBody) {
    super(body.message || "Request failed");
    this.name = "ApiError";
    this.code = body.code;
    this.status = httpStatus;
    this.details = body.details || [];
  }
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}

interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  skipAuth?: boolean;
}

/**
 * Wraps fetch() with:
 *  - base URL from NEXT_PUBLIC_API_URL
 *  - Bearer token attached automatically (unless skipAuth is set, e.g. for
 *    /auth/login and /auth/register themselves)
 *  - JSON body serialization
 *  - credentials: "include" so the refresh cookie travels
 *  - ApiError thrown on any non-2xx response, parsed from the documented
 *    error shape
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;

  if (!baseUrl) {
    throw new Error(
      "NEXT_PUBLIC_API_URL is not set yet. Waiting on the backend to be hosted — " +
        "fill this in .env.local once you have the real URL."
    );
  }

  const { body, skipAuth, headers, ...rest } = options;

  const finalHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(headers as Record<string, string> | undefined),
  };

  if (!skipAuth) {
    const token = getAccessToken();
    if (token) {
      finalHeaders["Authorization"] = "Bearer " + token;
    }
  }

  const response = await fetch(baseUrl + path, {
    ...rest,
    headers: finalHeaders,
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const errorBody: ApiErrorBody =
      data && typeof data === "object"
        ? data
        : { code: "UNKNOWN_ERROR", status: "error", message: "Request failed", details: [] };
    throw new ApiError(response.status, errorBody);
  }

  return data as T;
}