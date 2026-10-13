/**
 * The one place that talks to the network.
 *
 * In plain words: every request to the backend goes through ``request()``. It adds the
 * access key, turns the backend's structured error JSON into a typed ``ApiError`` that
 * screens can show to people, and never throws away the request ID (which is what you
 * quote when reporting a problem).
 */
import { useSyncExternalStore } from "react";

// ------------------------------------------------------------------ access key store
const STORAGE_KEY = "reid-api-key";
const listeners = new Set<() => void>();

function readStored(): string | null {
  // Storage can throw (private windows, blocked cookies): the app must still work without it.
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

let currentKey: string | null = readStored();

export const accessKey = {
  get: () => currentKey,
  /** remember=true keeps the key on this device; otherwise it lives only until the tab closes. */
  set(key: string, remember = false) {
    currentKey = key.trim() || null;
    try {
      sessionStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(STORAGE_KEY);
      if (currentKey) (remember ? localStorage : sessionStorage).setItem(STORAGE_KEY, currentKey);
    } catch {
      /* in-memory only */
    }
    listeners.forEach((l) => l());
  },
  clear() {
    this.set("");
  },
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

export function useAccessKey(): string | null {
  return useSyncExternalStore(accessKey.subscribe, accessKey.get, () => null);
}

// ----------------------------------------------------------------------------- errors
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly requestId?: string,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    const error = body?.error;
    if (error) return new ApiError(error.message, response.status, error.code, error.request_id, error.details ?? {});
  } catch {
    /* not JSON */
  }
  return new ApiError(`The server answered ${response.status} ${response.statusText}.`, response.status, "http_error");
}

// ------------------------------------------------------------------------------ calls
export interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  query?: Record<string, string | number | boolean | undefined | null>;
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
  /** Return the parsed body even for non-2xx answers with this status (e.g. readiness 503). */
  acceptStatus?: number[];
  /** Give up waiting after this long (default 2 minutes: a CPU query takes seconds, never minutes). */
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 120_000;

function withTimeout(signal: AbortSignal | undefined, ms: number): AbortSignal {
  const timeout = AbortSignal.timeout(ms);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

function networkError(error: unknown, timeoutMs: number): ApiError {
  if ((error as Error)?.name === "TimeoutError") {
    return new ApiError(`The server did not answer within ${Math.round(timeoutMs / 1000)} seconds.`, 0, "timeout");
  }
  return new ApiError("Cannot reach the backend. Is it running? (Start it with the commands in the README.)", 0, "network_error");
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(BASE + path, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  return BASE ? url.toString() : url.pathname + url.search;
}

function headers(options: RequestOptions): Headers {
  const h = new Headers();
  if (accessKey.get()) h.set("X-API-Key", accessKey.get() as string);
  if (options.json !== undefined) h.set("Content-Type", "application/json");
  return h; // for FormData the browser sets the multipart boundary itself
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers: headers(options),
      body: options.form ?? (options.json !== undefined ? JSON.stringify(options.json) : undefined),
      signal: withTimeout(options.signal, timeoutMs),
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error; // cancelled on purpose by the caller
    throw networkError(error, timeoutMs);
  }
  if (!response.ok && !options.acceptStatus?.includes(response.status)) throw await toApiError(response);
  if (response.status === 204) return undefined as T; // "No Content": success with nothing to parse (e.g. a delete)
  return (await response.json()) as T;
}

/** Fetch binary content (images, reports) WITH the access key, which a plain <img src> cannot send. */
export async function requestBlob(path: string, query?: RequestOptions["query"]): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), { headers: headers({}), signal: AbortSignal.timeout(60_000) });
  } catch (error) {
    throw networkError(error, 60_000);
  }
  if (!response.ok) throw await toApiError(response);
  return response.blob();
}

/** Save a Blob as a file download in the browser. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.requestId ? `${error.message} (request ${error.requestId})` : error.message;
  return error instanceof Error ? error.message : "Something went wrong.";
}
