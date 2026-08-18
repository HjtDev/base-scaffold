import { describe, expect, it } from "vitest";

import { makeQueryClient } from "../lib/query-client";

describe("makeQueryClient", () => {
  it("returns a fresh QueryClient on every call, not a module-level singleton", () => {
    // The SSR cache-leak bug: a module-level QueryClient would be shared across every
    // concurrent server-rendered request/user. app/providers.tsx relies on this factory
    // producing a distinct instance per call so each browser session gets its own.
    const first = makeQueryClient();
    const second = makeQueryClient();

    expect(first).not.toBe(second);
  });
});
