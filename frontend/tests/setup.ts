import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { setupServer } from "msw/node";

// The reference MSW setup every installed app package's own test suite is meant to copy
// (APP-DESIGN.md §7.7): mock the HTTP layer, never a live backend, and fail loudly on any
// request nobody set up a handler for rather than silently letting it through.
export const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
