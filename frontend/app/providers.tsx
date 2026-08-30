"use client";

import { useState } from "react";
import { ApiClientProvider, makeQueryClient } from "@hjtdev/appkit";
import { QueryClientProvider } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";

/**
 * Mounts the one shared QueryClient every installed app-package SDK's hooks resolve to,
 * and appkit's shared `ApiClientProvider` — nested under it, mounted once for the whole
 * host regardless of how many apps are installed (`INTEGRATION-GUIDE.md` §2 step 11).
 * Installing an app adds a `basePaths` entry to this same provider; it never nests a
 * second one.
 *
 * `useState(makeQueryClient)` creates exactly one `QueryClient` instance per browser
 * session — not a module-level singleton, which would leak across concurrent
 * server-rendered requests.
 *
 * No `headerSources` yet — the scaffold has no auth, and appkit never reads/stores/
 * refreshes a token itself (see appkit's README, "Header injection"). When the first
 * auth app is installed, pass its header-attaching callback here as a **stable** reference
 * (`useMemo`/module scope) — an inline array literal defeats the memoisation
 * `ApiClientProvider` relies on and rebuilds every installed app's own manager on every
 * render.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(makeQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <ApiClientProvider client={apiClient} basePaths={{}}>
        {children}
      </ApiClientProvider>
    </QueryClientProvider>
  );
}
