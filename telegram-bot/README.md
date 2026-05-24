# SG Chinese Dictionary — Telegram Bot

A DM-only Telegram bot built with [Telethon](https://docs.telethon.dev/) that lets users search the SG Chinese Dictionary by Chinese characters, Pinyin, or English — just by typing, no command prefix needed.

---

## Features

| Feature | Details |
|---|---|
| **Free-text search** | Type anything at any time — the bot auto-detects Chinese / Pinyin / English |
| **Pinyin tone matching** | `hao`, `hǎo`, and `hǎo` all find the same entries |
| **Paginated results** | 5 results per page with inline ◀ / ▶ navigation |
| **4 sort orders** | Pinyin A→Z, Pinyin Z→A, English A→Z, English Z→A |
| **Persistent sort preference** | Remembered per user in SQLite across restarts |
| **DM-only** | The bot ignores all group / channel messages |

---

## Prerequisites

- Python 3.11+ on your Debian VPS
- A Telegram account (to obtain API credentials)
- The existing Supabase project credentials (same ones used by the website)

---

## Step 1 — Create the bot with BotFather

Open Telegram and start a chat with **[@BotFather](https://t.me/BotFather)**.

### 1a. Create the bot

```
/newbot
```

Follow the prompts:
- **Name** — e.g. `SG Chinese Dictionary`
- **Username** — must end in `bot`, e.g. `sgchinesedict_bot`

BotFather will reply with your **bot token**. Copy it — you need it for `.env`.

### 1b. Disable group access (enforce DM-only)

```
/setjoingroups
```

Select your bot → choose **Disable**.  
This prevents anyone from adding the bot to groups.

### 1c. Set the command list

```
/setcommands
```

Select your bot, then paste the following block **exactly** as one message:

```
start - Get started with the dictionary
help - How to use this bot
sort - Change sort order for results
about - About this dictionary
```

### 1d. Set a description (shown before the user starts the chat)

```
/setdescription
```

Suggested text:
```
Search the SG Chinese Dictionary by Chinese characters, Pinyin, or English — just type to search, no command needed.
```

### 1e. Set the about text (shown in the bot profile)

```
/setabouttext
```

Suggested text:
```
A dictionary of Chinese words commonly used in Singapore.
```

### 1f. (Optional) Set a profile photo

```
/setuserpic
```

Upload any image you like.

---

## Step 2 — Get Telegram API credentials

These are **different** from the BotFather token. Telethon needs them to connect via the MTProto API.

1. Go to [https://my.telegram.org/apps](https://my.telegram.org/apps) and log in with your Telegram account.
2. Click **Create new application**.
3. Fill in any app name and short name (e.g. `sgchinese` / `sgchinese`). Platform: **Other**.
4. Copy your **App api_id** (a number) and **App api_hash** (a hex string).

---

## Step 3 — Server setup on Debian

### 3a. Install Python 3.11+

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

Verify: `python3 --version`

### 3b. Clone the repository

```bash
git clone https://github.com/<your-username>/sgchinese-dictionary.git
cd sgchinese-dictionary/telegram-bot
```

### 3c. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3d. Configure environment variables

```bash
cp .env.example .env
nano .env
```

Fill in all five values:

```env
TELEGRAM_API_ID=<your api_id from my.telegram.org>
TELEGRAM_API_HASH=<your api_hash from my.telegram.org>
TELEGRAM_BOT_TOKEN=<token from BotFather>
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_KEY=<service_role key from Supabase dashboard>
```

Save and exit (`Ctrl-X`, `Y`, `Enter` in nano).

> **Security:** Never commit `.env` to Git. It is already in `.gitignore`.

---

## Step 4 — Run the bot in tmux

### 4a. Start a named tmux session

```bash
tmux new-session -d -s bot
```

### 4b. Attach and start the bot

```bash
tmux send-keys -t bot "cd ~/sgchinese-dictionary/telegram-bot && source venv/bin/activate && python bot.py" Enter
```

Or attach interactively first:

```bash
tmux attach -t bot
# then inside the session:
cd ~/sgchinese-dictionary/telegram-bot
source venv/bin/activate
python bot.py
# Detach with Ctrl-B, D
```

### 4c. Reconnect later

```bash
tmux attach -t bot
```

### 4d. Check logs

The bot logs to stdout. Inside the tmux session, scroll up with `Ctrl-B [` (then `q` to exit scroll mode), or redirect logs to a file:

```bash
python bot.py 2>&1 | tee bot.log
```

---

## Step 5 — Keeping the bot running across reboots (optional)

If you want the bot to restart automatically after a reboot, use a simple systemd service instead of (or alongside) tmux.

Create `/etc/systemd/system/sgchinese-bot.service`:

```ini
[Unit]
Description=SG Chinese Dictionary Telegram Bot
After=network.target

[Service]
User=<your-username>
WorkingDirectory=/home/<your-username>/sgchinese-dictionary/telegram-bot
ExecStart=/home/<your-username>/sgchinese-dictionary/telegram-bot/venv/bin/python bot.py
Restart=on-failure
RestartSec=5
EnvironmentFile=/home/<your-username>/sgchinese-dictionary/telegram-bot/.env

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable sgchinese-bot
sudo systemctl start sgchinese-bot
sudo systemctl status sgchinese-bot
```

---

## Updating the bot

```bash
tmux attach -t bot
# Ctrl-C to stop the bot
git pull
source venv/bin/activate
pip install -r requirements.txt   # in case dependencies changed
python bot.py
# Ctrl-B, D to detach
```

---

## File structure

```
telegram-bot/
├── bot.py           # Main bot — event handlers and message formatting
├── search.py        # Supabase search logic (ported from the website API)
├── database.py      # SQLite session storage (sort preference, active query, page)
├── config.py        # Loads settings from .env
├── requirements.txt
├── .env.example     # Template — copy to .env and fill in
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

---

## Architecture notes

- **Session state** is stored in `bot_data.db` (SQLite via `aiosqlite`). Each user row holds their last query, sort preference, current page, and total result count. This lets the ◀ / ▶ buttons work correctly across messages.
- **Search** fans out to all 23 Supabase tables in parallel using `asyncio.to_thread`, then merges, deduplicates, sorts, and paginates the combined results in-process — matching the behaviour of the website API exactly.
- The bot session file (`sgchinese_bot.session`) is created on first run by Telethon and is excluded from Git via `.gitignore`.
