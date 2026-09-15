import { cn } from '@/lib/utils';

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  count?: number;
}

export interface SegmentedControlProps<T extends string> {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: 'sm' | 'md';
  className?: string;
  'aria-label'?: string;
}

/** A group of options where only one can be picked, with a filled indicator that slides. */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  size = 'md',
  className,
  ...props
}: SegmentedControlProps<T>) {
  return (
    <div
      role="tablist"
      aria-label={props['aria-label']}
      className={cn(
        'inline-flex items-center gap-0.5 rounded-lg bg-sunken p-0.5',
        size === 'sm' ? 'text-xs' : 'text-sm',
        className,
      )}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(option.value)}
            className={cn(
              'inline-flex items-center gap-1.5 whitespace-nowrap rounded-md font-medium',
              'transition-[background-color,color,box-shadow] duration-150',
              size === 'sm' ? 'h-6 px-2' : 'h-7 px-2.5',
              active
                ? 'bg-surface text-ink shadow-xs'
                : 'text-ink-secondary hover:text-ink',
            )}
          >
            {option.label}
            {option.count !== undefined ? (
              <span
                className={cn(
                  'numeric rounded px-1 text-2xs',
                  active ? 'bg-sunken text-ink-secondary' : 'text-ink-muted',
                )}
              >
                {option.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
