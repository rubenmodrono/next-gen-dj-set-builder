import assert from 'node:assert/strict';
import { BUILTIN_PROXY, proxyRequestUrl } from '../src/sources/beatport';
import { test } from './helpers';

const CHART = 'https://www.beatport.com/genre/progressive-house/15/top-100';

test('beatport: sin proxy propio usa el lector integrado de la misma web', () => {
  assert.equal(proxyRequestUrl(CHART, ''), `${BUILTIN_PROXY}?url=${encodeURIComponent(CHART)}`);
  assert.equal(proxyRequestUrl(CHART, '   '), `${BUILTIN_PROXY}?url=${encodeURIComponent(CHART)}`);
});

test('beatport: un proxy propio tiene prioridad y respeta parámetros previos', () => {
  assert.equal(proxyRequestUrl(CHART, 'https://p.example.workers.dev'), `https://p.example.workers.dev?url=${encodeURIComponent(CHART)}`);
  assert.equal(proxyRequestUrl(CHART, 'https://p.example/x?k=1'), `https://p.example/x?k=1&url=${encodeURIComponent(CHART)}`);
});
