import { cn, hueFor, initials } from '@/lib/utils';

export interface AvatarProps {
  name?: string | null;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  className?: string;
  /** Marks an AI author, which gets a fixed accent identity rather than a hue. */
  ai?: boolean;
}

const SIZES = {
  xs: 'h-5 w-5 text-[9px]',
  sm: 'h-7 w-7 text-2xs',
  md: 'h-9 w-9 text-xs',
  lg: 'h-12 w-12 text-base',
};

export function Avatar({ name, size = 'md', className, ai }: AvatarProps) {
  const hue = hueFor(name ?? 'anonymous');
  return (
    <span
      className={cn(
        'inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold',
        SIZES[size],
        ai ? 'bg-accent text-white' : '',
        className,
      )}
      style={
        ai
          ? undefined
          : {
              backgroundColor: `oklch(0.92 0.05 ${hue})`,
              color: `oklch(0.42 0.11 ${hue})`,
            }
      }
      aria-hidden="true"
    >
      {ai ? 'AI' : initials(name)}
    </span>
  );
}
