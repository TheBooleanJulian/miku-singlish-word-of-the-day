# 🎵 Miku's Singlish Word of the Day

> *"Aiyoh, I'm here to teach you Singlish one word at a time lah~"*

A Telegram bot that posts a **daily Singlish word at 6am SGT**, paired with real Singapore news — all voiced by Hatsune Miku.

**[@mikusinglishwordofthedaylehbot](https://t.me/mikusinglishwordofthedaylehbot)**

Built by [TheBooleanJulian](https://github.com/TheBooleanJulian).

---

## Features

| | |
|---|---|
| 🕕 | Daily 6am SGT post, deterministic word selection (consistent across restarts) |
| 🤖 | Claude Haiku + web search → real recent SG news applied to the word |
| 🎨 | 1080×640 Pillow card — dark premium, teal accents, Migu figure |
| 📚 | 412 Singlish words — examples generated live by Claude at post time |
| 🔧 | `/debug` command for deployment health checks |

---

## Project Structure

```
miku-singlish-bot/
├── bot.py               — Main bot, scheduler, all command handlers
├── card_generator.py    — Pillow card renderer (1080×640)
├── singlish_words.py    — Word bank (412 words, examples generated live by Claude)
├── assets/
│   └── sgmigu.png       — Migu figure (pre-processed, transparent bg)
├── requirements.txt
├── zbpack.json          — Zeabur build + start config
├── .env.example         — Environment variable template
└── .gitignore
```

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/TheBooleanJulian/miku-singlish-bot.git
cd miku-singlish-bot
pip install -r requirements.txt
```

### 2. Create your Telegram bot

```
@BotFather → /newbot → copy the token
```

Add the bot as an **admin** to your target channel or group.

### 3. Get your Chat ID

Send a message to your channel/group, then visit:
```
https://api.telegram.org/bot<TOKEN>/getUpdates
```
Find `"chat": {"id": -100xxxxxxxxxx}` in the response.

### 4. Set environment variables

```bash
cp .env.example .env
# Edit .env with your values
```

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from BotFather |
| `TARGET_CHAT_ID` | Channel/group ID (e.g. `-1001234567890`) |
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) |

### 5. Run locally

```bash
export $(cat .env | xargs)
python bot.py
```

---

## Deploy to Zeabur

1. Push this repo to GitHub
2. [Zeabur Dashboard](https://zeabur.com) → **New Project** → **Deploy from GitHub**
3. Select this repo
4. **Environment** tab → add the 3 variables from `.env.example`
5. **Deploy** — Zeabur reads `zbpack.json` for build and start commands automatically

---

## Commands

| Command | Description |
|---|---|
| `/start` / `/help` | Welcome message + command list |
| `/today` | Trigger today's word immediately (with AI content) |
| `/word <word>` | Look up any Singlish word in the bank |
| `/list` | See all 412 words |
| `/debug` | Health check: env vars, card render, Anthropic ping, scheduler status |

---

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

No need to add examples — Claude generates fresh first-person Miku examples at post time.

---

## Card Design

- **Canvas:** 1080 × 640px
- **Layout:** Text panel (left, 0–688px) | Migu panel (right, 700–1080px)
- **Palette:** `#00d4c8` teal on `#08101a` deep dark
- **Example box:** Solid teal bg, black text — max contrast, max readability
- **Date/day:** Centred in blank space above Migu figure
- **Fonts:** DejaVu (bundled with most Linux distros — drop JetBrains Mono into `fonts/` for the full aesthetic)

To use JetBrains Mono: download `JetBrainsMono-Bold.ttf` and `JetBrainsMono-Regular.ttf` into a `fonts/` folder. The generator checks that path first.

---

## Stack

| Layer | Tech |
|---|---|
| Bot framework | `python-telegram-bot` 21.x |
| Scheduler | `APScheduler` 3.x (AsyncIOScheduler, CronTrigger) |
| AI | `anthropic` SDK — Claude Haiku + `web_search_20250305` tool |
| Card | `Pillow` 10.x |
| Hosting | [Zeabur](https://zeabur.com) |

---

*Part of the TheBooleanJulian bot ecosystem* 🤖✨
