// Helpers for the Decision Planner view.
import type { DecisionPoint } from "../api/types";
import { utcDayMonth, utcTime } from "./format";

export function publishBanner(publishTimes: string[], cutoff: string): string {
  const describe = (iso: string) => `${utcTime(iso)} on ${utcDayMonth(iso)}`;
  if (publishTimes.length === 0) {
    return `No forecast had been published by your ${cutoff} cutoff`;
  }
  if (publishTimes.length === 1) {
    return `Forecast published at ${describe(publishTimes[0])} (available at your ${cutoff} cutoff)`;
  }
  const listed = publishTimes.map(describe);
  const text = `${listed.slice(0, -1).join(", ")} and ${listed[listed.length - 1]}`;
  return `Forecasts published at ${text} (the latest available for each hour at your ${cutoff} cutoff)`;
}

export interface DaySummary {
  peakHour: string | null;
  peakMw: number | null;
  averageMw: number | null;
  nAvailable: number;
}

export function daySummary(points: DecisionPoint[]): DaySummary {
  const available = points.filter((p) => p.forecast_mw !== null);
  if (available.length === 0) {
    return { peakHour: null, peakMw: null, averageMw: null, nAvailable: 0 };
  }
  const peak = available.reduce((a, b) => (b.forecast_mw! > a.forecast_mw! ? b : a));
  const total = available.reduce((sum, p) => sum + p.forecast_mw!, 0);
  return {
    peakHour: utcTime(peak.target_time),
    peakMw: peak.forecast_mw,
    averageMw: total / available.length,
    nAvailable: available.length,
  };
}

export interface BuyRow {
  hour: string;
  forecast: number | null;
  /** MW to buy from other sources if the forecast is right. */
  buy: number;
  /** MW to buy if wind falls short by the full buffer. */
  buyWithBuffer: number;
  missing: boolean;
}

export interface BuyPlan {
  rows: BuyRow[];
  /** Hourly MW summed over the day = MWh. */
  totalMwh: number;
  totalWithBufferMwh: number;
  peakWithBuffer: { hour: string; mw: number } | null;
}

/**
 * How much to buy from other sources each hour, given a flat demand (MW).
 * Without a forecast for an hour, no wind can be counted on.
 */
export function buyPlan(points: DecisionPoint[], demandMw: number, buffer: number | null): BuyPlan {
  const rows = points.map((p) => {
    const wind = p.forecast_mw ?? 0;
    const windWithBuffer = Math.max(0, wind - (buffer ?? 0));
    return {
      hour: utcTime(p.target_time),
      forecast: p.forecast_mw,
      buy: Math.max(0, demandMw - wind),
      buyWithBuffer: Math.max(0, demandMw - windWithBuffer),
      missing: p.missing,
    };
  });
  const peak = rows.reduce<BuyRow | null>((a, b) => (a === null || b.buyWithBuffer > a.buyWithBuffer ? b : a), null);
  return {
    rows,
    totalMwh: rows.reduce((sum, r) => sum + r.buy, 0),
    totalWithBufferMwh: rows.reduce((sum, r) => sum + r.buyWithBuffer, 0),
    peakWithBuffer: peak ? { hour: peak.hour, mw: peak.buyWithBuffer } : null,
  };
}

export interface ChartRow {
  hour: string;
  forecast: number | null;
  actual: number | null;
  /** [forecast - buffer, forecast]: where wind may land in 9 of 10 hours. */
  band: [number, number] | null;
  missing: boolean;
}

export function chartRows(points: DecisionPoint[], buffer: number | null): ChartRow[] {
  return points.map((p) => ({
    hour: utcTime(p.target_time),
    forecast: p.forecast_mw,
    actual: p.actual_mw,
    band:
      p.forecast_mw === null || buffer === null
        ? null
        : [Math.max(0, p.forecast_mw - buffer), p.forecast_mw],
    missing: p.missing,
  }));
}
