import * as React from 'react';
import type { MetricPoint } from '@/lib/types';
import { cn } from '@/lib/utils';

export interface TrendChartProps {
  data: MetricPoint[];
  height?: number;
  className?: string;
}

const PADDING = { top: 12, right: 8, bottom: 22, left: 30 };

/** Created vs. resolved over time. */
export function TrendChart({ data, height = 220, className }: TrendChartProps) {
  const [hover, setHover] = React.useState<number | null>(null);
  const [width, setWidth] = React.useState(720);
  const containerRef = React.useRef<HTMLDivElement>(null);

  // The SVG uses a pixel coordinate system, so it has to know its real width.
  React.useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    setWidth(element.clientWidth);
    return () => observer.disconnect();
  }, []);

  const plotWidth = Math.max(120, width - PADDING.left - PADDING.right);
  const plotHeight = height - PADDING.top - PADDING.bottom;
  const peak = Math.max(1, ...data.flatMap((point) => [point.created, point.resolved]));
  // Round the axis up to a clean number so gridline labels read well.
  const ceiling = niceCeiling(peak);

  const x = (index: number) =>
    PADDING.left + (data.length <= 1 ? plotWidth / 2 : (index / (data.length - 1)) * plotWidth);
  const y = (value: number) => PADDING.top + plotHeight - (value / ceiling) * plotHeight;

  const line = (key: 'created' | 'resolved') =>
    data.map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(point[key])}`).join(' ');

  const area = (key: 'created' | 'resolved') =>
    `${line(key)} L ${x(data.length - 1)} ${PADDING.top + plotHeight} L ${x(0)} ${PADDING.top + plotHeight} Z`;

  const gridValues = [0, ceiling / 2, ceiling];
  const tickIndices = axisTicks(data.length);
  const active = hover !== null ? data[hover] : null;

  const handleMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const position = event.clientX - bounds.left - PADDING.left;
    const index = Math.round((position / plotWidth) * (data.length - 1));
    setHover(Math.min(data.length - 1, Math.max(0, index)));
  };

  if (data.length === 0) {
    return (
      <div ref={containerRef} className={cn('flex items-center justify-center', className)} style={{ height }}>
        <p className="text-sm text-ink-muted">No data in this range</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={cn('relative', className)}>
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        onPointerMove={handleMove}
        onPointerLeave={() => setHover(null)}
        role="img"
        aria-label="Tickets created and resolved over time"
      >
        <defs>
          <linearGradient id="trend-created" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {gridValues.map((value) => (
          <g key={value}>
            <line
              x1={PADDING.left}
              x2={width - PADDING.right}
              y1={y(value)}
              y2={y(value)}
              stroke="var(--border-subtle)"
              strokeWidth={1}
            />
            <text
              x={PADDING.left - 8}
              y={y(value) + 3}
              textAnchor="end"
              className="numeric fill-[var(--text-muted)] text-[10px]"
            >
              {Math.round(value)}
            </text>
          </g>
        ))}

        <path d={area('created')} fill="url(#trend-created)" />
        <path
          d={line('created')}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d={line('resolved')}
          fill="none"
          stroke="var(--success)"
          strokeWidth={2}
          strokeDasharray="4 3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {tickIndices.map((index) => (
          <text
            key={index}
            x={x(index)}
            y={height - 6}
            // Anchor the end labels inward so neither is clipped by the edge.
            textAnchor={index === 0 ? 'start' : index === data.length - 1 ? 'end' : 'middle'}
            className="fill-[var(--text-muted)] text-[10px]"
          >
            {shortDate(data[index].date)}
          </text>
        ))}

        {hover !== null ? (
          <g>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={PADDING.top}
              y2={PADDING.top + plotHeight}
              stroke="var(--border-strong)"
              strokeWidth={1}
            />
            <circle cx={x(hover)} cy={y(data[hover].created)} r={3.5} fill="var(--accent)" />
            <circle cx={x(hover)} cy={y(data[hover].resolved)} r={3.5} fill="var(--success)" />
          </g>
        ) : null}
      </svg>

      {active ? (
        <div
          className="pointer-events-none absolute top-1 rounded-md border border-line bg-surface px-2.5 py-1.5 shadow-md"
          style={{
            // Flip the readout to the left near the right edge so it stays in view.
            left: Math.min(Math.max(x(hover!) - 60, 0), Math.max(0, width - 130)),
          }}
        >
          <p className="text-2xs font-medium text-ink-muted">{shortDate(active.date, true)}</p>
          <p className="numeric text-xs text-ink">
            <span className="text-accent">●</span> {active.created} created
          </p>
          <p className="numeric text-xs text-ink">
            <span className="text-success">●</span> {active.resolved} resolved
          </p>
        </div>
      ) : null}

      <div className="mt-1 flex items-center gap-4 pl-[30px] text-xs text-ink-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded bg-accent" /> Created
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded bg-success" /> Resolved
        </span>
      </div>
    </div>
  );
}

function niceCeiling(peak: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(peak));
  return Math.ceil(peak / magnitude) * magnitude;
}

/** At most six labels on the x axis, evenly spaced, always including the last day. */
function axisTicks(length: number): number[] {
  if (length <= 1) return [0];
  const step = Math.max(1, Math.round(length / 6));
  const ticks: number[] = [];
  for (let index = 0; index < length; index += step) ticks.push(index);
  if (ticks[ticks.length - 1] !== length - 1) ticks.push(length - 1);
  return ticks;
}

function shortDate(value: string, withYear = false): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(withYear ? { year: 'numeric' } : {}),
  });
}
