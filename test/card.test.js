// node --test   The word card: font metrics, wrapping, layout, and a real PNG render through resvg.
import { test, before } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { initWasm } from '@resvg/resvg-wasm';

import { parseFont, wrap, fit, buildCardSvg, renderPng, cardDates, pngSize } from '../card.js';
import { WORDS } from '../singlish.js';

const FILES = { sans: 'DejaVuSans.ttf', sansBold: 'DejaVuSans-Bold.ttf', mono: 'DejaVuSansMono.ttf', monoBold: 'DejaVuSansMono-Bold.ttf' };
const buffers = Object.values(FILES).map((f) => new Uint8Array(readFileSync(new URL(`../assets/fonts/${f}`, import.meta.url))));
const fonts = Object.fromEntries(Object.keys(FILES).map((k, i) => [k, parseFont(buffers[i])]));
const miku = new Uint8Array(readFileSync(new URL('../assets/sgmigu.png', import.meta.url)));

const card = (entry, examples = ['Wah, the chili crab so shiok!', 'Two.', 'Three.']) =>
  ({ word: entry.word, type: entry.type, pronunciation: entry.pronunciation, meaning: entry.meaning, examples, ...cardDates('2026-08-31') });

before(() => initWasm(readFileSync(new URL('../node_modules/@resvg/resvg-wasm/index_bg.wasm', import.meta.url))));

test('font metrics match DejaVu (Pillow measured the same strings)', () => {
  assert.equal(fonts.mono.width('abcd', 10), 4 * 1233 / 2048 * 10);   // monospace advance 1233/2048 em
  assert.ok(Math.abs(fonts.sansBold.ascent - 1901 / 2048) < 1e-9);
  assert.ok(fonts.sans.width('W', 20) > fonts.sans.width('i', 20));
});

test('wrap matches card_generator._wrap and fit adds an ellipsis', () => {
  const lines = wrap(fonts.sans, "An exclamation of admiration, surprise, or impressed disbelief. The Singaporean 'wow'.", 20, 644);
  assert.deepEqual(lines, ['An exclamation of admiration, surprise, or impressed disbelief.', "The Singaporean 'wow'."]);
  assert.ok(fit(fonts.sans, 'x'.repeat(200), 20, 100).endsWith('…'));
  assert.ok(fonts.sans.width(fit(fonts.sans, 'x'.repeat(200), 20, 100), 20) <= 100);
});

test('card dates follow bot.py (%d %b %Y, %A), "Sep" not "Sept"', () => {
  assert.deepEqual(cardDates('2026-09-02'), { dateStr: '02 Sep 2026', dayStr: 'Wednesday' });
});

test('SVG escapes text and keeps long words inside the text panel', () => {
  const svg = buildCardSvg(card({ word: 'a < b & "c"', type: 'phrase', pronunciation: 'x', meaning: 'm' }), fonts, pngSize(miku));
  assert.match(svg, /A &lt; B &amp; &quot;C&quot;/);
  const long = buildCardSvg(card({ word: 'kan ni na bu chao chee bye', type: 'interjection', pronunciation: 'x', meaning: 'm' }), fonts, pngSize(miku));
  const size = Number(long.match(/font-size="(\d+)"[^>]*>KAN NI NA/)[1]);
  assert.ok(size < 74 && fonts.sansBold.width('KAN NI NA BU CHAO CHEE BYE', size) <= 644);
});

test('renders a 1080×640 PNG with the figure, for curated and imported words', () => {
  for (const entry of [WORDS.find((w) => w.word === 'wah'), WORDS.find((w) => w.source)]) {
    const png = renderPng(buildCardSvg(card(entry), fonts, pngSize(miku)), buffers, miku);
    assert.deepEqual([...png.subarray(1, 4)], [...Buffer.from('PNG')]);
    assert.deepEqual(pngSize(png), { width: 1080, height: 640 });
    assert.ok(png.length > 100_000, 'too small: the Migu image probably did not load');
  }
});
