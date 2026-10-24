import { describe, expect, it } from "vitest";
import type { DecisionPoint } from "../api/types";
import { toCsv } from "./csv";
import { buyPlan, chartRows, daySummary, publishBanner } from "./decision";
import { energy, hourLabel, longDate, mw, signedMw, utcDayMonth, utcTime } from "./format";
import { visibleFindings } from "./findings";
import { histogram } from "./histogram";

function point(hour: number, forecast: number | null, actual: number | null = null): DecisionPoint {
  const t = `2026-01-03T${String(hour).padStart(2, "0")}:00:00Z`;
  return {
    target_time: t,
    forecast_mw: forecast,
    publish_time: forecast === null ? null : "2026-01-02T07:30:00Z",
    horizon_h: forecast === null ? null : 16.5 + hour,
    actual_mw: actual,
    error_mw: forecast !== null && actual !== null ? forecast - actual : null,
    missing: forecast === null,
  };
}

describe("format", () => {
  it("formats MW with thousands separators and a dash for null", () => {
    expect(mw(4300.15)).toBe("4,300 MW");
    expect(mw(null)).toBe("–");
  });
  it("shows the sign explicitly for errors", () => {
    expect(signedMw(1851.9)).toBe("+1,852 MW");
    expect(signedMw(-730)).toBe("−730 MW");
    expect(signedMw(0)).toBe("0 MW");
  });
  it("formats UTC times and dates without the browser's time zone", () => {
    expect(utcTime("2026-01-02T07:30:00Z")).toBe("07:30");
    expect(utcDayMonth("2026-01-02T07:30:00Z")).toBe("02 Jan");
    expect(longDate("2026-01-03")).toBe("Sat 03 Jan 2026");
    expect(hourLabel(5)).toBe("05:00");
  });
});

describe("publishBanner", () => {
  it("names the single publish used", () => {
    expect(publishBanner(["2026-01-02T07:30:00Z"], "09:00")).toBe(
      "Forecast published at 07:30 on 02 Jan (available at your 09:00 cutoff)",
    );
  });
  it("lists several publishes", () => {
    expect(publishBanner(["2026-01-02T04:30:00Z", "2026-01-02T07:30:00Z"], "09:00")).toBe(
      "Forecasts published at 04:30 on 02 Jan and 07:30 on 02 Jan (the latest available for each hour at your 09:00 cutoff)",
    );
  });
  it("says so when nothing was available", () => {
    expect(publishBanner([], "06:00")).toBe("No forecast had been published by your 06:00 cutoff");
  });
});

describe("daySummary", () => {
  it("finds the peak hour and the average, ignoring missing hours", () => {
    const s = daySummary([point(0, 100), point(1, 300), point(2, null), point(3, 200)]);
    expect(s.peakHour).toBe("01:00");
    expect(s.peakMw).toBe(300);
    expect(s.averageMw).toBe(200);
    expect(s.nAvailable).toBe(3);
  });
  it("handles a day with no forecasts", () => {
    const s = daySummary([point(0, null)]);
    expect(s.peakHour).toBeNull();
    expect(s.averageMw).toBeNull();
  });
});

describe("chartRows", () => {
  it("builds a band from forecast - buffer up to forecast, never below zero", () => {
    const rows = chartRows([point(0, 5000, 4800), point(1, 1000), point(2, null)], 4300);
    expect(rows[0]).toMatchObject({ hour: "00:00", forecast: 5000, actual: 4800, band: [700, 5000] });
    expect(rows[1].band).toEqual([0, 1000]);
    expect(rows[2]).toMatchObject({ forecast: null, band: null, missing: true });
  });
  it("has no band when there is no buffer", () => {
    expect(chartRows([point(0, 5000)], null)[0].band).toBeNull();
  });
});

describe("histogram", () => {
  it("bins values into fixed-width bins aligned to the width", () => {
    const bins = histogram([-250, -10, 0, 499, 500, 1200], 500);
    expect(bins.map((b) => [b.start, b.count])).toEqual([
      [-500, 2], // -250, -10
      [0, 2], // 0, 499
      [500, 1],
      [1000, 1],
    ]);
    expect(bins[0].mid).toBe(-250);
  });
  it("returns no bins for no values", () => {
    expect(histogram([], 500)).toEqual([]);
  });
});

describe("toCsv", () => {
  it("writes a header, blanks for null, and quotes awkward values", () => {
    const csv = toCsv(
      [
        { a: 1, b: null, c: "x" },
        { a: 2, b: 3.5, c: 'say "hi", ok' },
      ],
      ["a", "b", "c"],
    );
    expect(csv).toBe('a,b,c\n1,,x\n2,3.5,"say ""hi"", ok"\n');
  });
});

describe("buyPlan", () => {
  it("buys what wind does not cover, with and without the shortfall buffer", () => {
    const plan = buyPlan([point(0, 5000), point(1, 12000), point(2, null)], 10000, 4000);
    // Hour 0: 10,000 - 5,000 = 5,000; with buffer 10,000 - (5,000 - 4,000) = 9,000.
    expect(plan.rows[0]).toMatchObject({ hour: "00:00", buy: 5000, buyWithBuffer: 9000, missing: false });
    // Hour 1: wind covers all demand; with buffer 10,000 - 8,000 = 2,000.
    expect(plan.rows[1]).toMatchObject({ buy: 0, buyWithBuffer: 2000 });
    // Missing forecast: cannot count on any wind.
    expect(plan.rows[2]).toMatchObject({ buy: 10000, buyWithBuffer: 10000, missing: true });
    expect(plan.totalMwh).toBe(15000);
    expect(plan.totalWithBufferMwh).toBe(21000);
    // Peak is the hour with no forecast (02:00): the whole 10,000 MW.
    expect(plan.peakWithBuffer).toEqual({ hour: "02:00", mw: 10000 });
  });

  it("never lets the buffer push expected wind below zero", () => {
    const plan = buyPlan([point(0, 1000)], 10000, 4000);
    expect(plan.rows[0].buyWithBuffer).toBe(10000);
  });

  it("works without a buffer", () => {
    const plan = buyPlan([point(0, 3000)], 10000, null);
    expect(plan.rows[0]).toMatchObject({ buy: 7000, buyWithBuffer: 7000 });
  });
});

describe("energy", () => {
  it("adds GWh for large amounts so they are easy to read", () => {
    expect(energy(441370)).toBe("441,370 MWh (441 GWh)");
    expect(energy(9500)).toBe("9,500 MWh");
    expect(energy(null)).toBe("–");
  });
});

describe("visibleFindings", () => {
  const all = ["a", "b", "c", "d", "e", "f", "caveat"];
  it("shows the first few plus the closing caveat when collapsed", () => {
    expect(visibleFindings(all, false, 4)).toEqual(["a", "b", "c", "d", "caveat"]);
  });
  it("shows everything when expanded or when there are few findings", () => {
    expect(visibleFindings(all, true, 4)).toEqual(all);
    expect(visibleFindings(["a", "b"], false, 4)).toEqual(["a", "b"]);
  });
});
