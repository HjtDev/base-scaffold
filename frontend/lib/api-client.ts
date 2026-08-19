/**
 * The shared fetcher every host page (and, per BASE-DESIGN.md §3/§8.1, every installed
 * app SDK's own low-level client) plugs into: base URL resolution, credentials handling,
 * and one consistent error shape.
 *
 * The base URL is read from `NEXT_PUBLIC_API_URL` lazily, inside `request()`, never at
 * module load — `NEXT_PUBLIC_*` is inlined at build time (BASE-DESIGN.md §8.1), but this
 * module itself must still import cleanly with the variable unset (a fresh clone's
 * `npm run build` has no `.env.local` yet). There is deliberately no fallback value: a
 * silent default to a dev backend URL is exactly the kind of thing that ships to prod by
 * accident. `frontend/.env.example` is the only file allowed to hardcode that URL.
 */

const REQUEST_ID_HEADER = "X-Request-ID";
const CSRF_COOKIE_NAME = "csrftoken";
const CSRF_HEADER_NAME = "X-CSRFToken";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * Mirrors the DRF error envelope from `backend/tools/mixins.py`:
 * `{"error": {"code", "message", "details", "request_id"}}`. `code` is one of the nine
 * stable values that handler emits (`validation_error`, `parse_error`,
 * `not_authenticated`, `authentication_failed`, `permission_denied`, `not_found`,
 * `method_not_allowed`, `throttled`, `server_error`) — except `"unknown_error"`, which is
 * this client's own code for a response that isn't the envelope at all (an nginx error
 * page, a truncated body, a non-JSON 500), so a caller never has to guard against a
 * `JSON.parse` crash reaching them.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;
  readonly retryAfter: string | null;

  constructor(
    message: string,
    options: {
      status: number;
      code: string;
      details?: Record<string, unknown>;
      requestId?: string | null;
      retryAfter?: string | null;
    },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.details = options.details ?? {};
    this.requestId = options.requestId ?? null;
    this.retryAfter = options.retryAfter ?? null;
  }
}

interface EnvelopeError {
  code: string;
  message: string;
  details: Record<string, unknown>;
  request_id: string | null;
}

function isEnvelope(data: unknown): data is { error: EnvelopeError } {
  if (typeof data !== "object" || data === null || !("error" in data)) return false;
  const error = (data as { error?: unknown }).error;
  return typeof error === "object" && error !== null && "code" in error && "message" in error;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null; // server-side render, no cookies yet
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function resolveBaseUrl(override?: string): string {
  const baseUrl = override ?? process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) {
    throw new ApiError(
      "NEXT_PUBLIC_API_URL is not set. Copy frontend/.env.example to " +
        "frontend/.env.local and fill it in.",
      { status: 0, code: "unknown_error" },
    );
  }
  return baseUrl;
}

export interface ApiClientOptions {
  /** Overrides `NEXT_PUBLIC_API_URL`. Mainly for tests. */
  baseUrl?: string;
  /**
   * Default `RequestCredentials` for every call made through this instance, overridable
   * per call via `init.credentials`. Defaults to `"same-origin"`, matching the backend's
   * current CORS config (`CORS_ALLOW_CREDENTIALS` defaults to `False` — see
   * `backend/config/settings.py`). An installed auth app that relies on cross-origin
   * cookies constructs its own instance with `credentials: "include"` once, per
   * BASE-DESIGN.md §3 "Auth integration", instead of every call site overriding it.
   */
  credentials?: RequestCredentials;
}

export class ApiClient {
  private readonly baseUrl: string | undefined;
  private readonly defaultCredentials: RequestCredentials;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl;
    this.defaultCredentials = options.credentials ?? "same-origin";
  }

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const baseUrl = resolveBaseUrl(this.baseUrl);
    const method = (init.method ?? "GET").toUpperCase();
    const credentials = init.credentials ?? this.defaultCredentials;

    const headers = new Headers(init.headers);
    if (init.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    // CSRF_COOKIE_HTTPONLY is deliberately False in backend/config/settings.py so this
    // cookie stays JS-readable — it exists specifically for this handshake.
    if (UNSAFE_METHODS.has(method) && credentials !== "omit") {
      const csrfToken = readCookie(CSRF_COOKIE_NAME);
      if (csrfToken) headers.set(CSRF_HEADER_NAME, csrfToken);
    }

    const response = await fetch(`${baseUrl}${path}`, { ...init, method, credentials, headers });

    if (response.status === 204) {
      return undefined as T;
    }

    const requestId = response.headers.get(REQUEST_ID_HEADER);
    const retryAfter = response.headers.get("Retry-After");
    const contentType = response.headers.get("Content-Type") ?? "";

    if (!contentType.includes("application/json")) {
      const text = await response.text();
      if (!response.ok) {
        throw new ApiError(text || `${response.status} ${response.statusText}`, {
          status: response.status,
          code: "unknown_error",
          requestId,
          retryAfter,
        });
      }
      return text as unknown as T;
    }

    let data: unknown;
    try {
      data = await response.json();
    } catch {
      // A non-JSON body claiming to be JSON, or an empty body — never let JSON.parse's
      // SyntaxError escape to the caller.
      throw new ApiError(`${response.status} ${response.statusText}`, {
        status: response.status,
        code: "unknown_error",
        requestId,
        retryAfter,
      });
    }

    if (!response.ok) {
      if (isEnvelope(data)) {
        const { error } = data;
        throw new ApiError(error.message, {
          status: response.status,
          code: error.code,
          details: error.details ?? {},
          requestId: error.request_id ?? requestId,
          retryAfter,
        });
      }
      throw new ApiError(`${response.status} ${response.statusText}`, {
        status: response.status,
        code: "unknown_error",
        requestId,
        retryAfter,
      });
    }

    return data as T;
  }

  get<T>(path: string, init?: RequestInit): Promise<T> {
    return this.request<T>(path, { ...init, method: "GET" });
  }

  post<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...init,
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  put<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...init,
      method: "PUT",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  patch<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...init,
      method: "PATCH",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  delete<T>(path: string, init?: RequestInit): Promise<T> {
    return this.request<T>(path, { ...init, method: "DELETE" });
  }
}

/** The base URL every request resolves against, for a host that needs to hand it to an
 * installed SDK's own `configure()`-style setup. Resolved lazily by `ApiClient`; exported
 * here only as a convenience getter, not cached — reading it before `NEXT_PUBLIC_API_URL`
 * is set throws the same way `ApiClient.request()` does. */
export function getApiBaseUrl(): string {
  return resolveBaseUrl();
}

/** The default instance every host page uses. */
export const apiClient = new ApiClient();
