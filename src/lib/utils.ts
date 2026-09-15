import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Merge class names, letting later Tailwind utilities win over earlier ones. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Initials for an avatar, at most two letters, in uppercase. */
export function initials(name: string | null | undefined): string {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? '').join('') || '?';
}

/** A stable hue per string, so a person always gets the same avatar colour. */
export function hueFor(seed: string): number {
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash << 5) - hash + seed.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash) % 360;
}

export function groupBy<T, K extends string>(items: T[], key: (item: T) => K): Record<K, T[]> {
  return items.reduce(
    (groups, item) => {
      const group = key(item);
      (groups[group] ??= []).push(item);
      return groups;
    },
    {} as Record<K, T[]>,
  );
}
