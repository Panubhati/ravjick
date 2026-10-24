import { useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { DecisionForecast, Meta } from "../api/types";
import { CutoffSelect, DateInput } from "../components/Controls";
import { Async, Card, Kpi } from "../components/ui";
import { downloadCsv, toCsv } from "../lib/csv";
import { buyPlan, chartRows, daySummary, publishBanner } from "../lib/decision";
import { energy, longDate, mw, num, signedMw, utcDayMonth, utcTime } from "../lib/format";
import { useApi } from "../lib/useApi";

/** "2026-01-15" + 1 -> "2026-01-16" (UTC calendar arithmetic). */
function shiftDay(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

interface Props {
  meta: Meta;
  date: string;
  cutoff: string;
  onDateChange: (d: string) => void;
  onCutoffChange: (c: string) => void;
}

export function DecisionPlanner(props: Props) {
  const [showActual, setShowActual] = useState(false);
  const state = useApi(
    () => api.decisionForecast(props.date, props.cutoff),
    [props.date, props.cutoff],
  );

  return (
    <div>
      <div className="controls">
        <div className="date-stepper">
          <button
            className="secondary step"
            aria-label="Previous day"
            disabled={props.date <= props.meta.min_date}
            onClick={() => props.onDateChange(shiftDay(props.date, -1))}
          >
            ‹
          </button>
          <DateInput label="Delivery day" meta={props.meta} value={props.date} onChange={props.onDateChange} />
          <button
            className="secondary step"
            aria-label="Next day"
            disabled={props.date >= props.meta.max_date}
            onClick={() => props.onDateChange(shiftDay(props.date, 1))}
          >
            ›
          </button>
        </div>
        <CutoffSelect meta={props.meta} value={props.cutoff} onChange={props.onCutoffChange} />
        <label className="toggle">
          <input type="checkbox" checked={showActual} onChange={(e) => setShowActual(e.target.checked)} />
          Show what actually happened
        </label>
      </div>
      <Async state={state} skeletonHeight={480}>
        {(data) => <DecisionView data={data} showActual={showActual} />}
      </Async>
    </div>
  );
}

function DecisionView({ data, showActual }: { data: DecisionForecast; showActual: boolean }) {
  const summary = daySummary(data.points);
  const rows = chartRows(data.points, data.buffer_90_mw);
  const missingHours = data.points.filter((p) => p.missing).map((p) => utcTime(p.target_time));

  return (
    <>
      <div className="banner" role="status">
        <strong>{publishBanner(data.publish_times, data.cutoff)}</strong>
        <span>
          Delivery {longDate(data.delivery_date)} · decision made at {utcTime(data.cutoff_datetime)} on{" "}
          {utcDayMonth(data.cutoff_datetime)}
          {data.horizon_min_h !== null &&
            ` · forecast made ${data.horizon_min_h} to ${data.horizon_max_h} hours in advance`}
        </span>
      </div>

      {missingHours.length > 0 && (
        <div className="notice" role="alert">
          <strong>
            {missingHours.length} of 24 hours had no forecast out by this cutoff:
          </strong>{" "}
          {missingHours.join(", ")}. They are left blank and never filled from later forecasts.
        </div>
      )}

      <div className="kpis">
        <Kpi
          label="Peak forecast hour"
          value={summary.peakHour ?? "–"}
          hint={summary.peakMw !== null ? `${mw(summary.peakMw)} of wind expected` : undefined}
        />
        <Kpi label="Average forecast" value={mw(summary.averageMw)} hint="Average over the 24 hours" />
        <Kpi
          label="Shortfall buffer (90%)"
          value={mw(data.buffer_90_mw)}
          hint="Buy this much extra to be safe in 9 hours out of 10 (based on January)"
        />
        <Kpi
          label="Buffer without hindsight"
          value={data.rolling_buffer_90_mw === null ? "Not enough history" : mw(data.rolling_buffer_90_mw)}
          hint="Same idea, but using only past days you knew about that morning"
        />
        <Kpi
          label="Forecast runs high by"
          value={signedMw(data.bias_mw)}
          hint={
            data.bias_mw !== null && data.bias_mw > 0
              ? "Real wind was usually lower than this forecast"
              : "Average of forecast minus real wind in January"
          }
        />
        {showActual && (
          <Kpi label="This day's MAE" value={mw(data.day_mae_mw)} hint="On average, the forecast was off by this much each hour" />
        )}
      </div>

      <Card
        title="Expected wind power through the day (MW)"
        subtitle="Blue line: the wind forecast you had. Shaded area: how low the wind could really go (9 hours in 10)."
      >
        <div className="chart">
          <ResponsiveContainer>
            <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
              <CartesianGrid stroke="#e3e7ee" vertical={false} />
              <XAxis dataKey="hour" interval={2} tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={num} width={56} tick={{ fontSize: 12 }} />
              <Tooltip
                formatter={(value, name) =>
                  Array.isArray(value)
                    ? [`${num(value[0] as number)} to ${num(value[1] as number)} MW`, name]
                    : [mw(value as number | null), name]
                }
                labelFormatter={(label) => `${label} UTC`}
              />
              <Legend />
              <Area
                dataKey="band"
                name="Shortfall buffer range (90%)"
                fill="var(--band)"
                fillOpacity={0.45}
                stroke="none"
                isAnimationActive={false}
              />
              <Line
                dataKey="forecast"
                name="Forecast you had"
                stroke="var(--forecast)"
                strokeWidth={2.5}
                dot={false}
                connectNulls={false}
                isAnimationActive={false}
              />
              {showActual && (
                <Line
                  dataKey="actual"
                  name="What actually happened"
                  stroke="var(--actual)"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  dot={false}
                  isAnimationActive={false}
                />
              )}
              {missingHours.map((h) => (
                <ReferenceLine
                  key={h}
                  x={h}
                  stroke="var(--warn-border)"
                  strokeDasharray="2 2"
                  label={{ value: "missing", fontSize: 10, position: "top" }}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        {!showActual && (
          <p className="chart-note">
            Tick “Show what actually happened” to see the real wind.
          </p>
        )}
      </Card>

      <BuyCalculator data={data} />

      <HourlyTable data={data} showActual={showActual} />
    </>
  );
}

type BufferChoice = "january" | "no-hindsight" | "none";

/** Section 2 of the brief: demand minus expected wind = what to buy elsewhere. */
function BuyCalculator({ data }: { data: DecisionForecast }) {
  const [demand, setDemand] = useState(30000);
  const [choice, setChoice] = useState<BufferChoice>("january");
  const buffer =
    choice === "january" ? data.buffer_90_mw : choice === "no-hindsight" ? data.rolling_buffer_90_mw : null;
  const plan = buyPlan(data.points, demand, buffer);
  const bufferHint =
    buffer === null ? "No extra for weaker wind" : `Includes ${mw(buffer)} extra in case the wind is weaker`;

  return (
    <section className="card">
      <details className="table-panel">
        <summary>How much to buy</summary>
        <p className="subtitle">
          Type how much power you need. We take away the expected wind and show how much to buy elsewhere.
        </p>
        <div className="controls">
          <label>
            Power you need each hour (MW)
            <input
              type="number"
              min={0}
              step={500}
              value={demand}
              onChange={(e) => {
                const v = Number(e.target.value);
                if (Number.isFinite(v) && v >= 0) setDemand(v);
              }}
            />
          </label>
          <label>
            Safety buffer
            <select value={choice} onChange={(e) => setChoice(e.target.value as BufferChoice)}>
              <option value="january">Shortfall buffer (90%), January</option>
              <option value="no-hindsight" disabled={data.rolling_buffer_90_mw === null}>
                Buffer without hindsight
              </option>
              <option value="none">No buffer</option>
            </select>
          </label>
        </div>
        <div className="kpis">
          <Kpi
            label="To buy if the forecast is right"
            value={energy(plan.totalMwh)}
            hint="What you need minus the expected wind, for the whole day"
          />
          <Kpi
            label="To buy with the buffer"
            value={energy(plan.totalWithBufferMwh)}
            hint={bufferHint}
          />
          <Kpi
            label="Busiest hour to cover"
            value={plan.peakWithBuffer?.hour ?? "–"}
            hint={plan.peakWithBuffer ? `${mw(plan.peakWithBuffer.mw)} to buy in that hour` : undefined}
          />
        </div>
        <p className="chart-note">
          We assume you need the same amount every hour. If an hour has no forecast, we count no wind for it.
        </p>
      </details>
    </section>
  );
}

function HourlyTable({ data, showActual }: { data: DecisionForecast; showActual: boolean }) {
  const download = () => {
    const rows = data.points.map((p) => ({ ...p, delivery_date: data.delivery_date, cutoff: data.cutoff }));
    const columns = [
      "delivery_date",
      "cutoff",
      "target_time",
      "forecast_mw",
      "publish_time",
      "horizon_h",
      "actual_mw",
      "error_mw",
      "missing",
    ];
    downloadCsv(`decision-forecast_${data.delivery_date}_cutoff-${data.cutoff.replace(":", "")}.csv`, toCsv(rows, columns));
  };

  return (
    <section className="card">
      <details className="table-panel">
        <summary>Hourly values (24 hours)</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Hour</th>
                <th>Forecast (MW)</th>
                <th>Forecast issued</th>
                <th>Hours in advance</th>
                {showActual && <th>Actual (MW)</th>}
                {showActual && <th>Forecast minus actual (MW)</th>}
              </tr>
            </thead>
            <tbody>
              {data.points.map((p) => (
                <tr key={p.target_time} className={p.missing ? "missing" : undefined}>
                  <td>{utcTime(p.target_time)}</td>
                  <td>{p.missing ? <span className="badge">Missing</span> : num(p.forecast_mw)}</td>
                  <td>{p.publish_time ? `${utcTime(p.publish_time)} ${utcDayMonth(p.publish_time)}` : "–"}</td>
                  <td>{p.horizon_h ?? "–"}</td>
                  {showActual && <td>{num(p.actual_mw)}</td>}
                  {showActual && <td>{signedMw(p.error_mw)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button className="secondary" onClick={download}>
          Download CSV
        </button>
      </details>
    </section>
  );
}
