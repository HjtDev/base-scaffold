import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./api-client";

/**
 * The shared TanStack Query client. Every installed frontend app-package SDK declares
 * `@tanstack/react-query` as a peer dependency and calls `useQueryClient()` internally
 * (APP-DESIGN.md §12) — this is the one client every one of those hooks resolves to.
 * INTEGRATION-GUIDE.md §6 is explicit that this file is the *only* thing an installed
 * SDK is allowed to assume exists in `frontend/lib/`.
 *
 * `makeQueryClient()` is a factory, not a module-level singleton, and must stay one:
 * Next.js renders on the server, and a module-level `QueryClient` would be shared across
 * every concurrent request/user, leaking one visitor's cached data into another's
 * response. `app/providers.tsx` calls this exactly once per browser session, inside
 * `useState`, so each session gets its own instance while still being the single
 * instance every mounted SDK hook and every host page shares for that session.
 */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // Retrying a 4xx (bad request, not found, forbidden) is pure latency — the
          // response won't change on retry. Only retry what might be transient:
          // network failures and 5xx, and only a couple of times.
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
            return false;
          }
          return failureCount < 2;
        },
      },
    },
  });
}
