import { afterEach, describe, expect, it, vi } from "vitest";
import { accessKey, ApiError, describeError, request } from "./http";

afterEach(() => accessKey.clear());

describe("request()", () => {
  it("sends the access key in the X-API-Key header, never in the URL", async () => {
    accessKey.set("secret-key");
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await request("/api/gallery", { query: { search: "alpha" } });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/gallery?search=alpha");
    expect(url).not.toContain("secret-key");
    expect((init.headers as Headers).get("X-API-Key")).toBe("secret-key");
  });

  it("turns the backend's structured error into an ApiError that keeps the request ID", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ error: { code: "not_found", message: "No such identity.", request_id: "abc123", details: {} } }), { status: 404 }));
    const failure = (await request("/api/gallery/x").catch((e) => e)) as ApiError;
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ status: 404, code: "not_found", requestId: "abc123" });
    expect(describeError(failure)).toBe("No such identity. (request abc123)");
  });

  it("explains a network failure in plain words", async () => {
    vi.stubGlobal("fetch", async () => { throw new TypeError("Failed to fetch"); });
    const failure = (await request("/api/health").catch((e) => e)) as ApiError;
    expect(failure).toMatchObject({ code: "network_error" });
    expect(failure.message).toMatch(/Is it running/);
  });

  it("gives up with a clear message instead of waiting forever when the server hangs", async () => {
    vi.stubGlobal("fetch", (_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(init.signal?.reason));
    }));
    const failure = (await request("/api/reid/predict", { timeoutMs: 40 }).catch((e) => e)) as ApiError;
    expect(failure).toMatchObject({ code: "timeout" });
    expect(failure.message).toMatch(/did not answer within/);
  });

  it("does not choke on a non-JSON error page", async () => {
    vi.stubGlobal("fetch", async () => new Response("<html>Bad gateway</html>", { status: 502, statusText: "Bad Gateway" }));
    const failure = await request("/api/health").catch((e) => e);
    expect(failure).toMatchObject({ status: 502, code: "http_error" });
  });
});

describe("access key storage", () => {
  it("keeps a key for the tab by default and on the device only when asked", () => {
    accessKey.set("tab-key");
    expect(sessionStorage.getItem("reid-api-key")).toBe("tab-key");
    expect(localStorage.getItem("reid-api-key")).toBeNull();
    accessKey.set("device-key", true);
    expect(localStorage.getItem("reid-api-key")).toBe("device-key");
    expect(sessionStorage.getItem("reid-api-key")).toBeNull();
    accessKey.clear();
    expect(accessKey.get()).toBeNull();
    expect(localStorage.getItem("reid-api-key")).toBeNull();
  });
});
