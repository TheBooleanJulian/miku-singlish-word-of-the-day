"""
Miku's Singlish Word of the Day Bot — @mikusinglishwordofthedaylehbot
Daily 6am SGT: Singlish word + recent Singapore news, Miku-style.
"""

import os
import random
import logging
import json
import hashlib
from datetime import datetime, date
import pytz
from google import genai
from google.genai import types

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ChatMemberHandler, ContextTypes, PicklePersistence
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from singlish_words import SINGLISH_WORDS
from card_generator import generate_card

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("MikuSinglishBot")

TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY  = os.environ["GEMINI_API_KEY"]
PERSISTENCE_PATH = os.environ.get("PERSISTENCE_PATH", "./miku_bot.pkl")
SGT = pytz.timezone("Asia/Singapore")

ai_client = genai.Client(api_key=GEMINI_API_KEY)


# ── Word selection ─────────────────────────────────────────────────────────────
def pick_word_for_today() -> dict:
    """Deterministic daily pick — same word all day even if bot restarts."""
    allow_nsfw = os.environ.get("ALLOW_NSFW", "0").lower() in ("1", "true", "yes")
    pool = SINGLISH_WORDS if allow_nsfw else [w for w in SINGLISH_WORDS if not w.get("nsfw")]
    today_str = date.today().isoformat()
    seed = int(hashlib.md5(today_str.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    return rng.choice(pool)


# ── AI content generation ──────────────────────────────────────────────────────
def generate_miku_content(word_entry: dict) -> dict:
    """Call Gemini Flash 2.5 with Google Search grounding to get recent SG news
    and generate Miku's post with 3 live example sentences."""
    word    = word_entry["word"]
    meaning = word_entry["meaning"]

    prompt = f"""You are Hatsune Miku — the iconic virtual vocaloid idol — fully fluent in Singlish after living in Singapore long enough to be a local.

Today's Singlish Word of the Day is: **{word}**
Meaning: {meaning}

Tasks:
1. Use Google Search to find 1-2 RECENT Singapore news stories from the past 7 days.
2. Write a punchy Miku-in-Singapore post that:
   - Applies the word to real Singapore news you found
   - Sounds like Miku: cheerful, uses Singlish particles (lah, leh, sia, wah, etc.), references vocaloid/music life naturally
   - Ends with a "🎤 Miku Verdict:" one-liner using the word
3. Generate 3 fresh first-person example sentences as Miku living in Singapore.
   Each must: use the word naturally, be 1 sentence, sound like Miku, reference Singapore life.

Respond ONLY in this exact JSON (no markdown, no fences):
{{
  "news_headline": "One sentence summary of the SG news story referenced",
  "news_source": "e.g. CNA, Straits Times, TODAY",
  "telegram_caption": "Full Miku post 180-260 words. Singlish, charming, references the news. Use line breaks. Include Miku Verdict at end.",
  "fun_fact": "One quirky linguistic or cultural fun fact about this Singlish word (1-2 sentences).",
  "examples": ["First person example sentence 1.", "First person example sentence 2.", "First person example sentence 3."]
}}"""

    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    result_text = response.text or ""
    clean = result_text.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
    clean = clean.strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        logger.warning("JSON parse failed — using fallback content")
        return {
            "news_headline": "Singapore continues to shine as a global city",
            "news_source": "CNA",
            "telegram_caption": (
                f"Wah, today Miku teach you one very important word sia! ✨\n\n"
                f"*{word.upper()}* — {meaning}\n\n"
                f"Today I feel very {word} lah!\n\n"
                f"Singapore life confirm need this word one lah~ 🎵\n\n"
                f"🎤 *Miku Verdict:* Very {word}, 10/10 would {word} again!"
            ),
            "fun_fact": f"'{word}' is one of the most versatile words in the Singlish lexicon!",
            "examples": [f"I feel so {word} today lah!", f"Wah, very {word} sia!", f"This is the most {word} thing in Singapore!"],
        }


# ── Caption builder ────────────────────────────────────────────────────────────
def build_telegram_caption(word_entry: dict, ai_content: dict, date_str: str) -> str:
    word          = word_entry["word"]
    word_type     = word_entry["type"]
    pronunciation = word_entry["pronunciation"]
    meaning       = word_entry["meaning"]
    examples      = ai_content.get("examples", [])
    news_src      = ai_content.get("news_source", "")
    news_hl       = ai_content.get("news_headline", "")
    fun_fact      = ai_content.get("fun_fact", "")
    body          = ai_content.get("telegram_caption", "")

    lines = [
        "🎵 *Miku Singlish word of the day leh?*",
        f"_{date_str}_",
        "─" * 28,
        "",
        f"📖 *{word.upper()}*",
        f"_{word_type}_ · /{pronunciation}/",
        "",
        meaning,
        "",
        *[f"▸ _{ex}_" for ex in examples[:3]],
        "",
        "─" * 28,
        "",
        body,
        "",
    ]

    if news_hl:
        lines += [f"📰 *Referenced:* {news_hl}", f"_via {news_src}_", ""]

    if fun_fact:
        lines += [f"💡 *Fun Fact:* {fun_fact}", ""]

    lines += ["─" * 28, "_Powered by @mikusinglishwordofthedaylehbot · TheBooleanJulian_ 🤖✨"]

    return "\n".join(lines)


# ── Core broadcast function ────────────────────────────────────────────────────
async def broadcast_word_of_the_day(app: Application, word_entry: dict = None):
    """Generate once, send to all subscribed chats."""
    subscribed: set = app.bot_data.get("subscribed_chats", set())
    if not subscribed:
        logger.warning("No subscribed chats — skipping broadcast")
        return

    now_sgt  = datetime.now(SGT)
    date_str = now_sgt.strftime("%A, %d %b %Y")

    if word_entry is None:
        word_entry = pick_word_for_today()
    logger.info(f"Broadcasting WOTD '{word_entry['word']}' to {len(subscribed)} chats")

    ai_content = generate_miku_content(word_entry)

    card_path = f"/tmp/miku_wotd_{now_sgt.strftime('%Y%m%d')}.png"
    generate_card(
        word          = word_entry["word"],
        word_type     = word_entry["type"],
        pronunciation = word_entry["pronunciation"],
        meaning       = word_entry["meaning"],
        examples      = ai_content.get("examples", []),
        date_str      = now_sgt.strftime("%d %b %Y"),
        day_str       = now_sgt.strftime("%A"),
        output_path   = card_path,
    )

    caption = build_telegram_caption(word_entry, ai_content, date_str)

    for chat_id in list(subscribed):
        try:
            with open(card_path, "rb") as photo:
                await app.bot.send_photo(
                    chat_id    = chat_id,
                    photo      = photo,
                    caption    = caption,
                    parse_mode = ParseMode.MARKDOWN,
                )
            logger.info(f"Posted to {chat_id}")
        except Exception as e:
            err = str(e).lower()
            logger.error(f"Failed to post to {chat_id}: {e}")
            if any(kw in err for kw in ("blocked", "chat not found", "kicked", "deactivated")):
                subscribed.discard(chat_id)
                logger.info(f"Removed unreachable chat {chat_id}")


async def post_word_of_the_day_to_chat(bot: Bot, chat_id: str, word_entry: dict = None):
    """Send to a single chat — used by /today command."""
    now_sgt  = datetime.now(SGT)
    date_str = now_sgt.strftime("%A, %d %b %Y")

    if word_entry is None:
        word_entry = pick_word_for_today()

    ai_content = generate_miku_content(word_entry)

    card_path = f"/tmp/miku_wotd_{now_sgt.strftime('%Y%m%d_%H%M%S')}.png"
    generate_card(
        word          = word_entry["word"],
        word_type     = word_entry["type"],
        pronunciation = word_entry["pronunciation"],
        meaning       = word_entry["meaning"],
        examples      = ai_content.get("examples", []),
        date_str      = now_sgt.strftime("%d %b %Y"),
        day_str       = now_sgt.strftime("%A"),
        output_path   = card_path,
    )

    caption = build_telegram_caption(word_entry, ai_content, date_str)

    with open(card_path, "rb") as photo:
        await bot.send_photo(
            chat_id    = chat_id,
            photo      = photo,
            caption    = caption,
            parse_mode = ParseMode.MARKDOWN,
        )


# ── Subscription helpers ───────────────────────────────────────────────────────
def _subscribe(bot_data: dict, chat_id: str) -> bool:
    subscribed: set = bot_data.setdefault("subscribed_chats", set())
    already = chat_id in subscribed
    subscribed.add(chat_id)
    return not already


def _unsubscribe(bot_data: dict, chat_id: str) -> bool:
    subscribed: set = bot_data.get("subscribed_chats", set())
    if chat_id in subscribed:
        subscribed.discard(chat_id)
        return True
    return False


# ── Command handlers ───────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or context.bot_data is None:
        return
    chat_id = str(update.effective_chat.id)
    is_new = _subscribe(context.bot_data, chat_id)

    if is_new:
        sub_note = "_Steady! I'll send you the word every day at 6am SGT lah~ 🎵_\n\n"
    else:
        sub_note = "_Eh, you already subscribed one leh~ Still sending daily at 6am SGT! 🎵_\n\n"

    await update.message.reply_text(
        "🎵 *Miku's Singlish Word of the Day* 🎵\n\n"
        "@mikusinglishwordofthedaylehbot\n\n"
        "Aiyoh, Miku is here to teach you Singlish one word at a time lah~\n\n"
        + sub_note +
        "*Commands:*\n"
        "/today — Post today's word now!\n"
        "/word <word> — Look up a Singlish word\n"
        "/list — See all words in my vocabulary\n"
        "/unsubscribe — Stop daily posts here\n"
        "/debug — Run deployment health check\n"
        "/help — Show this message again\n\n"
        "_Daily post at 6am SGT every day! Don't miss ah~ 🎤_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or context.bot_data is None:
        return
    chat_id = str(update.effective_chat.id)
    removed = _unsubscribe(context.bot_data, chat_id)
    if removed:
        await update.message.reply_text(
            "Okayyyy, Miku won't post here anymore lah~ 😢\n"
            "Use /start to re-subscribe anytime!",
        )
    else:
        await update.message.reply_text(
            "Eh, you weren't even subscribed here leh~\n"
            "Use /start to subscribe!",
        )


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-subscribe when bot is added to a group/channel, unsubscribe when removed."""
    if not update.my_chat_member or context.bot_data is None:
        return
    result = update.my_chat_member
    new_status = result.new_chat_member.status
    chat_id = str(result.chat.id)
    chat_title = result.chat.title or chat_id

    if new_status in ("member", "administrator"):
        _subscribe(context.bot_data, chat_id)
        logger.info(f"Auto-subscribed chat '{chat_title}' ({chat_id})")
        try:
            await context.bot.send_message(
                chat_id    = chat_id,
                text       = "🎵 Wah, Miku has arrived lah! I'll send Singlish Word of the Day here every 6am SGT~\nUse /unsubscribe to stop.",
                parse_mode = ParseMode.MARKDOWN,
            )
        except Exception:
            pass
    elif new_status in ("left", "kicked"):
        _unsubscribe(context.bot_data, chat_id)
        logger.info(f"Auto-unsubscribed chat '{chat_title}' ({chat_id})")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message:
        return
    msg = await update.message.reply_text(
        "_Miku is preparing today's word… wait ah~ 🎵_",
        parse_mode=ParseMode.MARKDOWN,
    )
    try:
        await post_word_of_the_day_to_chat(
            bot=context.bot,
            chat_id=str(update.effective_chat.id),
        )
        await msg.delete()
    except Exception as e:
        logger.error(f"/today error: {e}", exc_info=True)
        await msg.edit_text(
            f"Aiyoh, something broke lah 😭\n`{e}`",
            parse_mode=ParseMode.MARKDOWN,
        )


async def cmd_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Eh, you never say which word leh~\nUsage: `/word <singlish_word>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    query = " ".join(context.args).lower().strip()
    matches = [w for w in SINGLISH_WORDS if w["word"].lower() == query]
    if not matches:
        matches = [w for w in SINGLISH_WORDS if query in w["word"].lower()]

    if not matches:
        await update.message.reply_text(
            f"Catch no ball leh — I don't know `{query}` yet lor~\n"
            f"Try /list to see what I know!",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    e = matches[0]
    await update.message.reply_text(
        f"📖 *{e['word'].upper()}*\n"
        f"_{e['type']}_ · /{e['pronunciation']}/\n\n"
        f"{e['meaning']}\n\n"
        f"_Use /today to see a live post with fresh examples!_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    unique = sorted({w["word"] for w in SINGLISH_WORDS})
    word_list = " • ".join(f"`{w}`" for w in unique)
    await update.message.reply_text(
        f"🎵 *My Singlish Vocabulary* ({len(unique)} words)\n\n{word_list}\n\n"
        f"_More coming, steady bom pi pi!_ ✨",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deployment health check."""
    if not update.effective_chat:
        return
    lines = ["🔧 *Miku Debug Mode* — checking systems lah~\n"]

    # 1. Env vars
    env_ok = all([
        os.environ.get("TELEGRAM_TOKEN"),
        os.environ.get("GEMINI_API_KEY"),
    ])
    lines.append(f"{'✅' if env_ok else '❌'} Env vars: `TELEGRAM_TOKEN`, `GEMINI_API_KEY`")

    # 2. Word bank
    lines.append(f"✅ Word bank: *{len(SINGLISH_WORDS)} words* loaded")

    # 3. Today's word
    word_entry = pick_word_for_today()
    lines.append(f"✅ Today's word: *{word_entry['word']}*")

    # 4. Card render
    try:
        now_sgt   = datetime.now(SGT)
        card_path = f"/tmp/miku_debug_{now_sgt.strftime('%H%M%S')}.png"
        generate_card(
            word          = word_entry["word"],
            word_type     = word_entry["type"],
            pronunciation = word_entry["pronunciation"],
            meaning       = word_entry["meaning"],
            examples      = ["Examples generated live at post time!", "Use /today for a full post with fresh AI examples.", "Word bank stores definitions only — no static examples."],
            date_str      = now_sgt.strftime("%d %b %Y"),
            day_str       = now_sgt.strftime("%A"),
            output_path   = card_path,
        )
        with open(card_path, "rb") as photo:
            await context.bot.send_photo(
                chat_id    = update.effective_chat.id,
                photo      = photo,
                caption    = f"🃏 *Debug card* — *{word_entry['word']}* (no AI content)",
                parse_mode = ParseMode.MARKDOWN,
            )
        lines.append("✅ Card render: OK ↑")
    except Exception as e:
        lines.append(f"❌ Card render failed: `{e}`")

    # 5. Gemini API ping
    try:
        ping = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Reply with exactly: pong",
        )
        lines.append(f"✅ Gemini API: `{ping.text.strip()}`")
    except Exception as e:
        lines.append(f"❌ Gemini API: `{e}`")

    # 6. Scheduler
    scheduler = context.application.bot_data.get("scheduler")
    if scheduler and scheduler.running:
        jobs = scheduler.get_jobs()
        next_run = jobs[0].next_run_time.strftime("%Y-%m-%d %H:%M %Z") if jobs else "?"
        lines.append(f"✅ Scheduler running — next post: `{next_run}`")
    else:
        lines.append("❌ Scheduler not running")

    # 7. Subscribed chats
    subscribed = context.bot_data.get("subscribed_chats", set())
    lines.append(f"ℹ️ Subscribed chats: *{len(subscribed)}*")
    lines.append(f"ℹ️ This chat ID: `{update.effective_chat.id}`")
    lines.append("\n_Steady bom pi pi, Miku is ready lah!_ 🎤")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


# ── Scheduler ──────────────────────────────────────────────────────────────────
def setup_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=SGT)
    scheduler.add_job(
        func=lambda: app.create_task(broadcast_word_of_the_day(app)),
        trigger=CronTrigger(hour=6, minute=0, timezone=SGT),
        id="daily_wotd",
        name="Miku WOTD 6am SGT",
        replace_existing=True,
    )
    logger.info("Scheduler set: daily WOTD at 06:00 SGT")
    return scheduler


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    logger.info("Starting @mikusinglishwordofthedaylehbot…")

    persistence = PicklePersistence(filepath=PERSISTENCE_PATH)
    app = Application.builder().token(TELEGRAM_TOKEN).persistence(persistence).build()

    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("help",        cmd_help))
    app.add_handler(CommandHandler("today",       cmd_today))
    app.add_handler(CommandHandler("word",        cmd_word))
    app.add_handler(CommandHandler("list",        cmd_list))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(CommandHandler("debug",       cmd_debug))
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    scheduler = setup_scheduler(app)
    app.bot_data["scheduler"] = scheduler
    scheduler.start()

    logger.info("Bot is live~ 🎵")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
