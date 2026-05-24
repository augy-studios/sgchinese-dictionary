#!/usr/bin/env python3
"""SG Chinese Dictionary - Discord slash-command bot."""

import asyncio
import logging
import aiohttp

import discord
from discord import app_commands

import config
from database import init_db, get_session, save_session
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


# ── Views

class SortView(discord.ui.View):
    """Sort-order picker; re-runs search immediately if query is set."""

    def __init__(
        self,
        user_id: int,
        current: str,
        *,
        query: str | None = None,
        page: int = 0,
    ):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.current = current
        self.query = query
        self.page = page

        for idx, (key, label) in enumerate(SORT_OPTIONS):
            is_cur = key == current
            btn = discord.ui.Button(
                label=("✓  " if is_cur else "      ") + label,
                style=discord.ButtonStyle.success if is_cur else discord.ButtonStyle.secondary,
                row=idx // 2,
            )
            btn.callback = self._make_cb(key, label)
            self.add_item(btn)

        cancel = discord.ui.Button(
            label="✕  Cancel",
            style=discord.ButtonStyle.danger,
            row=2,
        )
        cancel.callback = self.on_cancel
        self.add_item(cancel)

    def _make_cb(self, key: str, label: str):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message(
                    "This isn't your menu!", ephemeral=True
                )
                return

            await save_session(self.user_id, sort=key)

            if self.query is not None:
                offset = self.page * config.RESULTS_PER_PAGE
                try:
                    data = await do_search_query(
                        self.query, sort=key, offset=offset, limit=config.RESULTS_PER_PAGE
                    )
                except Exception as exc:
                    logger.error("Sort re-search error: %s", exc)
                    await interaction.response.send_message(
                        "⚠️ Search failed.", ephemeral=True
                    )
                    return
                await save_session(
                    self.user_id,
                    query=self.query, sort=key, page=self.page, total=data["total"],
                )
                embed = build_results_embed(
                    data["results"], data["total"],
                    self.query, key, self.page, data["query_type"],
                )
                new_view = SearchView(
                    self.user_id, self.query, key, self.page, data["total"]
                )
                await interaction.response.edit_message(embed=embed, view=new_view)
            else:
                embed = discord.Embed(
                    title="✓  Sort Order Updated",
                    description=(
                        f"Default sort set to **{label}**.\n"
                        "Applies to your next `/search`."
                    ),
                    colour=discord.Colour.green(),
                )
                await interaction.response.edit_message(embed=embed, view=None)

            self.stop()

        return cb

    async def on_cancel(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
            return

        if self.query is not None:
            offset = self.page * config.RESULTS_PER_PAGE
            try:
                data = await do_search_query(
                    self.query, sort=self.current,
                    offset=offset, limit=config.RESULTS_PER_PAGE,
                )
            except Exception as exc:
                logger.error("Sort cancel restore error: %s", exc)
                await interaction.response.defer()
                return
            embed = build_results_embed(
                data["results"], data["total"],
                self.query, self.current, self.page, data["query_type"],
            )
            new_view = SearchView(
                self.user_id, self.query, self.current, self.page, data["total"]
            )
            await interaction.response.edit_message(embed=embed, view=new_view)
        else:
            await interaction.response.edit_message(view=None)

        self.stop()


class SearchView(discord.ui.View):
    """Paginated search results with ◀ / ▶ navigation and a sort picker."""

    def __init__(self, user_id: int, query: str, sort: str, page: int, total: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.query = query
        self.sort = sort
        self.page = page
        self.total = total

        per_page = config.RESULTS_PER_PAGE
        total_pages = max(1, (total + per_page - 1) // per_page)

        prev_btn = discord.ui.Button(
            label="◀  Prev",
            style=discord.ButtonStyle.secondary,
            disabled=(page <= 0),
            row=0,
        )
        prev_btn.callback = self.go_prev
        self.add_item(prev_btn)

        self.add_item(discord.ui.Button(
            label=f"{page + 1} / {total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=0,
        ))

        next_btn = discord.ui.Button(
            label="Next  ▶",
            style=discord.ButtonStyle.secondary,
            disabled=(page >= total_pages - 1),
            row=0,
        )
        next_btn.callback = self.go_next
        self.add_item(next_btn)

        sort_btn = discord.ui.Button(
            label=f"⇅  {SORT_LABELS.get(sort, 'Sort')}",
            style=discord.ButtonStyle.primary,
            row=1,
        )
        sort_btn.callback = self.open_sort
        self.add_item(sort_btn)

    async def go_prev(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your search!", ephemeral=True
            )
            return
        await self._navigate(interaction, self.page - 1)

    async def go_next(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your search!", ephemeral=True
            )
            return
        await self._navigate(interaction, self.page + 1)

    async def open_sort(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your search!", ephemeral=True
            )
            return
        embed = discord.Embed(
            title="⇅  Choose Sort Order",
            description="Results will re-sort immediately after selection.",
            colour=ACCENT_COLOUR,
        )
        view = SortView(self.user_id, self.sort, query=self.query, page=self.page)
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
            await interaction.response.send_message(
                "⚠️ Failed to load page.", ephemeral=True
            )
            return

        await save_session(
            self.user_id,
            query=self.query, sort=self.sort, page=new_page, total=data["total"],
        )
        embed = build_results_embed(
            data["results"], data["total"],
            self.query, self.sort, new_page, data["query_type"],
        )
        new_view = SearchView(self.user_id, self.query, self.sort, new_page, data["total"])
        await interaction.response.edit_message(embed=embed, view=new_view)
        self.stop()


# ── Bot setup

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    await init_db()
    await tree.sync()
    logger.info("Logged in as %s  (ID: %s)", client.user, client.user.id)
    logger.info("Slash commands synced globally.")


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
    view  = SearchView(user_id, query, sort, 0, total) if total > 0 else None
    await interaction.followup.send(embed=embed, view=view)


@tree.command(name="sort", description="Set your default sort order for search results")
async def cmd_sort(interaction: discord.Interaction):
    session = await get_session(interaction.user.id)
    current = session.get("sort", "hypy_asc")
    embed = discord.Embed(
        title="⇅  Set Default Sort Order",
        description="Your chosen order applies to all future `/search` results.",
        colour=ACCENT_COLOUR,
    )
    view = SortView(interaction.user.id, current)
    await interaction.response.send_message(embed=embed, view=view)


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

    embed = discord.Embed(title="🎲  Random Entry", colour=ACCENT_COLOUR)
    embed.add_field(name="Chinese",     value=entry["chinese"],      inline=True)
    embed.add_field(name="Pinyin",      value=entry["hanyupinyin"],  inline=True)
    embed.add_field(name="Translation", value=entry["translation"],  inline=False)
    await interaction.followup.send(embed=embed)


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
