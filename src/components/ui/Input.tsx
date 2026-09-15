import * as React from 'react';
import { cn } from '@/lib/utils';

const FIELD_BASE = cn(
  'w-full rounded-md border border-line bg-surface text-base text-ink',
  'placeholder:text-ink-muted',
  'transition-[border-color,box-shadow] duration-150',
  'hover:border-line-strong',
  'focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25',
  'disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-muted',
);

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Rendered inside the field on the left, with the input padding around it. */
  leading?: React.ReactNode;
  trailing?: React.ReactNode;
  invalid?: boolean;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, leading, trailing, invalid, ...props },
  ref,
) {
  const field = (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        FIELD_BASE,
        'h-9 px-3',
        leading ? 'pl-9' : '',
        trailing ? 'pr-9' : '',
        invalid ? 'border-danger focus:border-danger focus:ring-danger/25' : '',
        className,
      )}
      {...props}
    />
  );

  if (!leading && !trailing) return field;

  return (
    <div className="relative">
      {leading ? (
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted">
          {leading}
        </span>
      ) : null}
      {field}
      {trailing ? (
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted">
          {trailing}
        </span>
      ) : null}
    </div>
  );
});

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }
>(function Textarea({ className, invalid, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        FIELD_BASE,
        'min-h-[80px] resize-y px-3 py-2 leading-relaxed',
        invalid ? 'border-danger focus:border-danger focus:ring-danger/25' : '',
        className,
      )}
      {...props}
    />
  );
});

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(function Select({ className, children, ...props }, ref) {
  return (
    <select
      ref={ref}
      className={cn(
        FIELD_BASE,
        'h-9 cursor-pointer appearance-none bg-no-repeat pl-3 pr-8',
        className,
      )}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M3 4.5 6 7.5 9 4.5' stroke='%23787e8a' stroke-width='1.4' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
        backgroundPosition: 'right 10px center',
      }}
      {...props}
    >
      {children}
    </select>
  );
});

export interface FieldProps {
  label: string;
  hint?: React.ReactNode;
  error?: string | null;
  htmlFor?: string;
  children: React.ReactNode;
  className?: string;
}

/** Label, control and message in the standard vertical rhythm. */
export function Field({ label, hint, error, htmlFor, children, className }: FieldProps) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={htmlFor} className="block text-sm font-medium text-ink-secondary">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-xs text-danger">{error}</p>
      ) : hint ? (
        <p className="text-xs text-ink-muted">{hint}</p>
      ) : null}
    </div>
  );
}

export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  disabled?: boolean;
  id?: string;
}

export function Switch({ checked, onChange, label, disabled, id }: SwitchProps) {
  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-[22px] w-[38px] shrink-0 items-center rounded-full',
        'transition-colors duration-200 disabled:opacity-50',
        checked ? 'bg-accent' : 'bg-line-strong',
      )}
    >
      <span
        className={cn(
          'inline-block h-[18px] w-[18px] rounded-full bg-white shadow-sm',
          'transition-transform duration-200 ease-[cubic-bezier(0.32,0.72,0,1)]',
          checked ? 'translate-x-[18px]' : 'translate-x-[2px]',
        )}
      />
    </button>
  );
}
