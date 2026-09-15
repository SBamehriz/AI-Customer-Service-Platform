import { cn } from '@/lib/utils';

export interface LogoProps {
  size?: number;
  className?: string;
}

/** The mark. Three inbound channel strokes converging into one rounded square. */
export function LogoMark({ size = 28, className }: LogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={cn('shrink-0', className)}
      aria-hidden="true"
    >
      <rect
        x="11.5"
        y="11.5"
        width="9"
        height="9"
        rx="3"
        fill="currentColor"
      />
      <path
        d="M6 6.5h2.5a3 3 0 0 1 3 3V13"
        stroke="currentColor"
        strokeWidth="2.1"
        strokeLinecap="round"
        opacity="0.5"
      />
      <path
        d="M26 6.5h-2.5a3 3 0 0 0-3 3V13"
        stroke="currentColor"
        strokeWidth="2.1"
        strokeLinecap="round"
        opacity="0.5"
      />
      <path
        d="M16 25.5V23"
        stroke="currentColor"
        strokeWidth="2.1"
        strokeLinecap="round"
        opacity="0.5"
      />
      <path
        d="M4.5 16.5H9"
        stroke="currentColor"
        strokeWidth="2.1"
        strokeLinecap="round"
        opacity="0.28"
      />
      <path
        d="M27.5 16.5H23"
        stroke="currentColor"
        strokeWidth="2.1"
        strokeLinecap="round"
        opacity="0.28"
      />
    </svg>
  );
}

export interface WordmarkProps extends LogoProps {
  /** Short form for tight spaces like a collapsed sidebar. */
  compact?: boolean;
}

export function Wordmark({ size = 26, compact, className }: WordmarkProps) {
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <LogoMark size={size} className="text-accent" />
      {!compact ? (
        <span className="text-md font-semibold tracking-[-0.02em] text-ink">
          Unified<span className="text-ink-muted"> Service</span>
        </span>
      ) : null}
    </span>
  );
}
