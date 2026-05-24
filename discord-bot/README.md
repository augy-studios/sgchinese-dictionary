# SG Chinese Dictionary - Discord Bot

A Discord slash-command bot built with [discord.py](https://discordpy.readthedocs.io/) that lets users search the SG Chinese Dictionary by Chinese characters, Pinyin, or English.

---

## Features

| Feature | Details |
|---|---|
| **Slash commands** | All interactions via Discord's native `/command` UI |
| **Auto-detected input** | Chinese / Pinyin / English detected automatically |
| **Pinyin tone matching** | `hao`, `hǎo`, and `hǎo` all find the same entries |
| **Paginated embeds** | 5 results per page with ◀ / ▶ navigation buttons |
| **4 sort orders** | Pinyin A→Z, Pinyin Z→A, English A→Z, English Z→A |
| **Per-user sort preference** | Remembered in SQLite across bot restarts |
| **Random entry** | Pick a random word from the dictionary |
| **Inspirational quotes** | Fetched live from [zenquotes.io](https://zenquotes.io/) |
| **Works in servers and DMs** | No channel restriction |

---

## Commands

| Command | Description |
|---|---|
| `/search <query>` | Search by Chinese characters, Pinyin, or English |
| `/sort` | Set your default sort order |
| `/random` | Get a random dictionary entry |
| `/quote` | Get an inspirational learning quote |
| `/about` | About the dictionary |
| `/help` | Usage guide and command list |

---

## File structure

```
discord-bot/
├── bot.py           # Slash commands, paginated embed views
├── search.py        # Supabase search logic (shared with Telegram bot)
├── database.py      # SQLite session storage (sort preference, last query)
├── config.py        # Loads settings from .env
├── requirements.txt
├── .env.example     # Copy to .env and fill in
├── .gitignore
└── README.md
```

---

## Setup on Debian VPS

### 1. Clone and enter the directory

```bash
git clone https://github.com/your-username/sgchinese-dictionary.git
cd sgchinese-dictionary/discord-bot
```

### 2. Create a Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
nano .env
```

Fill in your values:

| Variable | Where to find it |
|---|---|
| `DISCORD_TOKEN` | [Discord Developer Portal](https://discord.com/developers/applications) → Your App → Bot → Token |
| `SUPABASE_URL` | Supabase project dashboard → Project Settings → API |
| `SUPABASE_SERVICE_KEY` | Supabase project dashboard → Project Settings → API → `service_role` key |

### 4. Create a Discord application and bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**, give it a name.
3. Go to **Bot** → **Add Bot**.
4. Under **Privileged Gateway Intents**, no extras are needed (the bot uses only slash commands).
5. Copy the **Token** into your `.env`.
6. Under **OAuth2 → URL Generator**, select scope `bot` + `applications.commands`, then visit the generated URL to invite it to your server.

### 5. Run in tmux

```bash
tmux new-session -s discord-bot
source venv/bin/activate
python bot.py
```

Detach with `Ctrl+B` then `D`. Re-attach any time with:

```bash
tmux attach -t discord-bot
```

---

## Notes

- **Slash command sync** — on first start, `tree.sync()` registers commands globally with Discord. Global propagation can take up to an hour. For instant sync during development, pass your guild ID to `tree.sync(guild=discord.Object(id=YOUR_GUILD_ID))` in `bot.py`.
- **Button sessions** — pagination buttons are tied to the bot process. After a bot restart, buttons on old messages will stop responding (Discord will show "interaction failed"). This is expected; simply run `/search` again.
- **SQLite database** — `bot_data.db` is created automatically on first run and stores each user's sort preference. It is gitignored.
- **Quote API** — quotes are fetched from [zenquotes.io](https://zenquotes.io/), a free, open-source-friendly API requiring no API key.
