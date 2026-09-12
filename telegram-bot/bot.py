#!/usr/bin/env python3
"""SG Chinese Dictionary - Telegram bot (DM-only)."""

import asyncio
import logging
import re

from telethon import TelegramClient, events, Button

import config
from database import init_db, get_session, save_session
from reply import send_rich_message, edit_rich_message, edit_rich_message_at
from search import do_search_query, get_random_entry

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

bot = TelegramClient("sgchinese_bot", config.API_ID, config.API_HASH)

# ── Constants

SORT_OPTIONS: list[tuple[str, str]] = [
    ("hypy_asc",  "Pinyin A → Z"),
    ("hypy_desc", "Pinyin Z → A"),
    ("en_asc",    "English A → Z"),
    ("en_desc",   "English Z → A"),
]
SORT_LABELS: dict[str, str] = dict(SORT_OPTIONS)

QUERY_TYPE_LABELS: dict[str, str] = {
    "chinese":   "Chinese characters",
    "pinyin":    "Pinyin",
    "ambiguous": "Pinyin / English",
    "all":       "all entries",
}

# ── Rich Markdown escaping

_MD_SPECIAL = re.compile(r"([\\*_~`|\[\]#>=])")


def escape_md(text) -> str:
    """Escape user/data text for Telegram's Rich Markdown dialect."""
    return _MD_SPECIAL.sub(r"\\\1", str(text))


def escape_cell(text) -> str:
    """Escape for a GFM table cell; also flattens newlines so the row stays intact."""
    return escape_md(str(text).replace("\n", " "))


def md_table(headers: list[str], rows: list[list]) -> str:
    """Render a GFM pipe table. Headers are literal; cell values are escaped."""
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(escape_cell(v) for v in row) + " |")
    return "\n".join(lines)


def _plain_cell(text) -> str:
    return str(text).replace("\n", " ")


# ── View builders  (each returns (rich, buttons))

def _sort_keyboard(current: str, prefix: str) -> list[list]:
    return [
        [Button.inline(("✓  " if k == current else "     ") + label, data=f"{prefix}:{k}")]
        for k, label in SORT_OPTIONS
    ]


