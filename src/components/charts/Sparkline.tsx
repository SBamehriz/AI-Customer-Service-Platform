import { cn } from '@/lib/utils';

export interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  tone?: 'accent' | 'success' | 'danger';
  /** Window for the moving average. 1 plots the raw series. */
  smoothing?: number;
  className?: string;
}

/** A bare trend line for KPI tiles. No axes, no labels, just the shape. */
export function Sparkline({
  values,
  width = 88,
  height = 28,
  tone = 'accent',
  smoothing = 5,
  className,
}: SparklineProps) {
  if (values.length < 2) return null;

  const series = smoothing > 1 ? movingAverage(values, smoothing) : values;
  const peak = Math.max(...series);
  const floor = Math.min(...series);
  const span = peak - floor || 1;

  const points = series.map((value, index) => {
    const x = (index / (series.length - 1)) * width;
    // Inset by 2px top and bottom so the stroke is never clipped.
    const y = height - 2 - ((value - floor) / span) * (height - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const stroke =
    tone === 'success' ? 'var(--success)' : tone === 'danger' ? 'var(--danger)' : 'var(--accent)';

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn('overflow-visible', className)}
      aria-hidden="true"
    >
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke={stroke}
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Trailing average, shortening the window at the start of the series. */
function movingAverage(values: number[], window: number): number[] {
  return values.map((_, index) => {
    const start = Math.max(0, index - window + 1);
    const slice = values.slice(start, index + 1);
    return slice.reduce((total, value) => total + value, 0) / slice.length;
  });
}
