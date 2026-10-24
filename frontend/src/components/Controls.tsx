import type { Meta } from "../api/types";

export function CutoffSelect(props: { meta: Meta; value: string; onChange: (v: string) => void }) {
  return (
    <label>
      Cutoff (day before, UK time)
      <select value={props.value} onChange={(e) => props.onChange(e.target.value)}>
        {props.meta.cutoff_options.map((c) => (
          <option key={c} value={c}>
            {c}
            {c === props.meta.default_cutoff ? " (default)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

export function DateInput(props: {
  label: string;
  meta: Meta;
  value: string;
  min?: string;
  max?: string;
  onChange: (v: string) => void;
}) {
  const min = props.min ?? props.meta.min_date;
  const max = props.max ?? props.meta.max_date;
  return (
    <label>
      {props.label}
      <input
        type="date"
        value={props.value}
        min={min}
        max={max}
        required
        onChange={(e) => {
          const v = e.target.value;
          // Ignore cleared or out-of-range input instead of sending a bad request.
          if (v && v >= min && v <= max) props.onChange(v);
        }}
      />
    </label>
  );
}

export interface DateRange {
  from: string;
  to: string;
}

export function RangeInputs(props: { meta: Meta; value: DateRange; onChange: (r: DateRange) => void }) {
  const { value } = props;
  return (
    <>
      <DateInput
        label="From"
        meta={props.meta}
        value={value.from}
        max={value.to}
        onChange={(from) => props.onChange({ ...value, from })}
      />
      <DateInput
        label="To"
        meta={props.meta}
        value={value.to}
        min={value.from}
        onChange={(to) => props.onChange({ ...value, to })}
      />
    </>
  );
}
