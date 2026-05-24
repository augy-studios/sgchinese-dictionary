#!/usr/bin/env python3
"""SG Chinese Dictionary - Telegram bot (DM-only)."""

import asyncio
import logging

from telethon import TelegramClient, events, Button
from telethon.errors import MessageNotModifiedError

import config
from database import init_db, get_session, save_session
from search import do_search_query

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

bot = TelegramClient("sgchinese_bot", config.API_ID, config.API_HASH)

# ── Constants ─────────────────────────────────────────────────────────────────

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

# ── Formatting ────────────────────────────────────────────────────────────────

def _format_results(
    results: list[dict],
    total: int,
    query: str,
    sort: str,
    page: int,
    query_type: str,
) -> str:
    per_page = config.RESULTS_PER_PAGE
    total_pages = max(1, (total + per_page - 1) // per_page)
    sort_label = SORT_LABELS.get(sort, "Pinyin A → Z")
    type_label = QUERY_TYPE_LABELS.get(query_type, "")

    if not results:
        return f"❌ No results found for **{query}**"

    header = f"🔍 **{total}** result{'s' if total != 1 else ''}"
    if query:
        header += f" for **{query}**"
        if type_label:
            header += f" ({type_label})"
    header += f"\nPage {page + 1} / {total_pages}  ·  {sort_label}"

    lines = [header]
    for row in results:
        lines.append(f"\n**{row['chinese']}** - {row['hanyupinyin']}")
        lines.append(row["translation"])

    return "\n".join(lines)


def _build_nav_keyboard(page: int, total: int, sort: str) -> list[list] | None:
    if total == 0:
        return None
    per_page = config.RESULTS_PER_PAGE
    total_pages = max(1, (total + per_page - 1) // per_page)

    nav: list = []
    if page > 0:
        nav.append(Button.inline("◀ Prev", data=f"p:{page - 1}"))
    nav.append(Button.inline(f"{page + 1} / {total_pages}", data="noop"))
    if page < total_pages - 1:
        nav.append(Button.inline("Next ▶", data=f"p:{page + 1}"))

    sort_row = [Button.inline(f"⇅  {SORT_LABELS.get(sort, 'Sort')}", data="so")]

    return [nav, sort_row]


# ── Core search helper ────────────────────────────────────────────────────────

async def _deliver_results(
    target,
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
        await (target.edit(msg) if edit else target.respond(msg))
        return

    results   = data["results"]
    total     = data["total"]
    query_type = data["query_type"]

    await save_session(user_id, query=query, sort=sort, page=page, total=total)

    text    = _format_results(results, total, query, sort, page, query_type)
    buttons = _build_nav_keyboard(page, total, sort)

    if edit:
        try:
            await target.edit(text, buttons=buttons, parse_mode="md")
        except MessageNotModifiedError:
            await target.answer()
    else:
        await target.respond(text, buttons=buttons, parse_mode="md")


# ── Message handlers ──────────────────────────────────────────────────────────

@bot.on(events.NewMessage(func=lambda e: not e.is_private))
async def _reject_non_dm(_event):
    # Silently discard anything outside DMs
    pass


@bot.on(events.NewMessage(pattern="/start$", func=lambda e: e.is_private))
async def cmd_start(event):
    await event.respond(
        "👋 **Welcome to SG Chinese Dictionary!**\n\n"
        "Just type any word to search - no command needed.\n\n"
        "**Search by:**\n"
        "• Chinese characters: `吃饭`\n"
        "• Pinyin (tones optional): `chī fàn` or `chi fan`\n"
        "• English meaning: `eat rice`\n\n"
        "Use /help for full usage details.",
        parse_mode="md",
    )


@bot.on(events.NewMessage(pattern="/help$", func=lambda e: e.is_private))
async def cmd_help(event):
    await event.respond(
        "**SG Chinese Dictionary - Help**\n\n"
        "**Searching:**\n"
        "Type anything to search. The bot auto-detects your input type:\n"
        "• **Chinese** - type Chinese characters (e.g. `好`)\n"
        "• **Pinyin** - with or without tone marks (`hǎo` or `hao`)\n"
        "• **English** - type an English word (`good`)\n\n"
        "**Browsing results:**\n"
        "• ◀ / ▶ - previous / next page\n"
        "• ⇅ Sort - change sort order\n\n"
        "**Commands:**\n"
        "/start - Welcome message\n"
        "/sort  - Set default sort order\n"
        "/about - About this dictionary",
        parse_mode="md",
    )


@bot.on(events.NewMessage(pattern="/about$", func=lambda e: e.is_private))
async def cmd_about(event):
    await event.respond(
        "**SG Chinese Dictionary**\n\n"
        "A dictionary of Chinese words and phrases, including Mandarin "
        "and usage common in Singapore.",
        parse_mode="md",
    )


@bot.on(events.NewMessage(pattern="/sort$", func=lambda e: e.is_private))
async def cmd_sort(event):
    user_id = event.sender_id
    session = await get_session(user_id)
    current = session.get("sort", "hypy_asc")
    buttons = [
        [Button.inline(("✓  " if k == current else "     ") + label, data=f"sp:{k}")]
        for k, label in SORT_OPTIONS
    ]
    await event.respond(
        "**Choose sort order:**\nApplies to your next search.",
        buttons=buttons,
        parse_mode="md",
    )


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


# ── Callback query handlers ───────────────────────────────────────────────────

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
    buttons = [
        [Button.inline(("✓  " if k == current else "     ") + label, data=f"s:{k}")]
        for k, label in SORT_OPTIONS
    ]
    buttons.append([Button.inline("✕  Cancel", data="sc")])
    await event.answer()
    await event.edit("**Choose sort order:**", buttons=buttons, parse_mode="md")


@bot.on(events.CallbackQuery(pattern=rb"^s:.+$"))
async def cb_sort_select(event):
    """Sort selected from the inline sort menu (within an active search)."""
    if not event.is_private:
        await event.answer("This bot only works in DMs.", alert=True)
        return
    sort    = event.data.decode().split(":", 1)[1]
    user_id = event.sender_id
    session = await get_session(user_id)
    if not session.get("query"):
        # No active search - just persist preference and confirm
        await save_session(user_id, sort=sort)
        label = SORT_LABELS.get(sort, sort)
        await event.answer(f"Sort set to: {label}")
        await event.edit(
            f"✓ Sort order set to **{label}**.\n\nSearch for a word to see results.",
            parse_mode="md",
        )
        return
    await event.answer(f"Sort: {SORT_LABELS.get(sort, sort)}")
    await _deliver_results(event, user_id, session["query"], sort, 0, edit=True)


@bot.on(events.CallbackQuery(data=b"sc"))
async def cb_sort_cancel(event):
    """Cancel sort menu - restore previous search results."""
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
    """Sort selected from the /sort command (may or may not have an active search)."""
    if not event.is_private:
        await event.answer("This bot only works in DMs.", alert=True)
        return
    sort    = event.data.decode().split(":", 1)[1]
    user_id = event.sender_id
    session = await get_session(user_id)
    label   = SORT_LABELS.get(sort, sort)
    await event.answer(f"Sort set to: {label}")
    if session.get("query"):
        # Re-run active search with the new sort
        await _deliver_results(event, user_id, session["query"], sort, 0, edit=True)
    else:
        await save_session(user_id, sort=sort)
        # Refresh the sort menu to reflect the new selection
        buttons = [
            [Button.inline(("✓  " if k == sort else "     ") + lbl, data=f"sp:{k}")]
            for k, lbl in SORT_OPTIONS
        ]
        await event.edit(
            f"✓ Default sort set to **{label}**.\n\nApplies to your next search.",
            buttons=buttons,
            parse_mode="md",
        )


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    await init_db()
    await bot.start(bot_token=config.BOT_TOKEN)
    logger.info("Bot is running - press Ctrl-C to stop.")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
