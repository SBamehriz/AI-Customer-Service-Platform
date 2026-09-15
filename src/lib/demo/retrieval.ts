/** Lexical retrieval for demo mode. */

import type { Article } from '../types';

const WORD = /[a-z0-9']+/g;

const STOPWORDS = new Set(
  `a an and are as at be been but by can cant could did do does doesnt for from
   get got had has have how i im in is it its me my no not of on or our so than
   that the their them then there these they this to too very was we were what
   when where which who why will with would you your many much`
    .split(/\s+/)
    .filter(Boolean),
);

const VERB_SUFFIXES = ['ingly', 'edly', 'ing', 'ied', 'ed', 'ly'];
const ES_PLURAL_ENDINGS = ['ses', 'xes', 'zes', 'ches', 'shes'];

/** Below this a word is too short to strip safely. */
const STEM_FLOOR = 5;

/** Reduce a word to a rough root, so tenses and plurals match. */
export function stem(word: string): string {
  if (word.length < STEM_FLOOR) return word;

  if (word.endsWith('ies') && word.length > 4) return `${word.slice(0, -3)}y`;
  let base = word;
  if (ES_PLURAL_ENDINGS.some((ending) => base.endsWith(ending))) {
    base = base.slice(0, -2);
  } else if (base.endsWith('s') && !base.endsWith('ss')) {
    base = base.slice(0, -1);
  }
  if (base.length < STEM_FLOOR) return base;

  for (const suffix of VERB_SUFFIXES) {
    if (base.endsWith(suffix) && base.length - suffix.length >= 3) {
      let root = base.slice(0, -suffix.length);
      // A doubled consonant from shipped or planning collapses.
      if (root.length > 3 && root.at(-1) === root.at(-2) && !'aeiou'.includes(root.at(-1)!)) {
        root = root.slice(0, -1);
      }
      return root;
    }
  }

  // A trailing silent e goes last, so arrive and arrived both end at arriv.
  if (base.length >= STEM_FLOOR && base.endsWith('e')) return base.slice(0, -1);
  return base;
}

export function tokenize(text: string): string[] {
  return (text.toLowerCase().match(WORD) ?? [])
    .filter((word) => !STOPWORDS.has(word))
    .map(stem);
}

function documentText(article: Article): string {
  // Title counted twice, so a match there outranks one in the body alone.
  return [
    article.title,
    article.title,
    article.summary ?? '',
    (article.tags ?? []).join(' '),
    article.category,
    article.body,
  ].join(' ');
}

export function bm25(query: string, documents: string[], k1 = 1.5, b = 0.75): number[] {
  const terms = tokenize(query);
  if (terms.length === 0 || documents.length === 0) return documents.map(() => 0);

  const tokenized = documents.map(tokenize);
  const lengths = tokenized.map((doc) => doc.length || 1);
  const avgLength = lengths.reduce((sum, value) => sum + value, 0) / lengths.length;

  const frequencies = tokenized.map((doc) => {
    const counts = new Map<string, number>();
    for (const word of doc) counts.set(word, (counts.get(word) ?? 0) + 1);
    return counts;
  });

  const unique = [...new Set(terms)];
  const documentFrequency = new Map<string, number>();
  for (const term of unique) {
    documentFrequency.set(term, frequencies.filter((counts) => counts.has(term)).length);
  }

  const total = documents.length;
  return frequencies.map((counts, index) => {
    let score = 0;
    for (const term of terms) {
      const frequency = counts.get(term) ?? 0;
      if (!frequency) continue;
      const nq = documentFrequency.get(term) ?? 0;
      const idf = Math.log(1 + (total - nq + 0.5) / (nq + 0.5));
      const norm = frequency * (k1 + 1);
      const denom = frequency + k1 * (1 - b + (b * lengths[index]) / avgLength);
      score += (idf * norm) / denom;
    }
    return score;
  });
}

export interface Hit {
  article: Article;
  /** Rank within this result set, normalised so the best hit is always 1. */
  score: number;
  /** Absolute match quality, comparable across searches. See coverageScores. */
  coverage: number;
}

/** Matched rarity at which coverage reaches one half. */
const COVERAGE_MIDPOINT = 2.2;

/** The least a matched content word can be worth, for small knowledge bases. */
const MIN_TERM_WEIGHT = 1.2;

/** How much of the question each document actually answers, from 0 to 1. */
function coverageScores(query: string, documents: string[]): number[] {
  const terms = [...new Set(tokenize(query))];
  if (terms.length === 0 || documents.length === 0) return documents.map(() => 0);

  const present = documents.map((doc) => new Set(tokenize(doc)));
  const total = documents.length;
  const weights = new Map<string, number>();
  for (const term of terms) {
    const seen = present.filter((words) => words.has(term)).length;
    const idf = Math.log(1 + (total - seen + 0.5) / (seen + 0.5));
    // Floored, because idf collapses towards zero on a small corpus.
    weights.set(term, Math.max(idf, MIN_TERM_WEIGHT));
  }

  return present.map((words) => {
    let matched = 0;
    for (const term of terms) if (words.has(term)) matched += weights.get(term) ?? 0;
    return Number((matched / (matched + COVERAGE_MIDPOINT)).toFixed(4));
  });
}

export function searchArticles(
  articles: Article[],
  query: string,
  { limit = 5, includeInternal = true, minScore = 0.05, minCoverage = 0.15 } = {},
): Hit[] {
  const trimmed = query.trim();
  if (!trimmed) return [];

  const pool = articles.filter(
    (article) =>
      article.status === 'published' && (includeInternal || article.visibility === 'public'),
  );
  if (pool.length === 0) return [];

  const documents = pool.map(documentText);
  const raw = bm25(trimmed, documents);
  const peak = Math.max(...raw, 0);
  if (peak <= 0) return [];

  const coverage = coverageScores(trimmed, documents);
  return pool
    .map((article, index) => ({
      article,
      score: Number((raw[index] / peak).toFixed(4)),
      coverage: coverage[index],
    }))
    .filter((hit) => hit.score >= minScore && hit.coverage >= minCoverage)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}

/** A window of the article body around the first matching term. */
export function excerpt(article: Article, query: string, length = 240): string {
  const body = article.body.split(/\s+/).join(' ');
  if (!body) return article.summary ?? '';

  const lowered = body.toLowerCase();
  let position = -1;
  for (const term of tokenize(query)) {
    position = lowered.indexOf(term);
    if (position !== -1) break;
  }

  // A match inside the first window reads best from the top of the article,
  // rather than shaving a word or two off the opening sentence to centre it.
  const from = position === -1 || position < length
    ? 0
    : Math.max(0, position - Math.floor(length / 3));
  return windowAround(body, from, length);
}

/** How far back to look for a sentence start before cutting on a word instead. */
const SENTENCE_LOOKBACK = 160;

/** Cut a readable window out of a body of text. */
function windowAround(body: string, from: number, length: number): string {
  let start = from;
  if (start > 0) {
    const sentence = sentenceStart(body, start);
    if (sentence !== null) {
      start = sentence;
    } else {
      const space = body.indexOf(' ', start);
      start = space === -1 ? start : space + 1;
    }
  }

  let whole = false;
  let end = start + length;
  if (end < body.length) {
    const sentence = sentenceEnd(body, start, end);
    if (sentence !== null) {
      end = sentence;
      whole = true;
    } else {
      const space = body.lastIndexOf(' ', end - 1);
      end = space <= start ? end : space;
    }
  }

  const prefix = start > 0 ? '...' : '';
  const suffix = end < body.length && !whole ? '...' : '';
  return `${prefix}${body.slice(start, end).trim()}${suffix}`;
}

/** Index just after the nearest sentence end before `position`, when close. */
function sentenceStart(body: string, position: number): number | null {
  const floor = Math.max(0, position - SENTENCE_LOOKBACK);
  const window = body.slice(floor, position);
  const best = Math.max(...['. ', '! ', '? '].map((mark) => window.lastIndexOf(mark)));
  return best === -1 ? null : floor + best + 2;
}

/** Index just after the last sentence that finishes inside the window. */
function sentenceEnd(body: string, start: number, position: number): number | null {
  const floor = Math.max(start, position - SENTENCE_LOOKBACK);
  const window = body.slice(floor, position);
  const best = Math.max(...['. ', '! ', '? '].map((mark) => window.lastIndexOf(mark)));
  if (best === -1) {
    if (position >= body.length && ['.', '!', '?'].includes(body.slice(position - 1, position))) {
      return position;
    }
    return null;
  }
  return floor + best + 1;
}
