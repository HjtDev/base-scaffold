import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { server } from "./setup";
import { ApiClient, ApiError, getApiBaseUrl } from "../lib/api-client";

const BASE_URL = "http://test.local";

describe("ApiClient", () => {
  it("returns typed data on a successful JSON response", async () => {
    server.use(http.get(`${BASE_URL}/things/`, () => HttpResponse.json({ id: 1, name: "widget" })));
    const client = new ApiClient({ baseUrl: BASE_URL });

    const data = await client.get<{ id: number; name: string }>("/things/");

    expect(data).toEqual({ id: 1, name: "widget" });
  });

  it("surfaces code, message, details, and request_id from the backend envelope", async () => {
    server.use(
      http.post(`${BASE_URL}/things/`, () =>
        HttpResponse.json(
          {
            error: {
              code: "validation_error",
              message: "Validation failed.",
              details: { name: ["This field is required."] },
              request_id: "req-abc123",
            },
          },
          { status: 400 },
        ),
      ),
    );
    const client = new ApiClient({ baseUrl: BASE_URL });

    await expect(client.post("/things/", {})).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      code: "validation_error",
      message: "Validation failed.",
      details: { name: ["This field is required."] },
      requestId: "req-abc123",
    });
  });

  it("throws a sane ApiError instead of crashing on a non-JSON 500 body", async () => {
    server.use(
      http.get(
        `${BASE_URL}/broken/`,
        () =>
          new HttpResponse("<html><body>502 Bad Gateway</body></html>", {
            status: 502,
            headers: { "Content-Type": "text/html" },
          }),
      ),
    );
    const client = new ApiClient({ baseUrl: BASE_URL });

    const error = await client.get("/broken/").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(502);
    expect((error as ApiError).code).toBe("unknown_error");
  });

  it("does not attempt to parse a 204 response", async () => {
    server.use(http.delete(`${BASE_URL}/things/1/`, () => new HttpResponse(null, { status: 204 })));
    const client = new ApiClient({ baseUrl: BASE_URL });

    const result = await client.delete("/things/1/");

    expect(result).toBeUndefined();
  });

  it("defaults credentials to same-origin and allows overrides", async () => {
    const seen: RequestCredentials[] = [];
    server.use(
      http.get(`${BASE_URL}/creds/`, ({ request }) => {
        seen.push(request.credentials);
        return HttpResponse.json({ ok: true });
      }),
    );
    const defaultClient = new ApiClient({ baseUrl: BASE_URL });
    const includeClient = new ApiClient({ baseUrl: BASE_URL, credentials: "include" });

    await defaultClient.get("/creds/");
    await includeClient.get("/creds/");
    await defaultClient.get("/creds/", { credentials: "omit" });

    expect(seen).toEqual(["same-origin", "include", "omit"]);
  });

  describe("when NEXT_PUBLIC_API_URL is unset", () => {
    const original = process.env.NEXT_PUBLIC_API_URL;

    beforeEach(() => {
      delete process.env.NEXT_PUBLIC_API_URL;
    });

    afterEach(() => {
      process.env.NEXT_PUBLIC_API_URL = original;
    });

    it("throws, naming the variable, instead of falling back to a default", async () => {
      const client = new ApiClient();
      expect(() => getApiBaseUrl()).toThrow(/NEXT_PUBLIC_API_URL/);
      await expect(client.get("/anything/")).rejects.toThrow(/NEXT_PUBLIC_API_URL/);
    });
  });
});
