// Typed API client. VITE_API_BASE_URL is empty when the same server hosts
// the front end and the API (Docker / production).
import type {
  CutoffSensitivity,
  DecisionForecast,
  ErrorByHorizon,
  Meta,
  Metrics,
  Series,
} from "./types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {}

// The data never changes, so each successful response is kept for the life of
// the page. Failed requests are forgotten so that Retry asks the server again.
const cache = new Map<string, Promise<unknown>>();

function get<T>(path: string, params: Record<string, string> = {}): Promise<T> {
  const query = new URLSearchParams(params).toString();
  const url = `${BASE_URL}/api${path}${query ? `?${query}` : ""}`;
  if (!cache.has(url)) {
    cache.set(
      url,
      request<T>(url).catch((e) => {
        cache.delete(url);
        throw e;
      }),
    );
  }
  return cache.get(url) as Promise<T>;
}

async function request<T>(url: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new ApiError("Could not reach the server. Check your connection and retry.");
  }
  if (!response.ok) {
    let detail = `Request failed (HTTP ${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      // Body was not JSON; keep the generic message.
    }
    throw new ApiError(detail);
  }
  return response.json() as Promise<T>;
}

export interface Range {
  from: string;
  to: string;
}

export const api = {
  meta: () => get<Meta>("/meta"),
  decisionForecast: (deliveryDate: string, cutoff: string) =>
    get<DecisionForecast>("/decision-forecast", { delivery_date: deliveryDate, cutoff }),
  series: (range: Range, cutoff: string) =>
    get<Series>("/series", { from: range.from, to: range.to, cutoff }),
  metrics: (range: Range, cutoff: string) =>
    get<Metrics>("/metrics", { from: range.from, to: range.to, cutoff }),
  errorByHorizon: (range: Range) =>
    get<ErrorByHorizon>("/error-by-horizon", { from: range.from, to: range.to }),
  cutoffSensitivity: (range: Range) =>
    get<CutoffSensitivity>("/cutoff-sensitivity", { from: range.from, to: range.to }),
};
