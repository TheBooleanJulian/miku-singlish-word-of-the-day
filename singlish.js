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

export function buildPrompt(entry) {
  return `You are Hatsune Miku — the iconic virtual vocaloid idol — fully fluent in Singlish after living in Singapore long enough to be a local.

Today's Singlish Word of the Day is: **${entry.word}**
Meaning: ${entry.meaning}

Tasks:
1. Use Google Search to find 1-2 RECENT Singapore news stories from the past 7 days.
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

// Gemini REST call with Google Search grounding. Returns parsed content, or the fallback on any failure.
export async function generateMikuContent(env, entry, { timeoutMs = 120000 } = {}) {
  const model = env.GEMINI_MODEL || 'gemini-2.5-flash';
  try {
    const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-goog-api-key': env.GEMINI_API_KEY },
      body: JSON.stringify({ contents: [{ parts: [{ text: buildPrompt(entry) }] }], tools: [{ google_search: {} }] }),
      signal: AbortSignal.timeout(timeoutMs)
    });
    if (!res.ok) throw new Error(`Gemini ${res.status}`);
    const data = await res.json();
    const text = (data.candidates?.[0]?.content?.parts || []).map((p) => p.text || '').join('').trim();
    return parseContent(text) || fallbackContent(entry);
  } catch (err) {
    console.error(JSON.stringify({ level: 'warn', msg: 'gemini failed, using fallback', error: String(err.message) }));
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
