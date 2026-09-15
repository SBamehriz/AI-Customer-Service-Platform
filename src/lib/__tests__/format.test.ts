import { describe, expect, it, vi, afterEach } from 'vitest';
import {
  compactNumber,
  duration,
  dayLabel,
  percent,
  plural,
  relativeTime,
  signedPercent,
  timeUntil,
  titleCase,
} from '../format';

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

afterEach(() => {
  vi.useRealTimers();
});

function at(iso: string) {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(iso));
}

describe('relativeTime', () => {
  it('counts up through minutes, hours and days', () => {
    at('2026-03-10T12:00:00Z');
    expect(relativeTime(Date.now() - 30_000)).toBe('just now');
    expect(relativeTime(Date.now() - 12 * MINUTE)).toBe('12m');
    expect(relativeTime(Date.now() - 3 * HOUR)).toBe('3h');
    expect(relativeTime(Date.now() - 2 * DAY)).toBe('2d');
  });

  it('falls back to a date once a week has passed', () => {
    at('2026-03-10T12:00:00Z');
    expect(relativeTime(Date.now() - 30 * DAY)).not.toMatch(/^\d+[mhd]$/);
  });

  it('returns nothing for a value that is not a date', () => {
    expect(relativeTime('not a date')).toBe('');
  });
});

describe('timeUntil', () => {
  it('says None when there is no deadline', () => {
    expect(timeUntil(null)).toEqual({ label: 'None', overdue: false, urgent: false });
    expect(timeUntil(undefined).label).toBe('None');
  });

  it('marks a deadline inside two hours as urgent', () => {
    at('2026-03-10T12:00:00Z');
    const soon = timeUntil(new Date(Date.now() + 30 * MINUTE));
    expect(soon.urgent).toBe(true);
    expect(soon.overdue).toBe(false);
    expect(soon.label).toBe('30m');
  });

  it('does not call a distant deadline urgent', () => {
    at('2026-03-10T12:00:00Z');
    expect(timeUntil(new Date(Date.now() + 8 * HOUR)).urgent).toBe(false);
  });

  it('says how long a lapsed deadline has been over', () => {
    at('2026-03-10T12:00:00Z');
    const late = timeUntil(new Date(Date.now() - 3 * HOUR));
    expect(late.overdue).toBe(true);
    expect(late.urgent).toBe(false);
    expect(late.label).toBe('3h over');
  });

  it('never shows a deadline as zero minutes away', () => {
    at('2026-03-10T12:00:00Z');
    expect(timeUntil(new Date(Date.now() + 1_000)).label).toBe('1m');
  });
});

describe('dayLabel', () => {
  it('names today and yesterday rather than dating them', () => {
    at('2026-03-10T12:00:00Z');
    expect(dayLabel(Date.now())).toBe('Today');
    expect(dayLabel(Date.now() - DAY)).toBe('Yesterday');
    expect(dayLabel(Date.now() - 5 * DAY)).not.toBe('Today');
  });
});

describe('duration', () => {
  it('reads as minutes, hours then days', () => {
    expect(duration(42)).toBe('42m');
    expect(duration(190)).toBe('3h 10m');
    expect(duration(120)).toBe('2h');
    expect(duration(2880)).toBe('2d');
  });

  it('says None rather than printing nothing', () => {
    expect(duration(null)).toBe('None');
    expect(duration(undefined)).toBe('None');
  });
});

describe('compactNumber', () => {
  it('keeps small numbers exact and shortens large ones', () => {
    expect(compactNumber(999)).toBe('999');
    expect(compactNumber(1000)).toBe('1k');
    expect(compactNumber(1200)).toBe('1.2k');
    expect(compactNumber(2_400_000)).toBe('2.4M');
  });

  it('handles negatives', () => {
    expect(compactNumber(-1500)).toBe('-1.5k');
  });
});

describe('percent and signedPercent', () => {
  it('formats a plain percentage', () => {
    expect(percent(12)).toBe('12%');
    expect(percent(12.34, 1)).toBe('12.3%');
  });

  it('signs a change, and leaves zero unsigned', () => {
    expect(signedPercent(0)).toBe('0%');
    expect(signedPercent(12.4)).toBe('+12.4%');
    expect(signedPercent(-3.1).startsWith('+')).toBe(false);
    expect(signedPercent(-3.1)).toContain('3.1%');
  });
});

describe('titleCase', () => {
  it('capitalises and unpicks the underscores in a status', () => {
    expect(titleCase('on_hold')).toBe('On hold');
    expect(titleCase('open')).toBe('Open');
  });
});

describe('plural', () => {
  it('uses the singular for exactly one', () => {
    expect(plural(1, 'line')).toBe('1 line');
    expect(plural(0, 'line')).toBe('0 lines');
    expect(plural(2, 'line')).toBe('2 lines');
  });

  it('takes an irregular plural when given one', () => {
    expect(plural(1, 'person', 'people')).toBe('1 person');
    expect(plural(3, 'person', 'people')).toBe('3 people');
  });
});
