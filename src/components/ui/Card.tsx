import * as React from 'react';
import { cn } from '@/lib/utils';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Removes the default padding, for cards that own their own layout. */
  flush?: boolean;
}

export function Card({ className, flush, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-line bg-surface shadow-xs',
        flush ? '' : 'p-4',
        className,
      )}
      {...props}
    />
  );
}

export interface CardHeaderProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
}

export function CardHeader({ title, description, action, className, ...props }: CardHeaderProps) {
  return (
    <div className={cn('mb-4 flex items-start justify-between gap-4', className)} {...props}>
      <div className="min-w-0">
        <h3 className="text-md font-semibold text-ink">{title}</h3>
        {description ? (
          <p className="mt-0.5 text-sm text-ink-muted">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
