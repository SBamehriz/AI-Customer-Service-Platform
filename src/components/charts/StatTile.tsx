import * as React from 'react';
import { ArrowDownRight, ArrowUpRight, Minus } from '@/components/icons';
import { Sparkline } from './Sparkline';
import { signedPercent } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface StatTileProps {
  label: string;
  value: React.ReactNode;
  /** Change against the previous period, as a percentage. */
  delta?: number;
  /** Whether an increase is good. Backlog going up is bad, CSAT going up is good. */
  goodWhen?: 'up' | 'down';
  hint?: string;
  trend?: number[];
  className?: string;
}

export function StatTile({
  label,
  value,
  delta,
  goodWhen = 'up',
  hint,
  trend,
  className,
}: StatTileProps) {
  const flat = delta === undefined || Math.abs(delta) < 0.05;
  const rising = (delta ?? 0) > 0;
  const good = flat ? null : (rising ? goodWhen === 'up' : goodWhen === 'down');
  const Icon = flat ? Minus : rising ? ArrowUpRight : ArrowDownRight;

  return (
    <div className={cn('rounded-lg border border-line bg-surface p-4', className)}>
      <p className="text-sm text-ink-muted">{label}</p>
      <div className="mt-1.5 flex items-end justify-between gap-3">
        <p className="numeric text-3xl font-semibold leading-none tracking-[-0.02em] text-ink">
          {value}
        </p>
        {trend && trend.length > 1 ? (
          <Sparkline
            values={trend}
            tone={good === false ? 'danger' : good === true ? 'success' : 'accent'}
          />
        ) : null}
      </div>
      <div className="mt-2.5 flex items-center gap-1.5 text-xs">
        {delta !== undefined ? (
          <span
            className={cn(
              'inline-flex items-center gap-0.5 font-medium',
              good === null ? 'text-ink-muted' : good ? 'text-success' : 'text-danger',
            )}
          >
            <Icon className="h-3 w-3" />
            {signedPercent(delta)}
          </span>
        ) : null}
        {hint ? <span className="truncate text-ink-muted">{hint}</span> : null}
      </div>
    </div>
  );
}
