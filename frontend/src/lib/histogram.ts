export interface Bin {
  start: number;
  end: number;
  mid: number;
  count: number;
}

/** Count values in fixed-width bins [start, end), aligned to multiples of `width`. */
export function histogram(values: number[], width: number): Bin[] {
  if (values.length === 0) return [];
  const first = Math.floor(Math.min(...values) / width) * width;
  const last = Math.floor(Math.max(...values) / width) * width;
  const bins: Bin[] = [];
  for (let start = first; start <= last; start += width) {
    bins.push({ start, end: start + width, mid: start + width / 2, count: 0 });
  }
  for (const v of values) {
    bins[Math.floor((v - first) / width)].count += 1;
  }
  return bins;
}
