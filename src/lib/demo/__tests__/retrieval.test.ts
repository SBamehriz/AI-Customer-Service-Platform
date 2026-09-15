import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { excerpt, searchArticles, stem, tokenize } from '../retrieval';
import type { Article } from '../../types';

function article(partial: Partial<Article> & { title: string; body: string }): Article {
  return {
    id: partial.title.toLowerCase().replace(/\s+/g, '-'),
    workspaceId: 'ws',
    title: partial.title,
    body: partial.body,
    summary: partial.summary ?? '',
    category: partial.category ?? 'General',
    tags: partial.tags ?? [],
    status: 'published',
    visibility: 'public',
    authorName: 'Test',
    version: 1,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  } as Article;
}

const SHOP: Article[] = [
  article({
    title: 'Returns and refunds',
    category: 'Policies',
    body:
      'You can return anything within 30 days of delivery for a full refund. Items need to be ' +
      'unworn and in their original packaging. Start a return from your account, print the ' +
      'prepaid label and drop the parcel at any post office.',
  }),
  article({
    title: 'Delivery times and shipping costs',
    category: 'Policies',
    body:
      'Standard delivery takes three to five working days and is free on orders over fifty ' +
      'pounds. Express delivery arrives the next working day. We ship across the United Kingdom ' +
      'and Europe.',
  }),
  article({
    title: 'Payment methods we accept',
    category: 'Orders',
    body:
      'We take Visa, Mastercard, American Express, Apple Pay and PayPal. Payment is taken when ' +
      'the order ships, not when you place it, so a pending charge on your card is only a hold.',
  }),
];

describe('stem', () => {
  it('matches a question to an article across tense and plural', () => {
    expect(stem('returns')).toBe(stem('return'));
    expect(stem('shipping')).toBe(stem('shipped'));
    expect(stem('arrived')).toBe(stem('arrive'));
    expect(stem('deliveries')).toBe(stem('delivery'));
  });

  it('leaves short words alone rather than mangling them', () => {
    expect(stem('gas')).toBe('gas');
    expect(stem('bed')).toBe('bed');
  });
});

describe('tokenize', () => {
  it('drops the words that carry no meaning', () => {
    expect(tokenize('How do I return it')).not.toContain('how');
    expect(tokenize('How do I return it')).not.toContain('do');
  });

  it('drops the quantity fillers, the same as the backend', () => {
    const terms = tokenize('How much does delivery cost');
    expect(terms).not.toContain('much');
    expect(terms).not.toContain('many');
    expect(terms).toContain('cost');
  });
});

describe('searchArticles', () => {
  it('puts the article that answers the question first', () => {
    const cases: [string, string][] = [
      ['How long do I have to return something', 'Returns and refunds'],
      ['What is your refund policy', 'Returns and refunds'],
      ['How much does delivery cost', 'Delivery times and shipping costs'],
      ['Do you ship to Europe', 'Delivery times and shipping costs'],
      ['Do you take PayPal', 'Payment methods we accept'],
      ['when will my card be charged', 'Payment methods we accept'],
    ];
    for (const [question, expected] of cases) {
      const hits = searchArticles(SHOP, question);
      expect(hits.length, question).toBeGreaterThan(0);
      expect(hits[0].article.title, question).toBe(expected);
    }
  });

  it('gives a question nothing covers no usable hit', () => {
    const hits = searchArticles(SHOP, 'Can you refinance my houseboat mortgage');
    const best = hits[0]?.coverage ?? 0;
    expect(best).toBeLessThan(0.3);
  });

  it('scores coverage high enough for a covered question to be answered', () => {
    // 0.3 is the shipping default for aiSuggestThreshold.
    const hits = searchArticles(SHOP, 'What is your returns policy');
    expect(hits[0].coverage).toBeGreaterThanOrEqual(0.3);
  });

  it('normalises the top hit to one, so rank and quality stay separate', () => {
    const hits = searchArticles(SHOP, 'delivery');
    expect(hits[0].score).toBeCloseTo(1, 5);
  });
});

describe('excerpt', () => {
  it('starts at the top of the article rather than mid sentence', () => {
    const quoted = excerpt(SHOP[0], 'Can I get a refund', 240);
    expect(quoted.startsWith('...')).toBe(false);
    expect(quoted.startsWith('You can return anything')).toBe(true);
  });

  it('marks a passage taken from further in', () => {
    const long = article({
      title: 'Long article',
      body:
        'The opening paragraph talks about something else entirely and runs on for a good while ' +
        'so that the interesting part is well past the first window of text that would be shown. ' +
        'It keeps going here as well, still on the first subject, still not what was asked about. ' +
        'Only now do we mention that a replacement is sent at no cost when a parcel is lost.',
    });
    const quoted = excerpt(long, 'replacement', 120);
    expect(quoted.startsWith('...')).toBe(true);
  });
});

describe('parity with the backend', () => {
  const backend = readFileSync('backend/app/ai/retrieval.py', 'utf8');
  const demo = readFileSync('src/lib/demo/retrieval.ts', 'utf8');

  function pythonWords(): Set<string> {
    const block = backend.match(/_STOPWORDS = frozenset\(\s*"""([\s\S]*?)"""/);
    return new Set((block?.[1] ?? '').split(/\s+/).filter(Boolean));
  }

  function tsWords(): Set<string> {
    const block = demo.match(/STOPWORDS = new Set\(\s*`([\s\S]*?)`/);
    return new Set((block?.[1] ?? '').split(/\s+/).filter(Boolean));
  }

  it('uses the same stopword list', () => {
    const a = pythonWords();
    const b = tsWords();
    expect(a.size).toBeGreaterThan(50);
    expect([...a].filter((w) => !b.has(w))).toEqual([]);
    expect([...b].filter((w) => !a.has(w))).toEqual([]);
  });

  it('uses the same retrieval constants', () => {
    const pairs: [RegExp, RegExp][] = [
      [/_COVERAGE_MIDPOINT = ([\d.]+)/, /COVERAGE_MIDPOINT = ([\d.]+)/],
      [/_MIN_TERM_WEIGHT = ([\d.]+)/, /MIN_TERM_WEIGHT = ([\d.]+)/],
      [/_STEM_FLOOR = (\d+)/, /STEM_FLOOR = (\d+)/],
    ];
    for (const [py, ts] of pairs) {
      const a = backend.match(py)?.[1];
      const b = demo.match(ts)?.[1];
      expect(a, String(py)).toBeDefined();
      expect(b, String(ts)).toBeDefined();
      expect(Number(b), String(py)).toBe(Number(a));
    }
  });
});
