import * as React from 'react';
import { AlertCircle, Inbox } from '@/components/icons';
import { cn } from '@/lib/utils';
import { Button } from './Button';

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn('h-4 w-4 animate-spin text-ink-muted', className)}
      viewBox="0 0 16 16"
      fill="none"
      role="status"
      aria-label="Loading"
    >
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.5" />
      <path d="M14.5 8A6.5 6.5 0 0 0 8 1.5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ title, description, icon, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-14 text-center', className)}>
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-sunken text-ink-muted">
        {icon ?? <Inbox className="h-5 w-5" />}
      </div>
      <p className="text-md font-medium text-ink">{title}</p>
      {description ? (
        <p className="mt-1 max-w-sm text-sm text-ink-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <EmptyState
      icon={<AlertCircle className="h-5 w-5 text-danger" />}
      title="Something went wrong"
      description={error.message}
      action={
        onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Try again
          </Button>
        ) : null
      }
    />
  );
}

/** Placeholder block matching the height of the content it stands in for. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton rounded-md', className)} />;
}

export function SkeletonRows({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('space-y-2', className)}>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-12" />
      ))}
    </div>
  );
}
