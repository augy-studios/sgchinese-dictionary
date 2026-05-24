#!/usr/bin/env python3
"""SG Chinese Dictionary - Discord slash-command bot."""

import asyncio
import logging
import aiohttp

import discord
from discord import app_commands

import config
from database import (
    init_db,
    get_session,
    save_session,
    save_persistent_message,
    update_persistent_message,
    get_all_persistent_messages,
    delete_persistent_message,
)
from search import do_search_query, get_random_entry

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

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

ACCENT_COLOUR = discord.Colour(0xE84C30)

ZENQUOTES_URL = "https://zenquotes.io/api/random"

# ── Bot setup (declared early so views can reference client)

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ── Embed builders

def build_results_embed(
    results: list[dict],
    total: int,
    query: str,
    sort: str,
    page: int,
    query_type: str,
) -> discord.Embed:
    per_page = config.RESULTS_PER_PAGE
    total_pages = max(1, (total + per_page - 1) // per_page)
    sort_label = SORT_LABELS.get(sort, "Pinyin A → Z")
    type_label = QUERY_TYPE_LABELS.get(query_type, "")

    if not results:
        return discord.Embed(
            title="No Results",
            description=f"No results found for **{discord.utils.escape_markdown(query)}**.",
            colour=discord.Colour.red(),
        )

    count_word = "result" if total == 1 else "results"
    type_suffix = f"  ({type_label})" if type_label else ""
    title = f"🔍  {total} {count_word} for \"{query}\"{type_suffix}"

    lines: list[str] = []
    for row in results:
        lines.append(f"**{row['chinese']}** · *{row['hanyupinyin']}*")
        lines.append(row["translation"])
        lines.append("")

    embed = discord.Embed(
        title=title,
        description="\n".join(lines).rstrip(),
        colour=ACCENT_COLOUR,
    )
    embed.set_footer(text=f"Page {page + 1} / {total_pages}  ·  Sorted by {sort_label}")
    return embed


# ── Persistent button helpers

class _NavButton(discord.ui.Button):
    """Prev / Next / indicator button for PersistentSearchView."""

    def __init__(self, action: str, **kwargs):
        super().__init__(**kwargs)
        self._action = action

    async def callback(self, interaction: discord.Interaction):
        view: PersistentSearchView = self.view  # type: ignore[assignment]
        if self._action == "prev":
            await view.go_prev(interaction)
        elif self._action == "next":
            await view.go_next(interaction)
        elif self._action == "sort":
            await view.open_sort(interaction)


class _SortOptionButton(discord.ui.Button):
    """One sort-order choice inside PersistentSortView."""

    def __init__(self, key: str, option_label: str, is_current: bool, custom_id: str, row: int):
        super().__init__(
            label=("✓  " if is_current else "      ") + option_label,
            style=discord.ButtonStyle.success if is_current else discord.ButtonStyle.secondary,
            custom_id=custom_id,
            row=row,
        )
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        view: PersistentSortView = self.view  # type: ignore[assignment]
        await view.handle_select(interaction, self.key)


class _SortCancelButton(discord.ui.Button):
    def __init__(self, custom_id: str):
        super().__init__(
            label="✕  Cancel",
            style=discord.ButtonStyle.danger,
            custom_id=custom_id,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        view: PersistentSortView = self.view  # type: ignore[assignment]
        await view.handle_cancel(interaction)


# ── Views

class PersistentSearchView(discord.ui.View):
    """Paginated search results — never expires, survives bot restarts."""

    def __init__(self, message_id: int, user_id: int, query: str, sort: str, page: int, total: int):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.user_id = user_id
        self.query = query
        self.sort = sort
        self.page = page
        self.total = total

        per_page = config.RESULTS_PER_PAGE
        total_pages = max(1, (total + per_page - 1) // per_page)
        mid = str(message_id)

        prev_btn = _NavButton(
            "prev",
            label="◀  Prev",
            style=discord.ButtonStyle.secondary,
            disabled=(page <= 0),
            custom_id=f"sv_prev_{mid}",
            row=0,
        )
        self.add_item(prev_btn)

        self.add_item(_NavButton(
            "indicator",
            label=f"{page + 1} / {total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            custom_id=f"sv_page_{mid}",
            row=0,
        ))

        next_btn = _NavButton(
            "next",
            label="Next  ▶",
            style=discord.ButtonStyle.secondary,
            disabled=(page >= total_pages - 1),
            custom_id=f"sv_next_{mid}",
            row=0,
        )
        self.add_item(next_btn)

        sort_btn = _NavButton(
            "sort",
            label=f"⇅  {SORT_LABELS.get(sort, 'Sort')}",
            style=discord.ButtonStyle.primary,
            custom_id=f"sv_sort_{mid}",
            row=1,
        )
        self.add_item(sort_btn)

    async def go_prev(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your search!", ephemeral=True)
            return
        await self._navigate(interaction, self.page - 1)

    async def go_next(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your search!", ephemeral=True)
            return
        await self._navigate(interaction, self.page + 1)

    async def open_sort(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your search!", ephemeral=True)
            return
        embed = discord.Embed(
            title="⇅  Choose Sort Order",
            description="Results will re-sort immediately after selection.",
            colour=ACCENT_COLOUR,
        )
        view = PersistentSortView(
            self.message_id, self.user_id, self.sort,
            query=self.query, page=self.page,
        )
        client.add_view(view, message_id=self.message_id)
        await interaction.response.edit_message(embed=embed, view=view)
        self.stop()

    async def _navigate(self, interaction: discord.Interaction, new_page: int):
        offset = new_page * config.RESULTS_PER_PAGE
        try:
            data = await do_search_query(
                self.query, sort=self.sort,
                offset=offset, limit=config.RESULTS_PER_PAGE,
            )
        except Exception as exc:
            logger.error("Page navigation error: %s", exc)
            await interaction.response.send_message("⚠️ Failed to load page.", ephemeral=True)
            return

        await save_session(self.user_id, query=self.query, sort=self.sort, page=new_page, total=data["total"])
        await update_persistent_message(self.message_id, page=new_page, total=data["total"])

        embed = build_results_embed(
            data["results"], data["total"],
            self.query, self.sort, new_page, data["query_type"],
        )
        new_view = PersistentSearchView(
            self.message_id, self.user_id, self.query, self.sort, new_page, data["total"]
        )
        client.add_view(new_view, message_id=self.message_id)
        await interaction.response.edit_message(embed=embed, view=new_view)
        self.stop()


class PersistentSortView(discord.ui.View):
    """Sort-order picker — never expires, survives bot restarts."""

    def __init__(
        self,
        message_id: int,
        user_id: int,
        current_sort: str,
        *,
        query: str,
        page: int,
    ):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.user_id = user_id
        self.current_sort = current_sort
        self.query = query
        self.page = page

        mid = str(message_id)
        for idx, (key, label) in enumerate(SORT_OPTIONS):
            self.add_item(_SortOptionButton(
                key, label, key == current_sort,
                custom_id=f"sv_so_{key}_{mid}",
                row=idx // 2,
            ))
        self.add_item(_SortCancelButton(custom_id=f"sv_sc_{mid}"))

    async def handle_select(self, interaction: discord.Interaction, key: str):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return

        await save_session(self.user_id, sort=key)

        offset = self.page * config.RESULTS_PER_PAGE
        try:
            data = await do_search_query(
                self.query, sort=key, offset=offset, limit=config.RESULTS_PER_PAGE
            )
        except Exception as exc:
            logger.error("Sort re-search error: %s", exc)
            await interaction.response.send_message("⚠️ Search failed.", ephemeral=True)
            return

        new_total = data["total"]
        await save_session(self.user_id, query=self.query, sort=key, page=self.page, total=new_total)
        await update_persistent_message(self.message_id, sort=key, page=self.page, total=new_total)

        embed = build_results_embed(
            data["results"], new_total, self.query, key, self.page, data["query_type"]
        )
        new_view = PersistentSearchView(
            self.message_id, self.user_id, self.query, key, self.page, new_total
        )
        client.add_view(new_view, message_id=self.message_id)
        await interaction.response.edit_message(embed=embed, view=new_view)
        self.stop()

    async def handle_cancel(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return

        offset = self.page * config.RESULTS_PER_PAGE
        try:
            data = await do_search_query(
                self.query, sort=self.current_sort, offset=offset, limit=config.RESULTS_PER_PAGE,
            )
        except Exception as exc:
            logger.error("Sort cancel restore error: %s", exc)
            await interaction.response.defer()
            return

        embed = build_results_embed(
            data["results"], data["total"],
            self.query, self.current_sort, self.page, data["query_type"],
        )
        new_view = PersistentSearchView(
            self.message_id, self.user_id, self.query, self.current_sort, self.page, data["total"]
        )
        client.add_view(new_view, message_id=self.message_id)
        await interaction.response.edit_message(embed=embed, view=new_view)
        self.stop()


class StandaloneSortView(discord.ui.View):
    """Sort-order picker for /sort command (no active search context)."""

    def __init__(self, message_id: int, user_id: int, current_sort: str):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.user_id = user_id
        self.current_sort = current_sort

        mid = str(message_id)
        for idx, (key, label) in enumerate(SORT_OPTIONS):
            is_cur = key == current_sort
            btn = _SortOptionButton(
                key, label, is_cur,
                custom_id=f"ss_so_{key}_{mid}",
                row=idx // 2,
            )
            # Override callback to use standalone handler
            original_cb = btn.callback

            async def _cb(interaction: discord.Interaction, _key=key, _label=label):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                    return
                await save_session(self.user_id, sort=_key)
                embed = discord.Embed(
                    title="✓  Sort Order Updated",
                    description=(
                        f"Default sort set to **{_label}**.\n"
                        "Applies to your next `/search`."
                    ),
                    colour=discord.Colour.green(),
                )
                await interaction.response.edit_message(embed=embed, view=None)
                self.stop()

            btn.callback = _cb
            self.add_item(btn)

        cancel = discord.ui.Button(
            label="✕  Cancel",
            style=discord.ButtonStyle.danger,
            custom_id=f"ss_sc_{mid}",
            row=2,
        )

        async def _cancel(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                return
            await interaction.response.edit_message(view=None)
            self.stop()

        cancel.callback = _cancel
        self.add_item(cancel)


# ── Events

async def _update_presence():
    guild_count = len(client.guilds)
    await client.change_presence(
        activity=discord.Game(name=f"SG Chinese words with {guild_count} guild{'s' if guild_count != 1 else ''}")
    )


@client.event
async def on_ready():
    await init_db()
    await tree.sync()
    await _update_presence()
    logger.info("Logged in as %s  (ID: %s)", client.user, client.user.id)
    logger.info("Slash commands synced globally.")
    asyncio.create_task(_restore_persistent_views())


@client.event
async def on_guild_join(guild: discord.Guild):
    await _update_presence()


@client.event
async def on_guild_remove(guild: discord.Guild):
    await _update_presence()


async def _restore_persistent_views():
    messages = await get_all_persistent_messages()
    if not messages:
        return

    logger.info("Restoring %d persistent search view(s)…", len(messages))
    restored = 0

    for msg_data in messages:
        await asyncio.sleep(0.5)  # stay well under Discord rate limits
        mid = msg_data["message_id"]
        try:
            channel = client.get_channel(msg_data["channel_id"])
            if channel is None:
                channel = await client.fetch_channel(msg_data["channel_id"])

            message = await channel.fetch_message(mid)

            data = await do_search_query(
                msg_data["query"],
                sort=msg_data["sort"],
                offset=msg_data["page"] * config.RESULTS_PER_PAGE,
                limit=config.RESULTS_PER_PAGE,
            )
            embed = build_results_embed(
                data["results"], data["total"],
                msg_data["query"], msg_data["sort"],
                msg_data["page"], data["query_type"],
            )
            view = PersistentSearchView(
                mid,
                msg_data["user_id"],
                msg_data["query"],
                msg_data["sort"],
                msg_data["page"],
                data["total"],
            )
            client.add_view(view, message_id=mid)
            await message.edit(embed=embed, view=view)
            restored += 1

        except discord.NotFound:
            logger.info("Message %s deleted — removing from DB.", mid)
            await delete_persistent_message(mid)
        except discord.Forbidden:
            logger.warning("No access to message %s — removing from DB.", mid)
            await delete_persistent_message(mid)
        except Exception as exc:
            logger.error("Failed to restore view for message %s: %s", mid, exc)

    logger.info("Restored %d / %d persistent view(s).", restored, len(messages))


# ── Commands

@tree.command(name="help", description="Show usage guide and all available commands")
async def cmd_help(interaction: discord.Interaction):
    embed = discord.Embed(title="SG Chinese Dictionary - Help", colour=ACCENT_COLOUR)
    embed.add_field(
        name="Searching",
        value=(
            "Use `/search <query>` to look up words. Input is auto-detected:\n"
            "• **Chinese characters** - e.g. `好`, `吃饭`\n"
            "• **Pinyin** - with or without tone marks (`hǎo` or `hao`)\n"
            "• **English** - any English word (`good`, `eat rice`)"
        ),
        inline=False,
    )
    embed.add_field(
        name="Navigating results",
        value=(
            "**◀ Prev** / **Next ▶** - browse pages\n"
            "**⇅ Sort** - change sort order (takes effect immediately)"
        ),
        inline=False,
    )
    embed.add_field(
        name="Commands",
        value=(
            "`/search <query>` - Search the dictionary\n"
            "`/sort` - Set your default sort order\n"
            "`/random` - Get a random dictionary entry\n"
            "`/quote` - Get an inspirational learning quote\n"
            "`/about` - About this dictionary\n"
            "`/help` - Show this message"
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed)


@tree.command(name="about", description="About the SG Chinese Dictionary")
async def cmd_about(interaction: discord.Interaction):
    embed = discord.Embed(
        title="SG Chinese Dictionary",
        description=(
            "A dictionary of Chinese words and phrases, including Mandarin "
            "and usage common in Singapore.\n\n"
            "[Visit the website](https://sgchinesedictionary.com)"
        ),
        colour=ACCENT_COLOUR,
    )
    await interaction.response.send_message(embed=embed)


@tree.command(
    name="search",
    description="Search the dictionary by Chinese characters, Pinyin, or English",
)
@app_commands.describe(query="Word or phrase to look up")
async def cmd_search(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    user_id = interaction.user.id
    session = await get_session(user_id)
    sort = session.get("sort", "hypy_asc")
    query = query.strip()

    try:
        data = await do_search_query(query, sort=sort, offset=0, limit=config.RESULTS_PER_PAGE)
    except Exception as exc:
        logger.error("Search error for user %s: %s", user_id, exc)
        await interaction.followup.send(
            "⚠️ Search failed. Please try again later.", ephemeral=True
        )
        return

    results    = data["results"]
    total      = data["total"]
    query_type = data["query_type"]

    await save_session(user_id, query=query, sort=sort, page=0, total=total)

    embed = build_results_embed(results, total, query, sort, 0, query_type)

    if total > 0:
        msg = await interaction.followup.send(embed=embed)
        view = PersistentSearchView(msg.id, user_id, query, sort, 0, total)
        client.add_view(view, message_id=msg.id)
        await msg.edit(view=view)
        await save_persistent_message(msg.id, interaction.channel_id, user_id, query, sort, 0, total)
    else:
        await interaction.followup.send(embed=embed)


@tree.command(name="sort", description="Set your default sort order for search results")
async def cmd_sort(interaction: discord.Interaction):
    await interaction.response.defer()
    session = await get_session(interaction.user.id)
    current = session.get("sort", "hypy_asc")
    embed = discord.Embed(
        title="⇅  Set Default Sort Order",
        description="Your chosen order applies to all future `/search` results.",
        colour=ACCENT_COLOUR,
    )
    msg = await interaction.followup.send(embed=embed)
    view = StandaloneSortView(msg.id, interaction.user.id, current)
    client.add_view(view, message_id=msg.id)
    await msg.edit(view=view)


def _build_random_embed(entry: dict) -> discord.Embed:
    embed = discord.Embed(title="🎲  Random Entry", colour=ACCENT_COLOUR)
    embed.add_field(name="Chinese",     value=entry["chinese"],      inline=True)
    embed.add_field(name="Pinyin",      value=entry["hanyupinyin"],  inline=True)
    embed.add_field(name="Translation", value=entry["translation"],  inline=False)
    return embed


class RandomView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎲  New Random Word", style=discord.ButtonStyle.primary, custom_id="random_reroll")
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            entry = await get_random_entry()
        except Exception as exc:
            logger.error("Random entry error: %s", exc)
            await interaction.followup.send("⚠️ Couldn't fetch a random entry.", ephemeral=True)
            return

        if not entry:
            await interaction.followup.send("⚠️ No entries found. Try again.", ephemeral=True)
            return

        await interaction.edit_original_response(embed=_build_random_embed(entry))


@tree.command(name="random", description="Get a random entry from the dictionary")
async def cmd_random(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        entry = await get_random_entry()
    except Exception as exc:
        logger.error("Random entry error: %s", exc)
        await interaction.followup.send(
            "⚠️ Couldn't fetch a random entry.", ephemeral=True
        )
        return

    if not entry:
        await interaction.followup.send(
            "⚠️ No entries found. Try again.", ephemeral=True
        )
        return

    view = RandomView()
    client.add_view(view)
    await interaction.followup.send(embed=_build_random_embed(entry), view=view)


@tree.command(name="quote", description="Get an inspirational quote about learning")
async def cmd_quote(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                ZENQUOTES_URL,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        quote  = data[0]["q"]
        author = data[0]["a"]
    except Exception as exc:
        logger.error("Quote fetch error: %s", exc)
        await interaction.followup.send(
            "⚠️ Couldn't fetch a quote right now. Try again later.", ephemeral=True
        )
        return

    embed = discord.Embed(
        description=f"*\"{quote}\"*",
        colour=ACCENT_COLOUR,
    )
    embed.set_footer(text=f"- {author}")
    await interaction.followup.send(embed=embed)


# ── Entry point

if __name__ == "__main__":
    client.run(config.DISCORD_TOKEN, log_handler=None)
