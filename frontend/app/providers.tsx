"use client";

import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";

import { makeQueryClient } from "@/lib/query-client";

/**
 * Mounts the one shared QueryClient every installed app-package SDK's hooks resolve to
 * (see lib/query-client.ts). `useState(makeQueryClient)` creates exactly one instance per
 * browser session — not a module-level singleton, which would leak across concurrent
 * server-rendered requests.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(makeQueryClient);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
