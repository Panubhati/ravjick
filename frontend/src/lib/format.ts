// Display formatting. Times are always shown in UTC (equal to UK time in January),
// never in the viewer's local time zone.

const number = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const pad = (n: number) => String(n).padStart(2, "0");

export function num(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : number.format(value);
}

export function mw(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : `${number.format(value)} MW`;
}

/** Error with an explicit sign: +1,852 MW (over-forecast) or −730 MW. */
export function signedMw(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  const rounded = Math.round(value);
  if (rounded === 0) return "0 MW";
  return `${rounded > 0 ? "+" : "−"}${number.format(Math.abs(rounded))} MW`;
}

export function utcTime(iso: string): string {
  const d = new Date(iso);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

export function utcDayMonth(iso: string): string {
  const d = new Date(iso);
  return `${pad(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]}`;
}

/** "2026-01-03" -> "Sat 03 Jan 2026" */
export function longDate(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  return `${DAYS[d.getUTCDay()]} ${pad(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function hourLabel(hour: number): string {
  return `${pad(hour)}:00`;
}

/** Energy for a day: "441,370 MWh (441 GWh)"; GWh added from 10,000 MWh. */
export function energy(mwh: number | null | undefined): string {
  if (mwh === null || mwh === undefined) return "–";
  const text = `${number.format(mwh)} MWh`;
  return mwh >= 10000 ? `${text} (${number.format(mwh / 1000)} GWh)` : text;
}
