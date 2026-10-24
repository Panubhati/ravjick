import { describe, expect, it } from "vitest";
import type { Meta } from "../api/types";
import { defaultState, parseState, toSearch } from "./urlState";

const META: Meta = {
  min_date: "2026-01-01",
  max_date: "2026-01-31",
  default_cutoff: "09:00",
  cutoff_options: ["06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "12:00"],
  timezone: "UTC",
  data_notes: [],
};
const DEFAULTS = defaultState(META);

describe("urlState", () => {
  it("uses defaults for an empty query string", () => {
    expect(parseState("", META)).toEqual(DEFAULTS);
    expect(DEFAULTS).toEqual({
      tab: "planner",
      date: "2026-01-15",
      cutoff: "09:00",
      from: "2026-01-01",
      to: "2026-01-31",
    });
  });

  it("reads valid values", () => {
    expect(parseState("?tab=insights&date=2026-01-03&cutoff=10:00&from=2026-01-05&to=2026-01-12", META)).toEqual({
      tab: "insights",
      date: "2026-01-03",
      cutoff: "10:00",
      from: "2026-01-05",
      to: "2026-01-12",
    });
  });

  it("falls back to defaults for invalid values, one field at a time", () => {
    const s = parseState("?tab=admin&date=2026-02-01&cutoff=13:00&from=2026-01-20&to=2026-01-10", META);
    expect(s).toEqual(DEFAULTS);
    expect(parseState("?date=not-a-date", META).date).toBe(DEFAULTS.date);
    expect(parseState("?date=2026-01-32", META).date).toBe(DEFAULTS.date);
  });

  it("round-trips through the query string", () => {
    const state = { tab: "performance" as const, date: "2026-01-20", cutoff: "12:00", from: "2026-01-02", to: "2026-01-09" };
    expect(parseState(toSearch(state), META)).toEqual(state);
  });
});
