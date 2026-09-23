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
}

export async function apiFetch<T = unknown>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;

  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not set. Add it to .env.local.");
  }

  const body = options.body;
  const skipAuth = options.skipAuth;
  const headers = options.headers;
  const rest: RequestInit = {};
  for (const key in options) {
    if (key !== "body" && key !== "skipAuth" && key !== "headers") {
      (rest as any)[key] = (options as any)[key];
    }
  }

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
