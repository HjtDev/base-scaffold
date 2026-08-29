/**
 * The shared fetcher every host page (and, per BASE-DESIGN.md §3/§8.1, every installed
 * app SDK's own low-level client) plugs into: base URL resolution, credentials handling,
 * and one consistent error shape. Satisfies appkit's `HttpClient` interface (see the
 * assertion at the bottom of this file) — appkit owns that interface and the shared
 * `ApiClientProvider`, this module owns actually constructing the client: reading
 * `NEXT_PUBLIC_API_URL`, handling CSRF, deciding the credentials mode. All host
 * configuration appkit's own README is explicit it never owns.
 *
 * The base URL is read from `NEXT_PUBLIC_API_URL` lazily, inside `request()`, never at
 * module load — `NEXT_PUBLIC_*` is inlined at build time (BASE-DESIGN.md §8.1), but this
 * module itself must still import cleanly with the variable unset (a fresh clone's
 * `npm run build` has no `.env.local` yet). There is deliberately no fallback value: a
 * silent default to a dev backend URL is exactly the kind of thing that ships to prod by
 * accident. `frontend/.env.example` is the only file allowed to hardcode that URL.
 */

import { apiErrorFromEnvelope, ApiError, type HttpClient } from "appkit";

const REQUEST_ID_HEADER = "X-Request-ID";
const CSRF_COOKIE_NAME = "csrftoken";
const CSRF_HEADER_NAME = "X-CSRFToken";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// Re-exported so host pages keep one import site (`@/lib/api-client`) for both the client
// and the error type it throws, rather than reaching into `appkit` directly for one and
// this module for the other.
export { ApiError };

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

export class ApiClient implements HttpClient {
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
        // appkit's apiErrorFromEnvelope never recognises a plain string as the envelope
        // (isApiErrorEnvelope requires an object), so this always falls to its generic
        // "Request failed with status ${status}." message — the raw body text is still
        // reachable via ApiError.body, just no longer the thrown .message. A documented
        // behaviour difference from this client's pre-appkit version, which used the raw
        // text as the message here.
        throw apiErrorFromEnvelope({ status: response.status, body: text, requestId, retryAfter });
      }
      return text as unknown as T;
    }

    let data: unknown;
    try {
      data = await response.json();
    } catch {
      // A non-JSON body claiming to be JSON, or an empty body — never let JSON.parse's
      // SyntaxError escape to the caller. No parsed body to hand off, so apiErrorFromEnvelope
      // falls straight to its generic fallback.
      throw apiErrorFromEnvelope({
        status: response.status,
        body: undefined,
        requestId,
        retryAfter,
      });
    }

    if (!response.ok) {
      throw apiErrorFromEnvelope({ status: response.status, body: data, requestId, retryAfter });
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

// Compile-time proof this client satisfies appkit's HttpClient interface — `implements
// HttpClient` on the class above already enforces this structurally, but a drift here
// (appkit changing the interface, or this client's methods diverging) fails `tsc`, not a
// runtime call three layers into some installed app's SDK.
const _satisfiesHttpClient: HttpClient = apiClient;
void _satisfiesHttpClient;
