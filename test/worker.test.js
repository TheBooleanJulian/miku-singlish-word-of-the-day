// node --test   worker.js against fake Telegram (fetch) and fake Postgres (env.SQL).
import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

import worker from '../worker.js';

let sent, realFetch;

function fakeDb() {
  const chats = new Map();
  const posts = new Map();
  const sql = async (strings, ...v) => {
    const q = strings.join('?').replace(/\s+/g, ' ').trim().toLowerCase();
    if (q.startsWith('insert into miku_singlish.chats')) { const had = chats.has(v[0]); chats.set(v[0], v[1] ?? chats.get(v[0]) ?? null); return [{ inserted: !had }]; }
    if (q.startsWith('delete from miku_singlish.chats')) return chats.delete(v[0]) ? [{ chat_id: v[0] }] : [];
    if (q.includes('count(*)')) return [{ n: chats.size }];
    if (q.startsWith('select chat_id')) return [...chats.keys()].map((chat_id) => ({ chat_id }));
    if (q.startsWith('select word, content')) return posts.has(v[0]) ? [posts.get(v[0])] : [];
    if (q.startsWith('insert into miku_singlish.daily_posts')) { if (!posts.has(v[0])) posts.set(v[0], { word: v[1], content: v[2] }); return []; }
    throw new Error('unexpected query: ' + q);
  };
  sql.json = (x) => x;
  return { sql, chats, posts };
}

// Stands in for the thebooleanjulian-llm service binding.
let llmCalls = [];
async function fakeLlm(url, init) {
  if (String(url).endsWith('/healthz')) return Response.json({ providers: { freellmapi: 'configured' } });
  const body = JSON.parse(init.body);
  llmCalls.push({ headers: init.headers, prompt: body.messages[0].content });
  const content = { telegram_caption: 'Wah Miku post lah', examples: ['e1', 'e2', 'e3'], news_headline: 'N', news_source: 'CNA', fun_fact: 'F' };
  return Response.json({ choices: [{ message: { content: JSON.stringify(content) } }], tbj: { provider: 'freellmapi', trace_id: 't' } });
}

const ctx = () => { const p = []; return { waitUntil: (x) => p.push(x), done: () => Promise.all(p) }; };

beforeEach(() => {
  sent = [];
  realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    url = String(url);
    if (url.includes('straitstimes.com') || url.includes('channelnewsasia.com')) {
      return new Response('<rss><channel><item><title>MRT line opens</title><pubDate>' + new Date().toUTCString() + '</pubDate></item></channel></rss>');
    }
    const method = url.split('/').pop();
    const body = JSON.parse(init.body);
    sent.push({ method, ...body });
    return Response.json({ ok: true, result: { message_id: sent.length } });
  };
});
afterEach(() => { globalThis.fetch = realFetch; });

function env(db = fakeDb()) {
  return {
    SQL: db.sql, BOT_TOKEN: '1:x', WEBHOOK_SECRET: 's3cret', GEMINI_API_KEY: 'k', PUBLIC_URL: 'https://miku-singlish.thebooleanjulian.dev',
    BOT_USERNAME: 'mikusinglishwordofthedaylehbot',
    ASSETS: { fetch: () => new Response('asset') },
    SELF: { fetch: (url, init) => worker.fetch(new Request('https://self/internal/batch', init), env.current, ctx()) },
    LLM: { fetch: fakeLlm }
  };
}

async function webhook(e, update) {
  const c = ctx();
  const res = await worker.fetch(new Request('https://x/webhook', { method: 'POST', body: JSON.stringify(update), headers: { 'X-Telegram-Bot-Api-Secret-Token': 's3cret' } }), e, c);
  await c.done();
  return res;
}

test('/start subscribes the chat and replies with the 12:01am schedule', async () => {
  const db = fakeDb();
  const e = env(db);
  await webhook(e, { update_id: 1, message: { text: '/start', chat: { id: 42 } } });
  assert.ok(db.chats.has('42'));
  assert.match(sent[0].text, /12:01am SGT/);
});

test('adding the bot to a channel auto-subscribes it; removing unsubscribes', async () => {
  const db = fakeDb();
  const e = env(db);
  await webhook(e, { update_id: 2, my_chat_member: { chat: { id: -100, title: 'Ch' }, new_chat_member: { status: 'administrator' } } });
  assert.equal(db.chats.get('-100'), 'Ch');
  await webhook(e, { update_id: 3, my_chat_member: { chat: { id: -100 }, new_chat_member: { status: 'kicked' } } });
  assert.ok(!db.chats.has('-100'));
});

test('/today posts photo + body and stores the day\'s post once', async () => {
  const db = fakeDb();
  const e = env(db);
  await webhook(e, { update_id: 4, message: { text: '/today', chat: { id: 7 } } });
  const methods = sent.map((s) => s.method);
  assert.deepEqual(methods.filter((m) => m !== 'deleteMessage'), ['sendMessage', 'sendPhoto', 'sendMessage']);
  assert.match(sent.find((s) => s.method === 'sendPhoto').photo, /\/sgmigu\.png$/);
  assert.equal(db.posts.size, 1);
});

test('daily cron generates once and reaches every chat in batches of 20', async () => {
  const db = fakeDb();
  for (let i = 0; i < 45; i++) db.chats.set(String(-1000 - i), null);
  const e = env(db);
  env.current = e;
  llmCalls = [];
  await worker.scheduled({ cron: '1 16 * * *' }, e, ctx());
  assert.equal(llmCalls.length, 1);
  assert.equal(llmCalls[0].headers['X-TBJ-Use-Case'], 'singlish-daily');
  assert.match(llmCalls[0].prompt, /MRT line opens/);
  assert.equal(sent.filter((s) => s.method === 'sendPhoto').length, 45);
  assert.equal(sent.filter((s) => s.method === 'sendMessage').length, 45);
});

test('/internal/batch and /webhook refuse without the secret', async () => {
  const e = env();
  assert.equal((await worker.fetch(new Request('https://x/internal/batch', { method: 'POST', body: '{}' }), e, ctx())).status, 403);
  assert.equal((await worker.fetch(new Request('https://x/webhook', { method: 'POST', body: '{}' }), e, ctx())).status, 403);
});

test('/healthz reports postgres ok and the chat count', async () => {
  const db = fakeDb();
  db.chats.set('1', null);
  const body = await (await worker.fetch(new Request('https://x/healthz'), env(db), ctx())).json();
  assert.equal(body.status, 'pass');
  assert.equal(body.chats, 1);
});
