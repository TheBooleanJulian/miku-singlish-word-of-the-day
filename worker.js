// Miku's Singlish Word of the Day on Cloudflare Workers (replaces bot.py, which polled on Zeabur).
//
//   POST /webhook          Telegram updates (secret_token checked): commands + auto-subscribe on my_chat_member
//   cron 1 16 * * *        00:01 SGT: generate today's post once (Gemini + Google Search), store it, broadcast
//   POST /internal/batch   one broadcast batch, called through the SELF service binding (each batch is its own
//                          invocation, so the free plan's 50-subrequest limit applies per 20 chats, not per run)
//   GET  /status /healthz  bot-core status page and health JSON
//
// Data: schema miku_singlish in the shared Supabase project, via Hyperdrive (thebooleanjulian-bot-core/db).
// Commands and copy follow bot.py; the daily time moved from 06:00 to 00:01 SGT.
import { log, api, verifyWebhook, parseCommand, healthz, statusPage, serveBrand } from 'thebooleanjulian-bot-core';
import { withDb } from 'thebooleanjulian-bot-core/db';
import { WORDS, sgtDate, sgtLong, pickWordForDate, findWord, generateMikuContent, buildPhotoCaption, buildBodyMessage } from './singlish.js';

const BATCH = 20;
const DAILY_TIME = '00:01';

// ── storage ────────────────────────────────────────────────────────────────
const q = (env, fn) => withDb(env, null, fn);
const db = {
  subscribe: async (env, id, title = null) =>
    (await q(env, (sql) => sql`insert into miku_singlish.chats (chat_id, title) values (${String(id)}, ${title}) on conflict (chat_id) do update set title = coalesce(excluded.title, miku_singlish.chats.title) returning (xmax = 0) as inserted`))[0].inserted,
  unsubscribe: async (env, id) => (await q(env, (sql) => sql`delete from miku_singlish.chats where chat_id = ${String(id)} returning chat_id`)).length > 0,
  count: async (env) => (await q(env, (sql) => sql`select count(*)::int as n from miku_singlish.chats`))[0].n,
  all: async (env) => (await q(env, (sql) => sql`select chat_id from miku_singlish.chats order by added_at`)).map((r) => r.chat_id),
  getPost: async (env, date) => (await q(env, (sql) => sql`select word, content from miku_singlish.daily_posts where post_date = ${date}`))[0] || null,
  savePost: async (env, date, word, content) =>
    q(env, (sql) => sql`insert into miku_singlish.daily_posts (post_date, word, content) values (${date}, ${word}, ${sql.json(content)}) on conflict (post_date) do nothing`)
};

const allowNsfw = (env) => ['1', 'true', 'yes'].includes(String(env.ALLOW_NSFW || '0').toLowerCase());

// Today's post, generated at most once per Singapore day (the cron does it at 00:01; /today only if that failed).
async function todaysPost(env, { timeoutMs } = {}) {
  const date = sgtDate();
  const existing = await db.getPost(env, date);
  if (existing) return { date, entry: WORDS.find((w) => w.word === existing.word) || pickWordForDate(date, allowNsfw(env)), content: existing.content };
  const entry = pickWordForDate(date, allowNsfw(env));
  const content = await generateMikuContent(env, entry, { timeoutMs });
  if (!content.fallback) await db.savePost(env, date, entry.word, content);
  return { date, entry, content };
}

// ── telegram helpers ───────────────────────────────────────────────────────
// Legacy Markdown breaks on stray _ or * in AI text; retry the same message as plain text rather than drop it.
async function sendMd(env, method, params) {
  try {
    return await api(env, method, { ...params, parse_mode: 'Markdown' });
  } catch (err) {
    if (err.status === 400 && /parse entities/i.test(err.message)) return api(env, method, params);
    throw err;
  }
}
const say = (env, chatId, text) => sendMd(env, 'sendMessage', { chat_id: chatId, text });

async function postToChat(env, chatId, post) {
  await sendMd(env, 'sendPhoto', { chat_id: chatId, photo: `${env.PUBLIC_URL}/sgmigu.png`, caption: buildPhotoCaption(post.entry, sgtLong()) });
  await sendMd(env, 'sendMessage', { chat_id: chatId, text: buildBodyMessage(post.content), disable_web_page_preview: true });
}

// ── commands ───────────────────────────────────────────────────────────────
const HELP = (subNote) => `🎵 *Miku's Singlish Word of the Day* 🎵

@mikusinglishwordofthedaylehbot

Aiyoh, Miku is here to teach you Singlish one word at a time lah~

${subNote}*Commands:*
/today — Post today's word now!
/word <word> — Look up a Singlish word
/list — See all words in my vocabulary
/unsubscribe — Stop daily posts here
/debug — Run deployment health check
/help — Show this message again

_Daily post at 12:01am SGT every day! Don't miss ah~ 🎤_`;