def build_results(
    results: list[dict],
    total: int,
    query: str,
    sort: str,
    page: int,
    query_type: str,
) -> tuple[dict, list[list] | None]:
    per_page = config.RESULTS_PER_PAGE
    total_pages = max(1, (total + per_page - 1) // per_page)
    sort_label = SORT_LABELS.get(sort, "Pinyin A → Z")
    type_label = QUERY_TYPE_LABELS.get(query_type, "")

    title = f"🔍 {total} result{'s' if total != 1 else ''}"
    if query:
        title += f" for {query}"
        if type_label:
            title += f" ({type_label})"
    meta = f"Page {page + 1} / {total_pages}  ·  {sort_label}"

    md_title = f"🔍 {total} result{'s' if total != 1 else ''}"
    if query:
        md_title += f" for **{escape_md(query)}**"
        if type_label:
            md_title += f" ({type_label})"

    markdown = "\n".join([
        f"# {md_title}",
        meta,
        "",
        md_table(
            ["Chinese", "Pinyin", "Translation"],
            [[row["chinese"], row["hanyupinyin"], row["translation"]] for row in results],
        ),
    ])

    fallback_lines = [title, meta]
    for row in results:
        fallback_lines.append(
            f"\n{_plain_cell(row['chinese'])} - {_plain_cell(row['hanyupinyin'])}"
        )
        fallback_lines.append(_plain_cell(row["translation"]))

    rich = {"markdown": markdown, "fallback": "\n".join(fallback_lines)}

    nav: list = []
    if page > 0:
        nav.append(Button.inline("◀ Prev", data=f"p:{page - 1}"))
    nav.append(Button.inline(f"{page + 1} / {total_pages}", data="noop"))
    if page < total_pages - 1:
        nav.append(Button.inline("Next ▶", data=f"p:{page + 1}"))
    sort_row = [Button.inline(f"⇅  {sort_label}", data="so")]

    return rich, [nav, sort_row]


def build_random(entry: dict) -> tuple[dict, list[list]]:
    chinese = entry["chinese"]
    pinyin = entry["hanyupinyin"]
    translation = entry["translation"]
    rich = {
        "markdown": "\n".join([
            "# 🎲 Random word",
            "",
            md_table(["Chinese", "Pinyin", "Translation"], [[chinese, pinyin, translation]]),
        ]),
        "fallback": (
            f"🎲 Random word\n\n"
            f"{_plain_cell(chinese)} - {_plain_cell(pinyin)}\n"
            f"{_plain_cell(translation)}"
        ),
    }
    return rich, [[Button.inline("🎲 Another random word", data="rand")]]


def build_start() -> tuple[dict, list[list]]:
    rich = {
        "markdown": (
            "# 👋 Welcome to SG Chinese Dictionary!\n\n"
            "Just type any word to search - no command needed.\n\n"
            "## Search by\n"
            "- Chinese characters: `吃饭`\n"
            "- Pinyin (tones optional): `chī fàn` or `chi fan`\n"
            "- English meaning: `eat rice`\n\n"
            "Use /help for full usage details."
        ),
        "fallback": (
            "👋 Welcome to SG Chinese Dictionary!\n\n"
            "Just type any word to search - no command needed.\n\n"
            "Search by:\n"
            "• Chinese characters: 吃饭\n"
            "• Pinyin (tones optional): chī fàn or chi fan\n"
            "• English meaning: eat rice\n\n"
            "Use /help for full usage details."
        ),
    }
    return rich, [[Button.inline("🎲 Random word", data="rand")]]


def build_help() -> tuple[dict, None]:
    commands = [
        ("/start",  "Welcome message"),
        ("/random", "Show a random word"),
        ("/sort",   "Set default sort order"),
        ("/about",  "About this dictionary"),
    ]
    rich = {
        "markdown": "\n".join([
            "# SG Chinese Dictionary - Help",
            "",
            "## Searching",
            "Type anything to search. The bot auto-detects your input type:",
            "- **Chinese** - type Chinese characters (e.g. `好`)",
            "- **Pinyin** - with or without tone marks (`hǎo` or `hao`)",
            "- **English** - type an English word (`good`)",
            "",
            "## Browsing results",
            "- ◀ / ▶ - previous / next page",
            "- ⇅ Sort - change sort order",
            "",
            "## Commands",
            md_table(["Command", "Description"], [list(c) for c in commands]),
        ]),
        "fallback": "\n".join([
            "SG Chinese Dictionary - Help",
            "",
            "Searching:",
            "Type anything to search. The bot auto-detects your input type:",
            "• Chinese - type Chinese characters (e.g. 好)",
            "• Pinyin - with or without tone marks (hǎo or hao)",
            "• English - type an English word (good)",
            "",
            "Browsing results:",
            "• ◀ / ▶ - previous / next page",
            "• ⇅ Sort - change sort order",
            "",
            "Commands:",
            *[f"{cmd}  - {desc}" for cmd, desc in commands],
        ]),
    }
    return rich, None


def build_about() -> tuple[dict, None]:
    body = (
        "A dictionary of Chinese words and phrases, including Mandarin "
        "and usage common in Singapore."
    )
    rich = {
        "markdown": f"# SG Chinese Dictionary\n\n{body}",
        "fallback": f"SG Chinese Dictionary\n\n{body}",
    }
    return rich, None


def build_sort_prompt(current: str, *, prefix: str, cancel: bool) -> tuple[dict, list[list]]:
    """Sort picker. `sp:` sets the default; `s:` re-sorts the active search."""
    note = "Applies to your next search." if prefix == "sp" else ""
    rich = {
        "markdown": "# Choose sort order" + (f"\n{note}" if note else ""),
        "fallback": "Choose sort order" + (f"\n{note}" if note else ""),
    }
    buttons = _sort_keyboard(current, prefix)
    if cancel:
        buttons.append([Button.inline("✕  Cancel", data="sc")])
    return rich, buttons


def build_sort_confirm(sort: str, *, is_default: bool) -> tuple[dict, list[list] | None]:
    label = SORT_LABELS.get(sort, sort)
    if is_default:
        rich = {
            "markdown": f"# ✓ Default sort set to {escape_md(label)}\n\nApplies to your next search.",
            "fallback": f"✓ Default sort set to {label}.\n\nApplies to your next search.",
        }
        return rich, _sort_keyboard(sort, "sp")
    rich = {
        "markdown": f"# ✓ Sort order set to {escape_md(label)}\n\nSearch for a word to see results.",
        "fallback": f"✓ Sort order set to {label}.\n\nSearch for a word to see results.",
    }
    return rich, None


# ── Core search helper

async def _deliver_results(
    event,
    user_id: int,
    query: str,
    sort: str,
    page: int,
    *,
    edit: bool,
) -> None:
    offset = page * config.RESULTS_PER_PAGE
    try:
        data = await do_search_query(query, sort=sort, offset=offset, limit=config.RESULTS_PER_PAGE)
    except Exception as exc:
        logger.error("Search error for user %s: %s", user_id, exc)
        msg = "⚠️ Search failed. Please try again later."
        await (event.edit(msg) if edit else event.respond(msg))
        return

    results   = data["results"]
    total     = data["total"]
    query_type = data["query_type"]

    await save_session(user_id, query=query, sort=sort, page=page, total=total)

    if not results:
        msg = f"❌ No results found for {query}"
        await (event.edit(msg) if edit else event.respond(msg))
        return

    rich, buttons = build_results(results, total, query, sort, page, query_type)

    if edit:
        await edit_rich_message(bot, event, rich, buttons)
    else:
        await send_rich_message(bot, event.chat_id, rich, buttons)


# ── Message handlers

@bot.on(events.NewMessage(func=lambda e: not e.is_private))
async def _reject_non_dm(_event):
    pass


@bot.on(events.NewMessage(pattern="/start$", func=lambda e: e.is_private))
async def cmd_start(event):
    rich, buttons = build_start()
    await send_rich_message(bot, event.chat_id, rich, buttons)


@bot.on(events.NewMessage(pattern="/help$", func=lambda e: e.is_private))
async def cmd_help(event):
    rich, buttons = build_help()
    await send_rich_message(bot, event.chat_id, rich, buttons)


@bot.on(events.NewMessage(pattern="/about$", func=lambda e: e.is_private))
async def cmd_about(event):
    rich, buttons = build_about()
    await send_rich_message(bot, event.chat_id, rich, buttons)


async def _deliver_random(event, *, edit: bool) -> None:
    entry = await get_random_entry()
    if entry is None:
        msg = "⚠️ Could not fetch a random word. Please try again."
        await (event.edit(msg) if edit else event.respond(msg))
        return
    rich, buttons = build_random(entry)
    if edit:
        await edit_rich_message(bot, event, rich, buttons)
    else:
        await send_rich_message(bot, event.chat_id, rich, buttons)


@bot.on(events.NewMessage(pattern="/random$", func=lambda e: e.is_private))
async def cmd_random(event):
    async with bot.action(event.chat_id, "typing"):
        await _deliver_random(event, edit=False)


@bot.on(events.CallbackQuery(data=b"rand"))
async def cb_random(event):
    if not event.is_private:
        await event.answer("This bot only works in DMs.", alert=True)
        return
    await event.answer()
    await _deliver_random(event, edit=True)


@bot.on(events.NewMessage(pattern="/sort$", func=lambda e: e.is_private))
async def cmd_sort(event):
    user_id = event.sender_id
    session = await get_session(user_id)
    current = session.get("sort", "hypy_asc")
    rich, buttons = build_sort_prompt(current, prefix="sp", cancel=False)
    await send_rich_message(bot, event.chat_id, rich, buttons)


@bot.on(events.NewMessage(
    func=lambda e: e.is_private and bool(e.message.text) and not e.message.text.startswith("/")
))
async def handle_search(event):
    query = event.message.text.strip()
    if not query:
        return
    user_id = event.sender_id
    session = await get_session(user_id)
    async with bot.action(event.chat_id, "typing"):
        await _deliver_results(event, user_id, query, session.get("sort", "hypy_asc"), 0, edit=False)


# ── Callback query handlers

@bot.on(events.CallbackQuery(data=b"noop"))
async def cb_noop(event):
    await event.answer()


@bot.on(events.CallbackQuery(pattern=rb"^p:(\d+)$"))
async def cb_page(event):
    if not event.is_private:
        await event.answer("This bot only works in DMs.", alert=True)
        return
    page    = int(event.data.decode().split(":")[1])
    user_id = event.sender_id
    session = await get_session(user_id)
    if not session.get("query"):
        await event.answer("Session expired. Please search again.", alert=True)
        return
    await event.answer()
    await _deliver_results(event, user_id, session["query"], session["sort"], page, edit=True)


@bot.on(events.CallbackQuery(data=b"so"))
async def cb_sort_open(event):
    if not event.is_private:
        await event.answer("This bot only works in DMs.", alert=True)
        return
    user_id = event.sender_id
    session = await get_session(user_id)
    current = session.get("sort", "hypy_asc")
    rich, buttons = build_sort_prompt(current, prefix="s", cancel=True)
    await event.answer()
    await edit_rich_message(bot, event, rich, buttons)


@bot.on(events.CallbackQuery(pattern=rb"^s:.+$"))
async def cb_sort_select(event):
    if not event.is_private:
        await event.answer("This bot only works in DMs.", alert=True)
        return
    sort    = event.data.decode().split(":", 1)[1]
    user_id = event.sender_id
    session = await get_session(user_id)
    if not session.get("query"):
        # no active search - save preference, confirm, and drop the picker keyboard
        await save_session(user_id, sort=sort)
        await event.answer(f"Sort set to: {SORT_LABELS.get(sort, sort)}")
        rich, _ = build_sort_confirm(sort, is_default=False)
        await edit_rich_message_at(bot, event.chat_id, event.query.msg_id, rich)
        return
    await event.answer(f"Sort: {SORT_LABELS.get(sort, sort)}")
    await _deliver_results(event, user_id, session["query"], sort, 0, edit=True)


@bot.on(events.CallbackQuery(data=b"sc"))
async def cb_sort_cancel(event):
    if not event.is_private:
        await event.answer()
        return
    user_id = event.sender_id
    session = await get_session(user_id)
    await event.answer()
    if session.get("query"):
        await _deliver_results(
            event, user_id, session["query"], session["sort"], session.get("page", 0), edit=True
        )
    else:
        await event.delete()


@bot.on(events.CallbackQuery(pattern=rb"^sp:.+$"))
async def cb_sort_pref(event):
    if not event.is_private:
        await event.answer("This bot only works in DMs.", alert=True)
        return
    sort    = event.data.decode().split(":", 1)[1]
    user_id = event.sender_id
    session = await get_session(user_id)
    await event.answer(f"Sort set to: {SORT_LABELS.get(sort, sort)}")
    if session.get("query"):
        await _deliver_results(event, user_id, session["query"], sort, 0, edit=True)
    else:
        await save_session(user_id, sort=sort)
        rich, buttons = build_sort_confirm(sort, is_default=True)
        await edit_rich_message(bot, event, rich, buttons)


# ── Entry point

async def main() -> None:
    await init_db()
    await bot.start(bot_token=config.BOT_TOKEN)
    logger.info("Bot is running - press Ctrl-C to stop.")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
