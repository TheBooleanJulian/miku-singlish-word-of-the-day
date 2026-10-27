// Word of the day: pick, Gemini content, message formats. Ported from bot.py; the prompt and the
// Telegram copy are unchanged. Messages use Telegram's legacy Markdown, as before.
import WORDS from './words.json' with { type: 'json' };

export const TZ = 'Asia/Singapore';
export { WORDS };

// Singapore calendar date "YYYY-MM-DD". (bot.py used date.today() on a UTC server, so a 00:01 SGT post
// would have picked the previous day's word.)
export const sgtDate = (now = new Date()) => new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(now);
// "Tuesday, 27 Oct 2026", the format bot.py used (%A, %d %b %Y).
export function sgtLong(now = new Date()) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: TZ, weekday: 'long', day: '2-digit', month: 'short', year: 'numeric' })
    .formatToParts(now).map((x) => [x.type, x.value]));
  return `${p.weekday}, ${p.day} ${p.month} ${p.year}`;
}

export function wordPool(allowNsfw) {
  return allowNsfw ? WORDS : WORDS.filter((w) => !w.nsfw);
}

// FNV-1a over the date: the same word all day, on every isolate, without storing anything.
export function pickWordForDate(date, allowNsfw = false) {
  const pool = wordPool(allowNsfw);
  let h = 0x811c9dc5;
  for (const ch of date) h = Math.imul(h ^ ch.charCodeAt(0), 0x01000193) >>> 0;
  return pool[h % pool.length];
}

export function findWord(query) {
  const q = query.toLowerCase().trim();
  return WORDS.find((w) => w.word.toLowerCase() === q) || WORDS.find((w) => w.word.toLowerCase().includes(q));
}

// Recent Singapore headlines from public RSS (Straits Times, then CNA as backup), so models without web
// search (FreeLLMAPI's free pool) can still ground the post in real news. Never throws.
const FEEDS = [
  ['The Straits Times', 'https://www.straitstimes.com/news/singapore/rss.xml'],
  ['CNA', 'https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=10416']
];

const decode = (s) => s.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1').replace(/&amp;/g, '&').replace(/&#39;|&apos;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').trim();

export function parseHeadlines(xml, source, now = new Date(), limit = 8) {
  const items = [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].map((m) => {
    const title = m[1].match(/<title>([\s\S]*?)<\/title>/)?.[1];
    const date = m[1].match(/<pubDate>([\s\S]*?)<\/pubDate>/)?.[1];
    return { title: title && decode(title), source, at: date ? new Date(decode(date)) : null };
  });
  const weekAgo = now - 7 * 864e5;
  return items.filter((i) => i.title && (!i.at || isNaN(i.at) || i.at >= weekAgo)).slice(0, limit);
}

export async function fetchHeadlines() {
  for (const [source, url] of FEEDS) {
    try {
      const res = await fetch(url, { headers: { 'User-Agent': 'miku-singlish/1.0 (+https://miku-singlish.thebooleanjulian.dev)' }, signal: AbortSignal.timeout(10000) });
      if (!res.ok) continue;
      const items = parseHeadlines(await res.text(), source);
      if (items.length) return items;
    } catch {
      // try the next feed
    }
  }
  return [];
}

export function buildPrompt(entry, headlines = []) {
  const news = headlines.length
    ? `1. Pick 1-2 of these RECENT Singapore news headlines (past 7 days) to reference:\n${headlines.map((h) => `   - ${h.title} (${h.source})`).join('\n')}`
    : '1. Think of a recent, well-known Singapore news story or everyday Singapore moment to reference.';
  return `You are Hatsune Miku — the iconic virtual vocaloid idol — fully fluent in Singlish after living in Singapore long enough to be a local.

Today's Singlish Word of the Day is: **${entry.word}**
Meaning: ${entry.meaning}

Tasks:
${news}
2. Write a punchy Miku-in-Singapore post that:
   - Applies the word to real Singapore news you found
   - Sounds like Miku: cheerful, uses Singlish particles (lah, leh, sia, wah, etc.), references vocaloid/music life naturally
   - Ends with a "🎤 Miku Verdict:" one-liner using the word
3. Generate 3 fresh first-person example sentences as Miku living in Singapore.
   Each must: use the word naturally, be 1 sentence, sound like Miku, reference Singapore life.

Respond ONLY in this exact JSON (no markdown, no fences):
{
  "news_headline": "One sentence summary of the SG news story referenced",
  "news_source": "e.g. CNA, Straits Times, TODAY",
  "telegram_caption": "Full Miku post 180-260 words. Singlish, charming, references the news. Use line breaks. Include Miku Verdict at end.",
  "fun_fact": "One quirky linguistic or cultural fun fact about this Singlish word (1-2 sentences).",
  "examples": ["First person example sentence 1.", "First person example sentence 2.", "First person example sentence 3."]
}`;
}

