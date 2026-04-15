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
import anthropic

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
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

TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
TARGET_CHAT_ID    = os.environ["TARGET_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SGT = pytz.timezone("Asia/Singapore")

ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Word selection ─────────────────────────────────────────────────────────────
def pick_word_for_today() -> dict:
    """Deterministic daily pick — same word all day even if bot restarts."""
    today_str = date.today().isoformat()
    seed = int(hashlib.md5(today_str.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    return rng.choice(SINGLISH_WORDS)


# ── AI content generation ──────────────────────────────────────────────────────
def generate_miku_content(word_entry: dict) -> dict:
    """Call Claude Haiku with web_search to get recent SG news and generate Miku's post."""
    word     = word_entry["word"]
    meaning  = word_entry["meaning"]
    examples = word_entry["examples"]
    ex_block = "\n".join(f"  {i+1}. {ex}" for i, ex in enumerate(examples))

    prompt = f"""You are Hatsune Miku — the iconic virtual vocaloid idol — fully fluent in Singlish after living in Singapore long enough to be a local.

Today's Singlish Word of the Day is: **{word}**
Meaning: {meaning}
Examples:
{ex_block}

Tasks:
1. Use web_search to find 1-2 RECENT Singapore news stories from the past 7 days.
2. Write a punchy Miku-in-Singapore post that:
   - Applies the word to real Singapore news you found
   - Sounds like Miku: cheerful, uses Singlish particles (lah, leh, sia, wah, etc.), references vocaloid/music life naturally
   - Ends with a "🎤 Miku Verdict:" one-liner using the word

Respond ONLY in this exact JSON (no markdown, no fences):
{{
  "news_headline": "One sentence summary of the SG news story referenced",
  "news_source": "e.g. CNA, Straits Times, TODAY",
  "telegram_caption": "Full Miku post 180-260 words. Singlish, charming, references the news. Use line breaks. Include Miku Verdict at end.",
  "fun_fact": "One quirky linguistic or cultural fun fact about this Singlish word (1-2 sentences)."
}}"""

    response = ai_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text = block.text

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
                f"{examples[0]}\n\n"
                f"Singapore life confirm need this word one lah~ 🎵\n\n"
                f"🎤 *Miku Verdict:* Very {word}, 10/10 would {word} again!"
            ),
            "fun_fact": f"'{word}' is one of the most versatile words in the Singlish lexicon!",
        }


# ── Caption builder ────────────────────────────────────────────────────────────
def build_telegram_caption(word_entry: dict, ai_content: dict, date_str: str) -> str:
    word          = word_entry["word"]
    word_type     = word_entry["type"]
    pronunciation = word_entry["pronunciation"]
    meaning       = word_entry["meaning"]
    examples      = word_entry["examples"]
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


# ── Core post function ─────────────────────────────────────────────────────────
async def post_word_of_the_day(bot: Bot, chat_id: str = None, word_entry: dict = None):
    chat_id = chat_id or TARGET_CHAT_ID
    now_sgt  = datetime.now(SGT)
    date_str = now_sgt.strftime("%A, %d %b %Y")

    logger.info(f"Generating WOTD for {date_str}…")

    if word_entry is None:
        word_entry = pick_word_for_today()
    logger.info(f"Word: {word_entry['word']}")

    ai_content = generate_miku_content(word_entry)

    card_path = f"/tmp/miku_wotd_{now_sgt.strftime('%Y%m%d_%H%M%S')}.png"
    generate_card(
        word          = word_entry["word"],
        word_type     = word_entry["type"],
        pronunciation = word_entry["pronunciation"],
        meaning       = word_entry["meaning"],
        examples      = word_entry["examples"],
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
    logger.info(f"Posted WOTD '{word_entry['word']}' to {chat_id}")


# ── Command handlers ───────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *Miku's Singlish Word of the Day* 🎵\n\n"
        "@mikusinglishwordofthedaylehbot\n\n"
        "Aiyoh, Miku is here to teach you Singlish one word at a time lah~\n\n"
        "*Commands:*\n"
        "/today — Post today's word now!\n"
        "/word <word> — Look up a Singlish word\n"
        "/list — See all words in my vocabulary\n"
        "/debug — Run deployment health check\n"
        "/help — Show this message again\n\n"
        "_Daily post at 6am SGT every day! Don't miss ah~ 🎤_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        "_Miku is preparing today's word… wait ah~ 🎵_",
        parse_mode=ParseMode.MARKDOWN,
    )
    try:
        await post_word_of_the_day(
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
    ex_lines = "\n".join(f"  {n}. _{ex}_" for n, ex in enumerate(e["examples"], 1))
    await update.message.reply_text(
        f"📖 *{e['word'].upper()}*\n"
        f"_{e['type']}_ · /{e['pronunciation']}/\n\n"
        f"{e['meaning']}\n\n"
        f"{ex_lines}",
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
    """Deployment health check — env vars, word bank, card render, Anthropic ping, scheduler."""
    lines = ["🔧 *Miku Debug Mode* — checking systems lah~\n"]

    # 1. Env vars
    env_ok = all([
        os.environ.get("TELEGRAM_TOKEN"),
        os.environ.get("TARGET_CHAT_ID"),
        os.environ.get("ANTHROPIC_API_KEY"),
    ])
    lines.append(f"{'✅' if env_ok else '❌'} Env vars: `TELEGRAM_TOKEN`, `TARGET_CHAT_ID`, `ANTHROPIC_API_KEY`")

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
            examples      = word_entry["examples"],
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

    # 5. Anthropic API ping
    try:
        ping = ai_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": "Reply: pong"}],
        )
        lines.append(f"✅ Anthropic API: `{ping.content[0].text.strip()}`")
    except Exception as e:
        lines.append(f"❌ Anthropic API: `{e}`")

    # 6. Scheduler
    scheduler = context.application.bot_data.get("scheduler")
    if scheduler and scheduler.running:
        jobs = scheduler.get_jobs()
        next_run = jobs[0].next_run_time.strftime("%Y-%m-%d %H:%M %Z") if jobs else "?"
        lines.append(f"✅ Scheduler running — next post: `{next_run}`")
    else:
        lines.append("❌ Scheduler not running")

    # 7. Chat IDs
    lines.append(f"ℹ️ TARGET_CHAT_ID: `{TARGET_CHAT_ID}`")
    lines.append(f"ℹ️ This chat ID:   `{update.effective_chat.id}`")
    lines.append("\n_Steady bom pi pi, Miku is ready lah!_ 🎤")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


# ── Scheduler ──────────────────────────────────────────────────────────────────
def setup_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=SGT)
    scheduler.add_job(
        func=lambda: app.create_task(post_word_of_the_day(app.bot)),
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

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("today",  cmd_today))
    app.add_handler(CommandHandler("word",   cmd_word))
    app.add_handler(CommandHandler("list",   cmd_list))
    app.add_handler(CommandHandler("debug",  cmd_debug))

    scheduler = setup_scheduler(app)
    app.bot_data["scheduler"] = scheduler
    scheduler.start()

    logger.info("Bot is live~ 🎵")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
