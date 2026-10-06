const ACCESS_TOKEN_KEY = "elevare_access_token";

export interface FastApiValidationItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface ApiErrorBody {
  detail?: string | FastApiValidationItem[];
}

export class ApiError extends Error {
  status: number;
  fieldErrors: Record<string, string>;

  constructor(status: number, body: ApiErrorBody) {
    let message = "Request failed";
    const fieldErrors: Record<string, string> = {};

    if (body && typeof body === "object" && body.detail) {
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        const msgs: string[] = [];
        body.detail.forEach(function (item) {
          msgs.push(item.msg);
          const field = item.loc && item.loc.length > 0 ? String(item.loc[item.loc.length - 1]) : "form";
          fieldErrors[field] = item.msg;
        });
        if (msgs.length > 0) {
          message = msgs.join(" ");
        }
      }
    }

    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
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
  /** Internal — set when retrying once after a token refresh. Do not pass this in yourself. */
  _isRetry?: boolean;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

// Access tokens are short-lived (15 minutes — see backend/app/core/config.py).
// The refresh token itself lives in an httpOnly cookie set by /auth/login, so
// it's never touched directly here; the browser sends it automatically
// because every fetch below already uses credentials: "include". When a
// request comes back 401, we try POST /auth/refresh once to mint a fresh
// access token and replay the original call, instead of surfacing a bare
// "Request failed" the moment 15 minutes have passed on any screen.
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = doFetch<TokenResponse>("/auth/refresh", { method: "POST", skipAuth: true })
      .then(function (data) {
        setAccessToken(data.access_token);
        return data.access_token;
      })
      .finally(function () {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

async function doFetch<T>(path: string, options: ApiFetchOptions): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;

  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not set. Add it to .env.local.");
  }

  // _isRetry rides along in ...rest below and is simply ignored by fetch()
  // (it isn't a real RequestInit field) — it only exists so apiFetch can
  // tell this call apart from a first attempt, see below.
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
    const errorBody: ApiErrorBody = data && typeof data === "object" ? data : {};
    throw new ApiError(response.status, errorBody);
  }

  return data as T;
}

export async function apiFetch<T = unknown>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  try {
    return await doFetch<T>(path, options);
  } catch (err) {
    const canRetryWithRefresh =
      err instanceof ApiError &&
      err.status === 401 &&
      !options.skipAuth &&
      !options._isRetry &&
      path !== "/auth/refresh" &&
      path !== "/auth/login";

    if (!canRetryWithRefresh) {
      throw err;
    }

    try {
      await refreshAccessToken();
    } catch {
      // The refresh token is gone or expired too — there's no session left
      // to recover. Clear the stale access token and send the person back
      // to log in rather than leaving every screen stuck on "Request failed".
      clearAccessToken();
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
      throw err;
    }

    return doFetch<T>(path, { ...options, _isRetry: true });
  }
}

