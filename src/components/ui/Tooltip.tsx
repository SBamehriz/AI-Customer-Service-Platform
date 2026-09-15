import * as React from 'react';
import { cn } from '@/lib/utils';

export interface TooltipProps {
  label: React.ReactNode;
  children: React.ReactElement;
  side?: 'top' | 'bottom' | 'right';
  className?: string;
}

/** A tooltip built with CSS alone. */
export function Tooltip({ label, children, side = 'top', className }: TooltipProps) {
  const position =
    side === 'top'
      ? 'bottom-full left-1/2 mb-1.5 -translate-x-1/2'
      : side === 'bottom'
        ? 'top-full left-1/2 mt-1.5 -translate-x-1/2'
        : 'left-full top-1/2 ml-1.5 -translate-y-1/2';

  return (
    <span className="group/tooltip relative inline-flex">
      {children}
      <span
        role="tooltip"
        className={cn(
          'pointer-events-none absolute z-50 whitespace-nowrap rounded-md px-2 py-1',
          'bg-ink text-2xs font-medium text-ink-inverse opacity-0 shadow-md',
          'transition-opacity duration-150',
          'group-hover/tooltip:opacity-100 group-focus-within/tooltip:opacity-100',
          position,
          className,
        )}
      >
        {label}
      </span>
    </span>
  );
}
