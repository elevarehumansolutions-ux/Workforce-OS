const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

/**
 * Wraps the backend's ErrorResponse envelope ({code, status, message, details})
 * so callers get typed-ish access via instanceof, not just a generic string.
 */
export class ApiError extends Error {
  constructor(response) {
    super(response.message);
    this.code = response.code;
    this.details = response.details;
  }
}

async function request(path, options = {}) {
  const accessToken = localStorage.getItem("access_token");

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    // Required for the httpOnly refresh cookie to be sent cross-origin —
    // the server-side half of this is CORSMiddleware's allow_credentials=True.
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const errorBody = await response.json();
    throw new ApiError(errorBody);
  }

  if (response.status === 204) {
    return undefined;
  }

  return response.json();
}

export const apiClient = {
  get: (path) => request(path, { method: "GET" }),
  post: (path, body) =>
    request(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: (path, body) =>
    request(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: (path) => request(path, { method: "DELETE" }),
};
