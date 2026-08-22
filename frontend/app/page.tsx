"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient, ApiError } from "@/lib/api-client";

interface HealthCheck {
  ok: boolean;
  detail: string;
}

interface HealthzResponse {
  status: "ok" | "unavailable";
  checks: {
    database: HealthCheck;
    cache: HealthCheck;
  };
}

/**
 * Minimal placeholder proving the two halves of the scaffold are actually wired
 * together: calls the backend's real /healthz/ (backend/config/views.py) through the
 * shared apiClient, under the shared QueryClient mounted in app/providers.tsx. If either
 * were missing, this would fail loudly instead of silently.
 */
export default function Home() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["healthz"],
    queryFn: () => apiClient.get<HealthzResponse>("/healthz/"),
  });

  return (
    <main style={{ fontFamily: "monospace", padding: "2rem" }}>
      <h1>Backend connectivity check</h1>
      <p>Backend status, fetched live from /healthz/:</p>
      {isLoading && <p>Checking backend…</p>}
      {isError && (
        <p style={{ color: "crimson" }}>
          Backend unreachable: {error instanceof ApiError ? error.message : String(error)}
        </p>
      )}
      {data && (
        <ul>
          <li>overall: {data.status}</li>
          <li>
            database: {data.checks.database.ok ? "ok" : "down"} — {data.checks.database.detail}
          </li>
          <li>
            cache: {data.checks.cache.ok ? "ok" : "down"} — {data.checks.cache.detail}
          </li>
        </ul>
      )}
    </main>
  );
}