async function handleCommand(env, msg, cmd) {
  const chatId = String(msg.chat.id);
  switch (cmd.name) {
    case 'start':
    case 'help': {
      const isNew = await db.subscribe(env, chatId, msg.chat.title || null);
      const note = isNew
        ? `_Steady! I'll send you the word every day at 12:01am SGT lah~ 🎵_\n\n`
        : `_Eh, you already subscribed one leh~ Still sending daily at 12:01am SGT! 🎵_\n\n`;
      return say(env, chatId, HELP(note));
    }
    case 'unsubscribe':
      return (await db.unsubscribe(env, chatId))
        ? api(env, 'sendMessage', { chat_id: chatId, text: "Okayyyy, Miku won't post here anymore lah~ 😢\nUse /start to re-subscribe anytime!" })
        : api(env, 'sendMessage', { chat_id: chatId, text: "Eh, you weren't even subscribed here leh~\nUse /start to subscribe!" });
    case 'today': {
      await db.subscribe(env, chatId, msg.chat.title || null); // as before: /today also subscribes the chat
      const wait = await say(env, chatId, '_Miku is preparing today\'s word… wait ah~ 🎵_');
      try {
        await postToChat(env, chatId, await todaysPost(env, { timeoutMs: 20000 }));
        await api(env, 'deleteMessage', { chat_id: chatId, message_id: wait.message_id }).catch(() => {});
      } catch (err) {
        log.error('/today failed', { error: err.message });
        await api(env, 'editMessageText', { chat_id: chatId, message_id: wait.message_id, text: 'Aiyoh, something broke lah 😭 Try again later ah.' }).catch(() => {});
      }
      return;
    }
    case 'word': {
      if (!cmd.args) return say(env, chatId, 'Eh, you never say which word leh~\nUsage: `/word <singlish_word>`');
      const e = findWord(cmd.args);
      if (!e) return say(env, chatId, `Catch no ball leh — I don't know \`${cmd.args}\` yet lor~\nTry /list to see what I know!`);
      return say(env, chatId, `📖 *${e.word.toUpperCase()}*\n_${e.type}_ · /${e.pronunciation}/\n\n${e.meaning}\n\n_Use /today to see a live post with fresh examples!_`);
    }
    case 'list': {
      const unique = [...new Set(WORDS.map((w) => w.word))].sort();
      const footer = '\n_More coming, steady bom pi pi!_ ✨';
      let cur = `🎵 *My Singlish Vocabulary* (${unique.length} words)\n\n`;
      for (const word of unique) {
        const token = `\`${word}\` • `;
        if (cur.length + token.length + footer.length > 4000) {
          await say(env, chatId, cur.replace(/ • $/, ''));
          cur = '';
        }
        cur += token;
      }
      return say(env, chatId, cur.replace(/ • $/, '') + footer);
    }
    case 'debug': {
      const date = sgtDate();
      const entry = pickWordForDate(date, allowNsfw(env));
      const lines = ['🔧 *Miku Debug Mode* — checking systems lah~\n'];
      lines.push(`${env.BOT_TOKEN && env.GEMINI_API_KEY ? '✅' : '❌'} Secrets: \`BOT_TOKEN\`, \`GEMINI_API_KEY\``);
      lines.push(`✅ Word bank: *${WORDS.length} words* loaded`);
      lines.push(`✅ Today's word (${date}): *${entry.word}*`);
      try {
        const [count, post] = await Promise.all([db.count(env), db.getPost(env, date)]);
        lines.push(`✅ Database: ok · subscribed chats: *${count}*`);
        lines.push(post ? '✅ Today\'s post: generated and stored' : '⏳ Today\'s post: not generated yet');
      } catch (err) {
        lines.push(`❌ Database: \`${err.message.slice(0, 80)}\``);
      }
      lines.push(`✅ Daily post: every day at ${DAILY_TIME} SGT (Cloudflare Cron)`);
      lines.push(`ℹ️ This chat ID: \`${chatId}\``);
      lines.push('\n_Steady bom pi pi, Miku is ready lah!_ 🎤');
      return say(env, chatId, lines.join('\n'));
    }
  }
}

// Bot added to / removed from a group or channel: auto-subscribe / unsubscribe, as bot.py did.
async function handleMembership(env, upd) {
  const chatId = String(upd.chat.id);
  const status = upd.new_chat_member?.status;
  if (status === 'member' || status === 'administrator') {
    await db.subscribe(env, chatId, upd.chat.title || null);
    log.info('auto-subscribed', { chat: upd.chat.title || chatId });
    await say(env, chatId, '🎵 Wah, Miku has arrived lah! I\'ll send Singlish Word of the Day here every 12:01am SGT~\nUse /start to confirm, /unsubscribe to stop.').catch((err) =>
      log.warn('welcome failed', { error: err.message }));
  } else if (status === 'left' || status === 'kicked') {
    await db.unsubscribe(env, chatId);
    log.info('auto-unsubscribed', { chat: upd.chat.title || chatId });
  }
}

