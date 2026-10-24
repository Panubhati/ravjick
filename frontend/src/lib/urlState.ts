// The user's selections live in the URL query string, so any view can be
// shared or bookmarked. Invalid values fall back to defaults, one at a time.
import type { Meta } from "../api/types";

export const TABS = [
  { id: "planner", label: "Decision Planner" },
  { id: "performance", label: "Forecast Performance" },
  { id: "insights", label: "Error Insights" },
] as const;
export type TabId = (typeof TABS)[number]["id"];

export interface ViewState {
  tab: TabId;
  date: string;
  cutoff: string;
  from: string;
  to: string;
}

const DEFAULT_DATE = "2026-01-15";

export function defaultState(meta: Meta): ViewState {
  return {
    tab: "planner",
    date: DEFAULT_DATE,
    cutoff: meta.default_cutoff,
    from: meta.min_date,
    to: meta.max_date,
  };
}

function isValidDate(value: string | null, meta: Meta): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const d = new Date(`${value}T00:00:00Z`);
  // Reject impossible dates such as 2026-01-32, which Date would roll over.
  if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== value) return false;
  return value >= meta.min_date && value <= meta.max_date;
}

export function parseState(search: string, meta: Meta): ViewState {
  const q = new URLSearchParams(search);
  const state = defaultState(meta);
  const tab = q.get("tab");
  if (TABS.some((t) => t.id === tab)) state.tab = tab as TabId;
  const date = q.get("date");
  if (isValidDate(date, meta)) state.date = date;
  const cutoff = q.get("cutoff");
  if (cutoff && meta.cutoff_options.includes(cutoff)) state.cutoff = cutoff;
  const from = q.get("from");
  const to = q.get("to");
  if (isValidDate(from, meta) && isValidDate(to, meta) && from <= to) {
    state.from = from;
    state.to = to;
  }
  return state;
}

export function toSearch(state: ViewState): string {
  const q = new URLSearchParams({
    tab: state.tab,
    date: state.date,
    cutoff: state.cutoff,
    from: state.from,
    to: state.to,
  });
  return `?${q.toString()}`;
}