export function fallbackContent(entry) {
  const { word, meaning } = entry;
  return {
    news_headline: 'Singapore continues to shine as a global city',
    news_source: 'CNA',
    telegram_caption: `Wah, today Miku teach you one very important word sia! ✨\n\n*${word.toUpperCase()}* — ${meaning}\n\nToday I feel very ${word} lah!\n\nSingapore life confirm need this word one lah~ 🎵\n\n🎤 *Miku Verdict:* Very ${word}, 10/10 would ${word} again!`,
    fun_fact: `'${word}' is one of the most versatile words in the Singlish lexicon!`,
    examples: [`I feel so ${word} today lah!`, `Wah, very ${word} sia!`, `This is the most ${word} thing in Singapore!`],
    fallback: true
  };
}

// Generation goes through thebooleanjulian-llm (service binding LLM, use case "singlish-daily"), which routes
// to FreeLLMAPI first and holds every provider key; this Worker holds none. Fallback content on any failure.
export async function generateMikuContent(env, entry, { timeoutMs = 120000 } = {}) {
  try {
    const headlines = await fetchHeadlines();
    const res = await env.LLM.fetch('https://llm/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-TBJ-Service': 'miku-singlish', 'X-TBJ-Use-Case': 'singlish-daily' },
      body: JSON.stringify({ messages: [{ role: 'user', content: buildPrompt(entry, headlines) }], temperature: 0.9 }),
      signal: AbortSignal.timeout(timeoutMs)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(`gateway ${res.status} ${data?.error?.code || ''} trace ${res.headers.get('x-tbj-trace-id') || '-'}`);
    const content = parseContent(data.choices?.[0]?.message?.content);
    if (!content) throw new Error(`unparseable reply from ${data.tbj?.provider} trace ${data.tbj?.trace_id}`);
    return { ...content, provider: data.tbj?.provider };
  } catch (err) {
    console.error(JSON.stringify({ level: 'warn', msg: 'generation failed, using fallback', error: String(err.message) }));
    return fallbackContent(entry);
  }
}

export function parseContent(text) {
  let clean = (text || '').trim();
  if (clean.startsWith('```')) clean = clean.replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '');
  const start = clean.indexOf('{'), end = clean.lastIndexOf('}');
  if (start < 0 || end < start) return null;
  try {
    const c = JSON.parse(clean.slice(start, end + 1));
    return typeof c.telegram_caption === 'string' ? c : null;
  } catch {
    return null;
  }
}

const RULE = '─'.repeat(28);

// Short caption under the photo (Telegram caps captions at 1024 chars).
export function buildPhotoCaption(entry, dateStr) {
  return [
    '🎵 *Miku Singlish word of the day leh?*',
    `_${dateStr}_`,
    RULE,
    '',
    `📖 *${entry.word.toUpperCase()}*`,
    `_${entry.type}_ · /${entry.pronunciation}/`,
    '',
    entry.meaning
  ].join('\n');
}

// Follow-up message: examples, Miku's post, the news it references, fun fact.
export function buildBodyMessage(content) {
  const lines = [...(content.examples || []).slice(0, 3).map((ex) => `▸ _${ex}_`), '', RULE, '', content.telegram_caption || '', ''];
  if (content.news_headline) lines.push(`📰 *Referenced:* ${content.news_headline}`, `_via ${content.news_source || ''}_`, '');
  if (content.fun_fact) lines.push(`💡 *Fun Fact:* ${content.fun_fact}`, '');
  lines.push(RULE, '_Powered by @mikusinglishwordofthedaylehbot · TheBooleanJulian_ 🤖✨');
  return lines.join('\n');
}
