import type { MixEntry } from '@/lib/types';
import { cn } from '@/lib/utils';

export interface BarListProps {
  data: MixEntry[];
  formatLabel?: (label: string) => string;
  /** Optional colour per row, for example a backlog coloured by priority. */
  colorFor?: (entry: MixEntry) => string;
  className?: string;
  emptyLabel?: string;
}

/** Ranked categories as inline bars. */
export function BarList({
  data,
  formatLabel = (label) => label,
  colorFor,
  className,
  emptyLabel = 'Nothing to show yet',
}: BarListProps) {
  const peak = Math.max(1, ...data.map((entry) => entry.value));

  if (data.length === 0) {
    return <p className={cn('py-6 text-center text-sm text-ink-muted', className)}>{emptyLabel}</p>;
  }

  return (
    <ul className={cn('space-y-1', className)}>
      {data.map((entry) => (
        <li key={entry.label} className="relative">
          <div
            className="absolute inset-y-0 left-0 rounded-md transition-[width] duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]"
            style={{
              width: `${(entry.value / peak) * 100}%`,
              background: colorFor?.(entry) ?? 'var(--accent-soft)',
            }}
            aria-hidden="true"
          />
          <div className="relative flex items-center justify-between gap-3 px-2.5 py-1.5">
            <span className="min-w-0 truncate text-sm text-ink">{formatLabel(entry.label)}</span>
            <span className="numeric shrink-0 text-sm font-medium text-ink-secondary">
              {entry.value}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
