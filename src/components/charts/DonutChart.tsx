import * as React from 'react';
import type { MixEntry } from '@/lib/types';
import { cn } from '@/lib/utils';

export interface DonutChartProps {
  data: MixEntry[];
  size?: number;
  thickness?: number;
  centerLabel?: string;
  centerValue?: string | number;
  formatLabel?: (label: string) => string;
  className?: string;
}

/** Categorical share, drawn as arcs. */
const SERIES_COLORS = [
  'var(--a-500)',
  'var(--green-500)',
  'var(--amber-500)',
  'var(--violet-500)',
  'var(--red-500)',
  'var(--a-300)',
  'var(--n-400)',
];

export function DonutChart({
  data,
  size = 148,
  thickness = 18,
  centerLabel,
  centerValue,
  formatLabel = (label) => label,
  className,
}: DonutChartProps) {
  const [active, setActive] = React.useState<number | null>(null);
  const total = data.reduce((sum, entry) => sum + entry.value, 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;

  if (total === 0) {
    return (
      <div className={cn('flex items-center justify-center text-sm text-ink-muted', className)} style={{ height: size }}>
        No data
      </div>
    );
  }

  let offset = 0;

  return (
    <div className={cn('flex items-center gap-5', className)}>
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} role="img" aria-label="Share by category">
          <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
            {data.map((entry, index) => {
              const fraction = entry.value / total;
              const dash = fraction * circumference;
              // A hairline gap between arcs reads as separation without a stroke.
              const gap = data.length > 1 ? 1.5 : 0;
              const element = (
                <circle
                  key={entry.label}
                  cx={size / 2}
                  cy={size / 2}
                  r={radius}
                  fill="none"
                  stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
                  strokeWidth={active === index ? thickness + 3 : thickness}
                  strokeDasharray={`${Math.max(0, dash - gap)} ${circumference - Math.max(0, dash - gap)}`}
                  strokeDashoffset={-offset}
                  className="transition-[stroke-width] duration-150"
                  onPointerEnter={() => setActive(index)}
                  onPointerLeave={() => setActive(null)}
                />
              );
              offset += dash;
              return element;
            })}
          </g>
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="numeric text-xl font-semibold text-ink">
            {active !== null ? data[active].value : (centerValue ?? total)}
          </span>
          <span className="text-2xs text-ink-muted">
            {active !== null ? formatLabel(data[active].label) : (centerLabel ?? 'total')}
          </span>
        </div>
      </div>

      <ul className="min-w-0 flex-1 space-y-1.5">
        {data.slice(0, 6).map((entry, index) => (
          <li
            key={entry.label}
            className="flex items-center gap-2 text-sm"
            onPointerEnter={() => setActive(index)}
            onPointerLeave={() => setActive(null)}
          >
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: SERIES_COLORS[index % SERIES_COLORS.length] }}
            />
            <span className="min-w-0 flex-1 truncate text-ink-secondary">
              {formatLabel(entry.label)}
            </span>
            <span className="numeric shrink-0 text-ink-muted">{entry.share}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export { SERIES_COLORS };
