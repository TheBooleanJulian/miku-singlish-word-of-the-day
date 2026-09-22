<div align="center">

# Miku's Singlish Word of the Day

**A Telegram bot that posts a daily Singlish word at 6am SGT, paired with a fresh Miku-voiced example generated live by Gemini.**

![Python](https://img.shields.io/badge/-Python-3776AB?logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/-Telegram-26A5E4?logo=telegram&logoColor=white)
![Gemini](https://img.shields.io/badge/-Gemini-8E75B2?logo=googlegemini&logoColor=white)
![License](https://img.shields.io/badge/license-AGPLv3%20%2B%20Commercial-00D4C8.svg)

</div>

---

> *"Aiyoh, I'm here to teach you Singlish one word at a time lah~"*

**[@mikusinglishwordofthedaylehbot](https://t.me/mikusinglishwordofthedaylehbot)**

## What it does

Every day at 6am SGT, the bot deterministically picks a Singlish word from a 412-word bank, asks Gemini to generate a fresh first-person Miku-flavoured example for it, renders both onto a 1080×640 Pillow card, and posts it to every subscribed chat. Chats auto-subscribe when the bot is added to a group/channel, and can also subscribe/unsubscribe manually with `/start` and `/unsubscribe`.

## Features

- Daily 6am SGT post, deterministic word selection (consistent across restarts)
- Gemini-generated first-person Miku examples, created fresh at post time (not pre-written)
- 1080×640 Pillow card — dark premium look, teal accents, Migu figure
- 412-word Singlish bank (`singlish_words.py`)
- Auto-subscribe on group/channel add, auto-unsubscribe on removal; manual `/start` / `/unsubscribe`
- Multi-chat broadcast — one word, sent to every subscribed chat
- `/debug` command for deployment health checks (env vars, card render, scheduler status)
- Optional NSFW word pool, gated behind an `ALLOW_NSFW` flag

## Tech Stack

| Layer | Choice |
|---|---|
| Bot framework | python-telegram-bot 21.x |
| Scheduler | APScheduler 3.x (AsyncIOScheduler, CronTrigger) |
| AI | Google Gemini via `google-genai` |
| Card rendering | Pillow 10.x |
| Persistence | `PicklePersistence` (subscribed chats) |
| Hosting | Zeabur (Docker via `zbpack.json`) |

## Screenshots

The generated card design uses the Migu figure in `assets/sgmigu.png` (and `assets/migu.png`) on a dark teal card. _A sample rendered card image is coming soon — none is checked into the repo yet._

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/TheBooleanJulian/miku-singlish-word-of-the-day.git
cd miku-singlish-word-of-the-day
pip install -r requirements.txt
```

### 2. Create your Telegram bot

```
@BotFather → /newbot → copy the token
```

Add the bot as an **admin** to your target channel or group (it will auto-subscribe on add).

### 3. Set environment variables

```bash
cp .env.example .env
# Edit .env with your values
```

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from BotFather |
| `GEMINI_API_KEY` | From [Google AI Studio](https://aistudio.google.com/) |
| `ALLOW_NSFW` | Set to `1` to include vulgar Singlish words in the daily rotation (default `0`) |

> Note: `.env.example` in this repo currently lists a legacy `ANTHROPIC_API_KEY`/`TARGET_CHAT_ID` pair from an earlier version of the bot — the code that actually runs today reads `TELEGRAM_TOKEN` and `GEMINI_API_KEY`, and subscribes chats dynamically rather than using a fixed target chat ID.

### 4. Run locally

```bash
python bot.py
```

## Deploy to Zeabur

1. Push this repo to GitHub
2. [Zeabur Dashboard](https://zeabur.com) → **New Project** → **Deploy from GitHub**
3. Select this repo
4. **Environment** tab → add `TELEGRAM_TOKEN` and `GEMINI_API_KEY`
5. **Deploy** — Zeabur reads `zbpack.json` for build and start commands automatically

## Commands

| Command | Description |
|---|---|
| `/start` / `/help` | Welcome message + command list, subscribes this chat |
| `/today` | Trigger today's word immediately (with AI-generated example) |
| `/word <word>` | Look up any Singlish word in the bank |
| `/list` | See all 412 words |
| `/unsubscribe` | Stop daily posts in this chat |
| `/debug` | Health check: env vars, card render, Gemini ping, scheduler status |

## Adding Words

Edit `singlish_words.py` and append to `SINGLISH_WORDS`:

```python
{
    "word": "your_word",
    "type": "adjective / noun / phrase / particle",
    "pronunciation": "phonetic-spelling",
    "meaning": "Clear explanation of the word.",
    # Optional: "nsfw": True  — filtered out unless ALLOW_NSFW=1
},
```

No need to add examples — Gemini generates fresh first-person Miku examples at post time.

## Card Design

- **Canvas:** 1080 × 640px
- **Layout:** Text panel (left, 0–688px) | Migu panel (right, 700–1080px)
- **Palette:** `#00d4c8` teal on `#08101a` deep dark
- **Fonts:** DejaVu (bundled with most Linux distros — drop JetBrains Mono into `fonts/` for the full aesthetic)

## Status / Roadmap

- [x] Daily 6am SGT scheduled post with deterministic word selection
- [x] 412-word Singlish bank with live AI-generated examples
- [x] Auto-subscribe/unsubscribe on group/channel add/remove
- [x] Multi-chat broadcast
- [x] `/debug` health-check command
- [ ] Update `.env.example` to match the current Gemini-based configuration
- [ ] Automated tests for word selection and card rendering

## Changelog

- **2026-04-20** — Store scheduler in a module-level variable to prevent pickle errors
- **2026-04-18** — Switched from Claude to Gemini 2.5 Flash; added multi-chat subscription (auto-subscribe/unsubscribe)
- **2026-04-16** — Expanded word bank to 412 words with live AI-generated examples
- **2026-04-15** — Initial release: Miku's Singlish Word of the Day bot

## License

This project is dual licensed.

- Community Edition — [GNU Affero General Public License v3 (AGPLv3)](LICENSE). Free to use, modify, and self-host. If you distribute a modified version or run it as a network service, you must make the corresponding source available.
- Commercial License — for organisations that want to embed, modify, or distribute this software without AGPLv3's obligations. See [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

---

<div align="center">
<sub>Built by <a href="https://github.com/TheBooleanJulian">@TheBooleanJulian</a></sub>
</div>
