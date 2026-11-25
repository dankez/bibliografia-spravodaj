import assert from 'node:assert/strict';
import test from 'node:test';

import { makeSearchSnippet, normalizeSearchText } from '../src/utils/search-snippets.js';

test('finds terms without accents while preserving the original text', () => {
  const text = `${'Úvod '.repeat(60)}Jaskyňa Domica je významná. ${'Záver '.repeat(60)}`;
  const snippet = makeSearchSnippet(text, 'jaskyna');
  assert.match(snippet, /Jaskyňa Domica/);
  assert.ok(snippet.startsWith('… '));
  assert.ok(snippet.endsWith(' …'));
  assert.equal(normalizeSearchText('  JASKYŇA  '), 'jaskyna');
});

test('handles decomposed accents and missing matches', () => {
  const text = `${'a\u0301'.repeat(150)} koniec`;
  assert.match(makeSearchSnippet(text, 'koniec'), /koniec/);
  assert.equal(makeSearchSnippet('Krátky text', 'neznáme'), 'Krátky text');
  assert.equal(makeSearchSnippet('', 'test'), '');
});
