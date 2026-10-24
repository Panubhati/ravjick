import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { Meta } from "../api/types";
import { CutoffSelect, RangeInputs, type DateRange } from "../components/Controls";
import { Async, Card, EmptyState } from "../components/ui";
import { hourLabel, mw, num, signedMw } from "../lib/format";
import { visibleFindings } from "../lib/findings";
import { histogram } from "../lib/histogram";
import { useApi } from "../lib/useApi";

const BIN_WIDTH_MW = 500;
const GRID = <CartesianGrid stroke="#e3e7ee" vertical={false} />;
const MARGIN = { top: 8, right: 12, bottom: 4, left: 4 };

interface Props {
  meta: Meta;
  range: DateRange;
  cutoff: string;
  onRangeChange: (r: DateRange) => void;
  onCutoffChange: (c: string) => void;
}

const mwTooltip = (value: unknown, name: unknown) =>
  [String(name) === "Forecast minus actual" ? signedMw(value as number) : mw(value as number), String(name)] as [string, string];

export function Insights(props: Props) {
  const { range, cutoff } = props;
  const metrics = useApi(() => api.metrics(range, cutoff), [range.from, range.to, cutoff]);
  const series = useApi(() => api.series(range, cutoff), [range.from, range.to, cutoff]);
  const horizon = useApi(() => api.errorByHorizon(range), [range.from, range.to]);
  const sensitivity = useApi(() => api.cutoffSensitivity(range), [range.from, range.to]);
  const [showAllFindings, setShowAllFindings] = useState(false);

  return (
    <div>
      <div className="controls">
        <RangeInputs meta={props.meta} value={range} onChange={props.onRangeChange} />
        <CutoffSelect meta={props.meta} value={cutoff} onChange={props.onCutoffChange} />
      </div>

      <Card title="Key findings" subtitle="Based on the dates and cutoff you picked.">
        <Async state={metrics} skeletonHeight={160}>
          {(m) => (
            <>
              <ul className="findings">
                {visibleFindings(m.findings, showAllFindings).map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
              {m.findings.length > visibleFindings(m.findings, false).length && (
                <button className="secondary" onClick={() => setShowAllFindings((v) => !v)}>
                  {showAllFindings ? "Show fewer findings" : `Show all ${m.findings.length} findings`}
                </button>
              )}
            </>
          )}
        </Async>
      </Card>

      <div className="grid-2">
        <Card
          title="Error histogram"
          subtitle="How many hours missed by how much. Right of zero: less wind than forecast (you'd be short)."
        >
          <Async state={series} skeletonHeight={260}>
            {(s) => {
              const errors = s.points.flatMap((p) => (p.error_mw === null ? [] : [p.error_mw]));
              const buffer = metrics.data?.overall.buffer_90 ?? null;
              if (errors.length === 0) return <EmptyState>No matched hours in this range.</EmptyState>;
              return (
                <div className="chart small">
                  <ResponsiveContainer>
                    <BarChart data={histogram(errors, BIN_WIDTH_MW)} margin={MARGIN} barCategoryGap={1}>
                      {GRID}
                      <XAxis
                        dataKey="mid"
                        type="number"
                        domain={["dataMin - 250", "dataMax + 250"]}
                        tickFormatter={num}
                        tick={{ fontSize: 12 }}
                      />
                      <YAxis allowDecimals={false} width={40} tick={{ fontSize: 12 }} />
                      <Tooltip
                        formatter={(value) => [`${value} hours`, "Count"]}
                        labelFormatter={(mid) =>
                          `${num(Number(mid) - BIN_WIDTH_MW / 2)} to ${num(Number(mid) + BIN_WIDTH_MW / 2)} MW`
                        }
                      />
                      <Bar dataKey="count" name="Hours" fill="var(--accent)" isAnimationActive={false} />
                      <ReferenceLine x={0} stroke="#8a93a3" />
                      {buffer !== null && (
                        <ReferenceLine
                          x={buffer}
                          stroke="var(--over)"
                          strokeWidth={2}
                          strokeDasharray="6 3"
                          label={{ value: `Shortfall buffer (90%) ${mw(buffer)}`, position: "insideTopRight", fontSize: 12 }}
                        />
                      )}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              );
            }}
          </Async>
        </Card>

        <Card title="MAE by hour of day" subtitle="Bars: average miss. Dashed line: how much too high the forecast was. UK time.">
          <Async state={metrics} skeletonHeight={260}>
            {(m) => (
              <div className="chart small">
                <ResponsiveContainer>
                  <ComposedChart data={m.by_hour} margin={MARGIN}>
                    {GRID}
                    <XAxis dataKey="hour" tickFormatter={hourLabel} interval={3} tick={{ fontSize: 12 }} />
                    <YAxis tickFormatter={num} width={56} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={mwTooltip} labelFormatter={(h) => `${hourLabel(Number(h))} UTC`} />
                    <Legend />
                    <Bar dataKey="mae" name="MAE" fill="var(--band)" isAnimationActive={false} />
                    <Line
                      dataKey="bias"
                      name="Forecast minus actual"
                      stroke="var(--over)"
                      strokeDasharray="5 3"
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            )}
          </Async>
        </Card>

        <Card
          title="Error by wind level"
          subtitle={
            metrics.data?.wind_thresholds
              ? `Hours sorted into low, medium and high wind. Low: up to ${mw(metrics.data.wind_thresholds.low_max_mw)}. High: above ${mw(metrics.data.wind_thresholds.medium_max_mw)}.`
              : "Hours sorted into low, medium and high wind."
          }
        >
          <Async state={metrics} skeletonHeight={260}>
            {(m) => (
              <div className="chart small">
                <ResponsiveContainer>
                  <BarChart data={m.by_wind_level} margin={MARGIN}>
                    {GRID}
                    <XAxis
                      dataKey="level"
                      tickFormatter={(l: string) => ({ low: "Low wind", medium: "Medium wind", high: "High wind" })[l] ?? l}
                      tick={{ fontSize: 12 }}
                    />
                    <YAxis tickFormatter={num} width={56} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={mwTooltip} />
                    <Legend />
                    <Bar dataKey="mae" name="MAE" fill="var(--accent)" isAnimationActive={false} />
                    <Bar dataKey="bias" name="Forecast minus actual" fill="var(--over)" isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </Async>
        </Card>

        <Card
          title="Error by forecast horizon"
          subtitle="All forecasts, grouped by how many hours ahead they were made."
        >
          <Async state={horizon} skeletonHeight={260}>
            {(h) => (
              <div className="chart small">
                <ResponsiveContainer>
                  <BarChart data={h.buckets} margin={MARGIN}>
                    {GRID}
                    <XAxis dataKey="bucket" tick={{ fontSize: 12 }} />
                    <YAxis tickFormatter={num} width={56} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={mwTooltip} />
                    <Legend />
                    <Bar dataKey="mae" name="MAE" fill="var(--accent)" isAnimationActive={false} />
                    <Bar dataKey="bias" name="Forecast minus actual" fill="var(--over)" isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </Async>
        </Card>

        <Card
          title="Look-ahead check: what if you could see later forecasts?"
          subtitle="Left: the forecast you really had. Right: a newer forecast you could not have had in time. Using the newer one would make the results look better than they really were. We never do that."
        >
          <Async state={metrics} skeletonHeight={260}>
            {(m) => {
              const rows = [
                { name: "At your cutoff", ...m.look_ahead.at_cutoff },
                { name: "Newest before delivery", ...m.look_ahead.latest_before_delivery },
              ];
              return (
                <>
                  <div className="chart small">
                    <ResponsiveContainer>
                      <BarChart data={rows} margin={MARGIN}>
                        {GRID}
                        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                        <YAxis tickFormatter={num} width={56} tick={{ fontSize: 12 }} />
                        <Tooltip formatter={mwTooltip} />
                        <Legend />
                        <Bar dataKey="mae" name="MAE" fill="var(--accent)" isAnimationActive={false} />
                        <Bar dataKey="bias" name="Forecast minus actual" fill="var(--over)" isAnimationActive={false} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="chart-note">
                    Your forecast was made about {m.look_ahead.at_cutoff.median_horizon_h} hours ahead. The newer one only{" "}
                    {m.look_ahead.latest_before_delivery.median_horizon_h} hours ahead.
                  </p>
                </>
              );
            }}
          </Async>
        </Card>

        <Card
          title="Shortfall buffer without hindsight"
          subtitle="Dashed line: the buffer you could have worked out each morning, using only past days. Solid line: the January buffer. Did it really keep you safe?"
        >
          <Async state={metrics} skeletonHeight={260}>
            {(m) => {
              const r = m.rolling_buffer;
              return (
                <>
                  <div className="chart small">
                    <ResponsiveContainer>
                      <LineChart data={r.days} margin={MARGIN}>
                        {GRID}
                        <XAxis
                          dataKey="delivery_date"
                          tickFormatter={(d: string) => d.slice(8)}
                          tick={{ fontSize: 12 }}
                        />
                        <YAxis tickFormatter={num} width={56} tick={{ fontSize: 12 }} domain={[0, "auto"]} />
                        <Tooltip formatter={(v) => [mw(v as number | null), "Buffer without hindsight"]} />
                        <Legend />
                        {m.overall.buffer_90 !== null && (
                          <ReferenceLine
                            y={m.overall.buffer_90}
                            stroke="var(--accent)"
                            strokeWidth={2}
                            label={{ value: `January buffer ${mw(m.overall.buffer_90)}`, position: "insideBottomRight", fontSize: 12 }}
                          />
                        )}
                        <Line
                          dataKey="buffer_mw"
                          name="Buffer without hindsight"
                          stroke="var(--over)"
                          strokeWidth={2}
                          strokeDasharray="6 3"
                          dot={false}
                          connectNulls={false}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="chart-note">
                    {r.n_days > 0 && r.coverage_pct !== null
                      ? `It kept you safe in ${r.coverage_pct.toFixed(0)}% of hours (the goal was ${r.target_pct}%). Average buffer: ${mw(r.mean_buffer_mw)}, over ${r.n_days} days.`
                      : "Not enough past days in this range to test this."}
                  </p>
                </>
              );
            }}
          </Async>
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card
          title="Cutoff sensitivity"
          subtitle="Average miss and shortfall buffer for each cutoff time. Forecasts come out at set times (04:30, 07:30, 09:30, 11:30), so some cutoffs use the same forecast."
        >
          <Async state={sensitivity} skeletonHeight={260}>
            {(s) => (
              <div className="chart small">
                <ResponsiveContainer>
                  <LineChart data={s.rows} margin={MARGIN}>
                    {GRID}
                    <XAxis dataKey="cutoff" tick={{ fontSize: 12 }} />
                    <YAxis tickFormatter={num} width={56} tick={{ fontSize: 12 }} domain={[0, "auto"]} />
                    <Tooltip formatter={mwTooltip} labelFormatter={(c) => `Cutoff ${c}`} />
                    <Legend />
                    <Line
                      dataKey="mae"
                      name="MAE"
                      stroke="var(--accent)"
                      strokeWidth={2.5}
                      isAnimationActive={false}
                    />
                    <Line
                      dataKey="buffer_90"
                      name="Shortfall buffer (90%)"
                      stroke="var(--over)"
                      strokeWidth={2.5}
                      strokeDasharray="6 3"
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </Async>
        </Card>
      </div>
    </div>
  );
}
