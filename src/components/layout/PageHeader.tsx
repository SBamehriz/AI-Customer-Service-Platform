import * as React from 'react';
import { cn } from '@/lib/utils';

export interface PageHeaderProps {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <div className={cn('flex flex-wrap items-end justify-between gap-3', className)}>
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold text-ink">{title}</h1>
        {description ? (
          <p className="mt-1 max-w-2xl text-base text-ink-secondary">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/** Standard page padding. Every routed page wraps its content in this. */
export function Page({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('mx-auto w-full max-w-7xl p-4 sm:p-6', className)}>{children}</div>;
}
