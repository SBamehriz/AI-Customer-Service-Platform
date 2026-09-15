import * as React from 'react';
import { cn } from '@/lib/utils';

export type BadgeTone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info';

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-sunken text-ink-secondary',
  accent: 'bg-accent-soft text-accent-text',
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
  info: 'bg-info-soft text-info',
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  /** Adds a filled dot in the badge colour. */
  dot?: boolean;
}

export function Badge({ className, tone = 'neutral', dot, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
        TONES[tone],
        className,
      )}
      {...props}
    >
      {dot ? <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

/** Ticket and conversation statuses share one colour language across the app. */
const STATUS_TONES: Record<string, BadgeTone> = {
  new: 'accent',
  open: 'accent',
  pending: 'warning',
  on_hold: 'neutral',
  solved: 'success',
  closed: 'neutral',
  resolved: 'success',
  escalated: 'danger',
};

export const statusTone = (status: string): BadgeTone => STATUS_TONES[status] ?? 'neutral';

const PRIORITY_TONES: Record<string, BadgeTone> = {
  low: 'neutral',
  medium: 'info',
  high: 'warning',
  urgent: 'danger',
};

export const priorityTone = (priority: string): BadgeTone => PRIORITY_TONES[priority] ?? 'neutral';
