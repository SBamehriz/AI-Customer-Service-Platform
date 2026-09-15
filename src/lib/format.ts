/** Presentation helpers. Everything the UI shows as a date or number goes here. */

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** "just now", "12m", "3h", "2d", then an absolute date. */
export function relativeTime(value: string | number | Date): string {
  const time = new Date(value).getTime();
  const diff = Date.now() - time;
  if (Number.isNaN(diff)) return '';
  if (diff < MINUTE) return 'just now';
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h`;
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)}d`;
  return new Date(time).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Time remaining, or how long ago it lapsed. Used for SLA countdowns. */
export function timeUntil(value: string | number | Date | null | undefined): {
  label: string;
  overdue: boolean;
  urgent: boolean;
} {
  if (!value) return { label: 'None', overdue: false, urgent: false };
  const diff = new Date(value).getTime() - Date.now();
  const overdue = diff < 0;
  const magnitude = Math.abs(diff);
  const label =
    magnitude < HOUR
      ? `${Math.max(1, Math.round(magnitude / MINUTE))}m`
      : magnitude < DAY
        ? `${Math.round(magnitude / HOUR)}h`
        : `${Math.round(magnitude / DAY)}d`;
  return {
    label: overdue ? `${label} over` : label,
    overdue,
    urgent: !overdue && diff < 2 * HOUR,
  };
}

export function formatTime(value: string | number | Date): string {
  return new Date(value).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

export function formatDate(value: string | number | Date): string {
  return new Date(value).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatDateTime(value: string | number | Date): string {
  return `${formatDate(value)} · ${formatTime(value)}`;
}

/** Day label for message groups. Today, Yesterday, or a date. */
export function dayLabel(value: string | number | Date): string {
  const date = new Date(value);
  const today = new Date();
  const isSameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (isSameDay(date, today)) return 'Today';
  const yesterday = new Date(today.getTime() - DAY);
  if (isSameDay(date, yesterday)) return 'Yesterday';
  return date.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
}

/** Minutes as a readable duration, such as 42m, 3h 10m, or 2d. */
export function duration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return 'None';
  if (minutes < 60) return `${Math.round(minutes)}m`;
  if (minutes < 1440) {
    const hours = Math.floor(minutes / 60);
    const rest = Math.round(minutes % 60);
    return rest ? `${hours}h ${rest}m` : `${hours}h`;
  }
  return `${Math.round(minutes / 1440)}d`;
}

/** 1200 → "1.2k". Keeps dashboard tiles from wrapping. */
export function compactNumber(value: number): string {
  if (Math.abs(value) < 1000) return String(value);
  if (Math.abs(value) < 1_000_000) return `${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)}k`;
  return `${(value / 1_000_000).toFixed(1)}M`;
}

export function percent(value: number, digits = 0): string {
  return `${value.toFixed(digits)}%`;
}

/** Signed change for KPI tiles, such as plus 12.4% or minus 3.1%. */
export function signedPercent(value: number): string {
  if (value === 0) return '0%';
  return `${value > 0 ? '+' : '−'}${Math.abs(value).toFixed(1)}%`;
}

export const CHANNEL_LABELS: Record<string, string> = {
  web: 'Web chat',
  email: 'Email',
  whatsapp: 'WhatsApp',
  instagram: 'Instagram',
  sms: 'SMS',
  voice: 'Voice',
  api: 'API',
};

export const STATUS_LABELS: Record<string, string> = {
  new: 'New',
  open: 'Open',
  pending: 'Pending',
  on_hold: 'On hold',
  solved: 'Solved',
  closed: 'Closed',
  resolved: 'Resolved',
  escalated: 'Escalated',
};

export function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, ' ');
}

/** A count with its noun, singular when there is one of them. */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}
