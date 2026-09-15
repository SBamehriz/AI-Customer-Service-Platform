import { describe, expect, it } from 'vitest';
import { cn, groupBy, hueFor, initials } from '../utils';

describe('cn', () => {
  it('lets a later utility win over an earlier one', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4');
    expect(cn('text-ink', 'text-ink-muted')).toBe('text-ink-muted');
  });

  it('drops anything falsy, so a conditional class is safe', () => {
    expect(cn('a', false && 'b', undefined, null, 'c')).toBe('a c');
  });
});

describe('initials', () => {
  it('takes at most two letters, in uppercase', () => {
    expect(initials('Dana Whitfield')).toBe('DW');
    expect(initials('priya raman')).toBe('PR');
    expect(initials('Ravi Chandrasekaran Kumar')).toBe('RC');
    expect(initials('Cher')).toBe('C');
  });

  it('never returns an empty label', () => {
    expect(initials(null)).toBe('?');
    expect(initials(undefined)).toBe('?');
    expect(initials('')).toBe('?');
    expect(initials('   ')).toBe('?');
  });
});

describe('hueFor', () => {
  it('gives the same person the same colour every time', () => {
    expect(hueFor('Dana Whitfield')).toBe(hueFor('Dana Whitfield'));
  });

  it('stays inside the colour wheel', () => {
    for (const seed of ['a', 'Dana', 'a much longer name than that one', '123', '']) {
      const hue = hueFor(seed);
      expect(hue).toBeGreaterThanOrEqual(0);
      expect(hue).toBeLessThan(360);
    }
  });

  it('separates different people', () => {
    expect(hueFor('Dana Whitfield')).not.toBe(hueFor('Priya Raman'));
  });
});

describe('groupBy', () => {
  it('collects items under the key they return', () => {
    const rows = [
      { channel: 'web', id: 1 },
      { channel: 'email', id: 2 },
      { channel: 'web', id: 3 },
    ];
    const grouped = groupBy(rows, (row) => row.channel as 'web' | 'email');
    expect(Object.keys(grouped).sort()).toEqual(['email', 'web']);
    expect(grouped.web.map((row) => row.id)).toEqual([1, 3]);
    expect(grouped.email.map((row) => row.id)).toEqual([2]);
  });

  it('returns nothing for nothing', () => {
    expect(groupBy([], () => 'x' as const)).toEqual({});
  });
});
