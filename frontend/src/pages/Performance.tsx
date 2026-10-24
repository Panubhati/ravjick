import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
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
import { Async, Card, EmptyState, Kpi } from "../components/ui";
import { mw, num, signedMw, utcDayMonth, utcTime } from "../lib/format";
import { useApi } from "../lib/useApi";

/** "; 90% range 1,789–2,544 MW" from a [low, high] bootstrap range. */
function rangeText(range: [number, number] | undefined): string {
  return range ? `. Likely range: ${num(range[0])}–${mw(range[1])}` : "";
}

interface Props {
  meta: Meta;
  range: DateRange;
  cutoff: string;
  onRangeChange: (r: DateRange) => void;
  onCutoffChange: (c: string) => void;
}

export function Performance(props: Props) {
  const { range, cutoff } = props;
  const metrics = useApi(() => api.metrics(range, cutoff), [range.from, range.to, cutoff]);
  const series = useApi(() => api.series(range, cutoff), [range.from, range.to, cutoff]);

  return (
    <div>
      <div className="controls">
        <RangeInputs meta={props.meta} value={range} onChange={props.onRangeChange} />
        <CutoffSelect meta={props.meta} value={cutoff} onChange={props.onCutoffChange} />
      </div>

      <Async state={metrics} skeletonHeight={100}>
        {(m) => (
          <div className="kpis">
            <Kpi
              label="MAE"
              value={mw(m.overall.mae)}
              hint={`On average, the forecast was off by this much each hour${rangeText(m.overall_ci?.mae)}`}
            />
            <Kpi label="RMSE" value={mw(m.overall.rmse)} hint="Like the average miss, but big misses count more" />
            <Kpi
              label="Bias"
              value={signedMw(m.overall.bias)}
              hint={`Above zero: the forecast was usually too high, so you'd be short${rangeText(m.overall_ci?.bias)}`}
            />
            <Kpi
              label="Normalised MAE"
              value={m.overall.nmae_pct === null ? "–" : `${m.overall.nmae_pct.toFixed(1)}%`}
              hint={`The average miss as a share of average wind (${mw(m.overall.mean_actual_mw)})`}
            />
          </div>
        )}
      </Async>

      <Card
        title="Forecast vs actual (MW)"
        subtitle="Blue line: the forecast you had. Dashed line: the real wind. Drag the handles below to zoom in."
      >
        <Async state={series} skeletonHeight={320}>
          {(s) =>
            s.points.length === 0 ? (
              <EmptyState>No hours in this range.</EmptyState>
            ) : (
              <div className="chart">
                <ResponsiveContainer>
                  <LineChart data={s.points} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
                    <CartesianGrid stroke="#e3e7ee" vertical={false} />
                    <XAxis
                      dataKey="target_time"
                      tickFormatter={utcDayMonth}
                      minTickGap={40}
                      tick={{ fontSize: 12 }}
                    />
                    <YAxis tickFormatter={num} width={56} tick={{ fontSize: 12 }} />
                    <Tooltip
                      formatter={(value, name) => [mw(value as number | null), name]}
                      labelFormatter={(label) => `${utcDayMonth(String(label))} ${utcTime(String(label))} UTC`}
                    />
                    <Legend />
                    <Line
                      dataKey="forecast_mw"
                      name="Forecast you had"
                      stroke="var(--forecast)"
                      strokeWidth={1.8}
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      dataKey="actual_mw"
                      name="What actually happened"
                      stroke="var(--actual)"
                      strokeWidth={1.5}
                      strokeDasharray="5 3"
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Brush dataKey="target_time" height={24} tickFormatter={utcDayMonth} stroke="var(--accent)" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )
          }
        </Async>
      </Card>

      <Card
        title="Daily error (MW)"
        subtitle="Above zero: less wind than forecast, so you'd be short. Below zero: more wind than forecast."
      >
        <Async state={metrics} skeletonHeight={260}>
          {(m) =>
            m.by_day.length === 0 ? (
              <EmptyState>No days with data in this range.</EmptyState>
            ) : (
              <div className="chart small">
                <ResponsiveContainer>
                  <BarChart data={m.by_day} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
                    <CartesianGrid stroke="#e3e7ee" vertical={false} />
                    <XAxis
                      dataKey="delivery_date"
                      tickFormatter={(d: string) => d.slice(8)}
                      tick={{ fontSize: 12 }}
                      label={{ value: "Day of January", position: "insideBottom", offset: -2, fontSize: 12 }}
                      height={36}
                    />
                    <YAxis tickFormatter={num} width={56} tick={{ fontSize: 12 }} />
                    <Tooltip
                      formatter={(value, name) => [signedMw(value as number), name]}
                      labelFormatter={(label) => String(label)}
                    />
                    <ReferenceLine y={0} stroke="#8a93a3" />
                    <Bar dataKey="bias" name="Forecast minus actual" isAnimationActive={false}>
                      {m.by_day.map((d) => (
                        <Cell key={d.delivery_date} fill={(d.bias ?? 0) >= 0 ? "var(--over)" : "var(--under)"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )
          }
        </Async>
      </Card>
    </div>
  );
}
