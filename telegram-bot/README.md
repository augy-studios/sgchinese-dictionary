# SG Chinese Dictionary - Telegram Bot

A DM-only Telegram bot built with [Telethon](https://docs.telethon.dev/) that lets users search the SG Chinese Dictionary by Chinese characters, Pinyin, or English.

---

## Features

| Feature | Details |
|---|---|
| **Free-text search** | Type anything at any time - the bot auto-detects Chinese / Pinyin / English |
| **Pinyin tone matching** | `hao`, `hǎo`, and `hǎo` all find the same entries |
| **Paginated results** | 5 results per page with inline ◀ / ▶ navigation |
| **4 sort orders** | Pinyin A→Z, Pinyin Z→A, English A→Z, English Z→A |
| **Persistent sort preference** | Remembered per user in SQLite across restarts |
| **DM-only** | The bot ignores all group / channel messages |

---

## File structure

```bash
telegram-bot/
├── bot.py           # Main bot - event handlers and message formatting
├── search.py        # Supabase search logic (ported from the website API)
├── database.py      # SQLite session storage (sort preference, active query, page)
├── config.py        # Loads settings from .env
├── requirements.txt
├── .env.example     # Template - copy to .env and fill in
├── .gitignore
└── README.md
```

---

## Commands reference

| Command | Description |
|---|---|
| `/start` | Welcome message and quick guide |
| `/help` | Full usage details |
| `/sort` | Pick a default sort order |
| `/about` | About the dictionary |
| *(any text)* | Search the dictionary |
