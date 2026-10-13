/**
 * Test harness: render the REAL application against a fake network.
 *
 * In plain words: ``mockApi`` replaces ``fetch`` with a table of "METHOD /path" -> response, so
 * tests exercise the real components, hooks and API client - only the server is pretend. Calls
 * are recorded so tests can check exactly what the interface sent.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "@/App";
import { ToastProvider } from "@/components/ui/Toast";
import { accessKey } from "@/services/http";
import type { Role } from "@/types/api";
import { config, demoInfo, galleryPage, overview, readiness, videoLimits } from "./fixtures";

export type Handler = (request: { url: URL; init: RequestInit; body: unknown }) => unknown | Response | Promise<unknown | Response>;
export interface Call { method: string; path: string; search: string; body: unknown }

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
export const apiError = (status: number, code: string, message: string) => json({ error: { code, message, request_id: "testreq", details: {} } }, status);

/**
 * ``authRequired`` mirrors the server setting REID_AUTH_REQUIRED. The shipped default is OFF; most tests turn it
 * ON because they check what each role may do. When it is on the pretend server answers 401 to a request that
 * carries no key, exactly like the real one.
 */
export function mockApi(handlers: Record<string, Handler> = {}, role: Role = "admin", { authRequired = true } = {}) {
  const calls: Call[] = [];
  const table: Record<string, Handler> = {
    "GET /api/auth/me": ({ init }) => {
      if (!authRequired) return { role: "admin", auth_required: false };
      const sentKey = new Headers(init.headers).get("X-API-Key");
      return sentKey ? { role, auth_required: true } : apiError(401, "unauthorized", "An access key is required. Send it in the X-API-Key header.");
    },
    "GET /api/readiness": () => readiness,
    "GET /api/config": () => config(),
    "GET /api/overview": () => overview(),
    "GET /api/gallery": () => galleryPage(),
    "GET /api/evaluation/datasets": () => [],
    "GET /api/evaluation/checkpoints": () => [],
    "GET /api/evaluation/runs": () => ({ items: [], total: 0 }),
    "GET /api/lookalike/runs": () => ({ items: [], total: 0 }),
    "GET /api/video/limits": () => videoLimits(),
    "GET /api/video/jobs": () => ({ items: [], total: 0 }),
    "GET /api/demo": () => demoInfo(),
    ...handlers,
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init.method ?? "GET").toUpperCase();
    const body = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
    calls.push({ method, path: url.pathname, search: url.search, body });
    const handler = table[`${method} ${url.pathname}`];
    if (!handler) return apiError(404, "not_found", `No mock for ${method} ${url.pathname}`);
    const result = await handler({ url, init, body });
    return result instanceof Response ? result : json(result);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock, called: (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path) };
}

export function renderApp(route = "/", options: { signedIn?: boolean } = {}) {
  if (options.signedIn !== false) accessKey.set("test-key");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[route]}>
          <App />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

/** A small valid PNG-named file for upload tests. */
export const imageFile = (name = "person.png", size = 2048, type = "image/png") => new File([new Uint8Array(size)], name, { type });
