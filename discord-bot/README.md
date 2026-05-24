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
