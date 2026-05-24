# SG Chinese Dictionary

A multi-platform Singaporean Chinese dictionary for looking up local Chinese terms by Hanyu Pinyin, Chinese characters, or English definitions.

## Features

- Auto-detects input type (Chinese characters, Pinyin, or English)
- Tone-agnostic Pinyin matching (`hao`, `hǎo`, and `hào` all return the same results)
- Paginated results with multiple sort options (Pinyin or English, A→Z / Z→A)
- Per-user sort preference persistence

Available on three platforms:

| Platform | Interface | Extra Features |
|----------|-----------|----------------|
| Web PWA | [sg-chinese.uwuapps.org](https://sg-chinese.uwuapps.org/) | Installable, offline support, light/dark theme |
| [Discord Bot](https://discord.com/oauth2/authorize?client_id=1508221545959653567) | Slash commands | Random word, inspirational quotes |
| [Telegram Bot](https://t.me/sgchinese_dict_bot) | Free-text + slash commands | DM-only |

## Project Structure

```bash
sgchinese-dictionary/
├── main-site/          # PWA web app (deployed on Vercel)
│   ├── api/            # Serverless search endpoint
│   └── ...
├── discord-bot/        # Discord slash-command bot (Python)
└── telegram-bot/       # Telegram bot (Python)
```

All three platforms share the same [Supabase](https://supabase.com) backend database.

## Tech Stack

- **Frontend**: Vanilla HTML/CSS/JavaScript, PWA with Service Worker
- **Hosting**: Vercel (Singapore region)
- **Bots**: Python (discord.py, Telethon) with aiohttp and aiosqlite
- **Database**: Supabase (shared), SQLite (per-bot interaction and preference storage)

## Bot Commands

### Discord (`/`)

| Command | Description |
|---------|-------------|
| `/search <term>` | Search the dictionary |
| `/random` | Get a random entry |
| `/sort` | Change your sort preference |
| `/quote` | Get an inspirational quote |
| `/about` | About this bot |
| `/help` | Show available commands |

### Telegram

| Command | Description |
|---------|-------------|
| Just type anything | Search the dictionary |
| `/start` | Welcome message and usage guide |
| `/random` | Get a random entry |
| `/sort` | Change your sort preference |
| `/about` | About this bot |
| `/help` | Show available commands |

The Telegram bot only responds in direct messages (DMs).