async function handleUpdate(update, env) {
  try {
    if (update.my_chat_member) return await handleMembership(env, update.my_chat_member);
    const msg = update.message || update.channel_post;
    const cmd = msg && parseCommand(msg.text, env.BOT_USERNAME);
    if (cmd) await handleCommand(env, msg, cmd);
  } catch (err) {
    log.error('update failed', { update_id: update.update_id, error: err.message });
  }
}

// ── daily broadcast ────────────────────────────────────────────────────────
// Unreachable chats (bot removed, chat deleted) are dropped, as bot.py did.
async function sendBatch(env, chatIds, post) {
  let ok = 0;
  for (const chatId of chatIds) {
    try {
      await postToChat(env, chatId, post);
      ok++;
    } catch (err) {
      log.error('post failed', { error: err.message });
      if (err.status === 403 || /chat not found|bot was kicked|not a member/i.test(err.message)) await db.unsubscribe(env, chatId);
    }
  }
  return ok;
}

async function broadcast(env) {
  const post = await todaysPost(env);
  const ids = await db.all(env);
  const batches = [];
  for (let i = 0; i < ids.length; i += BATCH) batches.push(ids.slice(i, i + BATCH));
  const results = await Promise.allSettled(batches.map((chatIds) =>
    env.SELF.fetch('https://self/internal/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Batch-Secret': env.WEBHOOK_SECRET },
      body: JSON.stringify({ chatIds, post }) // the exact post, so batches never call Gemini themselves
    }).then((r) => r.json())));
  const sent = results.reduce((n, r) => n + (r.status === 'fulfilled' ? r.value.ok || 0 : 0), 0);
  log.info('daily broadcast', { word: post.entry.word, chats: ids.length, sent, batches: batches.length, fallback: Boolean(post.content.fallback) });
}

// ── http ───────────────────────────────────────────────────────────────────
export default {
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    const brand = serveBrand(request);
    if (brand) return brand;

    if (pathname === '/webhook' && request.method === 'POST') {
      if (!verifyWebhook(request, env)) return new Response('forbidden', { status: 403 });
      const update = await request.json().catch(() => null);
      if (update) ctx.waitUntil(handleUpdate(update, env));
      return new Response('ok');
    }
    if (pathname === '/internal/batch' && request.method === 'POST') {
      if (!env.WEBHOOK_SECRET || request.headers.get('X-Batch-Secret') !== env.WEBHOOK_SECRET) return new Response('forbidden', { status: 403 });
      const { chatIds, post } = await request.json();
      const ok = await sendBatch(env, chatIds.slice(0, BATCH), post);
      return Response.json({ ok });
    }
    if (pathname === '/healthz' || pathname === '/status' || pathname === '/') {
      let checks, count = null, post = null;
      try {
        [count, post] = await Promise.all([db.count(env), db.getPost(env, sgtDate())]);
        checks = { postgres: 'ok', words: WORDS.length > 0 ? 'ok' : 'FAIL: empty word bank' };
      } catch (err) {
        checks = { postgres: `FAIL: ${String(err.message).replace(/postgres(ql)?:\/\/\S+/g, '<conn>')}` };
      }
      if (pathname === '/healthz') return healthz(env, { checks, extra: { chats: count, todays_post: Boolean(post) } });
      const today = pickWordForDate(sgtDate(), allowNsfw(env));
      return statusPage(env, {
        name: "Miku's Singlish Word of the Day",
        username: '@mikusinglishwordofthedaylehbot',
        icon: '🎵',
        description: 'A Singlish word every day at 12:01am SGT, with fresh Miku-voiced examples from Gemini.',
        ok: Object.values(checks).every((v) => v === 'ok'),
        metrics: { 'Chats': count ?? '—', "Today's word": today.word, 'Words': WORDS.length, 'Post ready': post ? 'yes' : 'not yet' },
        commands: [['/today', "Post today's word now"], ['/word <word>', 'Look up a word'], ['/list', 'All words'], ['/unsubscribe', 'Stop daily posts'], ['/debug', 'Health check'], ['/help', 'Help']],
        sections: [{ title: 'Schedule', html: `Daily word: <b>every day ${DAILY_TIME} SGT</b> to every subscribed chat and channel` }]
      });
    }
    return env.ASSETS.fetch(request);
  },

  async scheduled(event, env, ctx) {
    await broadcast(env);
  }
};
