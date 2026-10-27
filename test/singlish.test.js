// node --test
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { parseHeadlines, buildPrompt, WORDS, sgtDate, sgtLong, pickWordForDate, findWord, parseContent, fallbackContent, buildPhotoCaption, buildBodyMessage, wordPool } from '../singlish.js';

test('sgtDate rolls over at Singapore midnight, not UTC midnight', () => {
  assert.equal(sgtDate(new Date('2026-10-27T15:59:00Z')), '2026-10-27'); // 23:59 SGT
  assert.equal(sgtDate(new Date('2026-10-27T16:01:00Z')), '2026-10-28'); // 00:01 SGT, the daily post time
});

test('sgtLong matches the old "%A, %d %b %Y" format', () => {
  assert.equal(sgtLong(new Date('2026-10-27T16:01:00Z')), 'Wednesday, 28 Oct 2026');
});

test('word of the day is stable for a date, varies across dates, and skips nsfw by default', () => {
  assert.equal(pickWordForDate('2026-10-28').word, pickWordForDate('2026-10-28').word);
  const week = new Set(['01', '02', '03', '04', '05', '06', '07'].map((d) => pickWordForDate(`2026-11-${d}`).word));
  assert.ok(week.size > 3);
  for (let d = 1; d <= 28; d++) assert.ok(!pickWordForDate(`2026-02-${String(d).padStart(2, '0')}`).nsfw);
  assert.equal(wordPool(false).length, WORDS.length - WORDS.filter((w) => w.nsfw).length);
});

test('findWord matches exact first, then substring', () => {
  assert.equal(findWord('LAH').word, 'lah');
  assert.ok(findWord('alama').word.includes('alama'));
  assert.equal(findWord('zzzz-not-a-word'), undefined);
});

test('parseContent handles fences and stray text, and rejects junk', () => {
  const json = '{"telegram_caption":"hi","examples":["a"]}';
  assert.equal(parseContent('```json\n' + json + '\n```').telegram_caption, 'hi');
  assert.equal(parseContent('Here you go: ' + json).telegram_caption, 'hi');
  assert.equal(parseContent('no json here'), null);
  assert.equal(parseContent('{"other":1}'), null);
});

test('photo caption stays under Telegram\'s 1024-char limit for every word', () => {
  for (const w of WORDS) assert.ok(buildPhotoCaption(w, 'Wednesday, 28 Oct 2026').length <= 1024, w.word);
});

test('body message carries examples, news and fun fact', () => {
  const body = buildBodyMessage({ ...fallbackContent(WORDS[0]), news_headline: 'News', news_source: 'CNA' });
  assert.match(body, /▸ _I feel so lah today lah!_/);
  assert.match(body, /📰 \*Referenced:\* News/);
  assert.match(body, /💡 \*Fun Fact:\*/);
});

test('parseHeadlines keeps recent items, decodes entities and CDATA', () => {
  const now = new Date('2026-10-27T10:00:00Z');
  const xml = `<rss><item><title><![CDATA[New MRT line &amp; bus routes]]></title><pubDate>Mon, 26 Oct 2026 08:00:00 +0800</pubDate></item>
    <item><title>Old story</title><pubDate>Mon, 05 Oct 2026 08:00:00 +0800</pubDate></item></rss>`;
  const items = parseHeadlines(xml, 'ST', now);
  assert.deepEqual(items.map((i) => i.title), ['New MRT line & bus routes']);
});

test('prompt lists the headlines instead of asking for web search', () => {
  const p = buildPrompt(WORDS[0], [{ title: 'MRT line opens', source: 'CNA' }]);
  assert.match(p, /MRT line opens \(CNA\)/);
  assert.doesNotMatch(p, /Google Search/);
});
