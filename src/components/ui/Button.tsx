import * as React from 'react';
import { cn } from '@/lib/utils';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'link';
type Size = 'sm' | 'md' | 'lg' | 'icon';

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-accent text-white shadow-xs hover:bg-accent-hover active:brightness-95 disabled:bg-accent/50',
  secondary:
    'bg-surface text-ink border border-line shadow-xs hover:bg-hover active:bg-active disabled:text-ink-muted',
  ghost: 'text-ink-secondary hover:bg-hover hover:text-ink active:bg-active',
  danger: 'bg-danger text-white shadow-xs hover:brightness-110 active:brightness-95',
  link: 'text-accent-text hover:underline underline-offset-4 px-0',
};

const SIZES: Record<Size, string> = {
  sm: 'h-7 px-2.5 text-xs gap-1.5 rounded-md',
  md: 'h-9 px-3.5 text-base gap-2 rounded-md',
  lg: 'h-11 px-5 text-md gap-2 rounded-lg',
  icon: 'h-9 w-9 rounded-md',
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  /** Rendered before the label, and hidden while loading. */
  icon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = 'secondary', size = 'md', loading, icon, children, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        'inline-flex select-none items-center justify-center whitespace-nowrap font-medium',
        'transition-[background-color,color,box-shadow,opacity] duration-150',
        'disabled:pointer-events-none disabled:opacity-60',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
});

function Spinner() {
  return (
    <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.5" />
      <path
        d="M14.5 8A6.5 6.5 0 0 0 8 1.5"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
