import re
import random
import asyncio
from supabase import create_client, Client

import config

AVAILABLE_LETTERS = list("abcdefghjklmnopqrstwxyz")  # no 'i' table

TONE_MAP: dict[str, str] = {
    "ā": "a", "á": "a", "ǎ": "a", "à": "a",
    "ē": "e", "é": "e", "ě": "e", "è": "e",
    "ī": "i", "í": "i", "ǐ": "i", "ì": "i",
    "ō": "o", "ó": "o", "ǒ": "o", "ò": "o",
    "ū": "u", "ú": "u", "ǔ": "u", "ù": "u",
    "ǖ": "v", "ǘ": "v", "ǚ": "v", "ǜ": "v", "ü": "v",
}

ACCENT_CLASS: dict[str, str] = {
    "a": "[aāáǎà]",
    "e": "[eēéěè]",
    "i": "[iīíǐì]",
    "o": "[oōóǒò]",
    "u": "[uūúǔù]",
    "v": "[vüǖǘǚǜ]",
}

_SPECIAL_RE = re.compile(r'[.+*?^${}()|[\]\\]')

_supabase: Client | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _supabase


def normalise_pinyin(s: str) -> str:
    return "".join(TONE_MAP.get(c.lower(), c) for c in s).lower()


def build_pinyin_regex(query: str) -> str:
    norm = normalise_pinyin(query)
    escaped = _SPECIAL_RE.sub(lambda m: "\\" + m.group(), norm)
    return re.sub(r"[aeiouv]", lambda m: ACCENT_CLASS.get(m.group(), m.group()), escaped)


def detect_query_type(q: str) -> str:
    if re.search(r"[一-鿿㐀-䶿]", q):
        return "chinese"
    if re.search(r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü]", q, re.IGNORECASE):
        return "pinyin"
    return "ambiguous"


def _fetch_table_sync(letter: str, query: str, query_type: str) -> list[dict]:
    sb = _get_supabase()
    table = f"sgchn_{letter}"
    try:
        qb = sb.from_(table).select("hanyupinyin, chinese, translation")
        if query_type == "chinese":
            qb = qb.ilike("chinese", f"%{query}%")
        elif query_type == "pinyin":
            qb = qb.filter("hanyupinyin", "imatch", build_pinyin_regex(query))
        elif query_type == "ambiguous":
            pattern = build_pinyin_regex(query)
            qb = qb.or_(f"hanyupinyin.imatch.{pattern},translation.ilike.%{query}%")
        result = qb.execute()
        return result.data or []
    except Exception:
        return []


async def do_search_query(
    query: str,
    sort: str = "hypy_asc",
    offset: int = 0,
    limit: int = 5,
) -> dict:
    query = query.strip()
    query_type = detect_query_type(query) if query else "all"

    sort_map = {
        "hypy_asc":  ("hanyupinyin", True),
        "hypy_desc": ("hanyupinyin", False),
        "en_asc":    ("translation", True),
        "en_desc":   ("translation", False),
    }
    col, asc = sort_map.get(sort, ("hanyupinyin", True))

    tasks = [
        asyncio.to_thread(_fetch_table_sync, letter, query, query_type)
        for letter in AVAILABLE_LETTERS
    ]
    per_table = await asyncio.gather(*tasks)

    all_rows: list[dict] = []
    seen: set[str] = set()
    for rows in per_table:
        for row in rows:
            key = f"{row['chinese']}__{row['hanyupinyin']}"
            if key not in seen:
                seen.add(key)
                all_rows.append(row)

    total = len(all_rows)

    def sort_key(row: dict) -> str:
        val = (row.get(col) or "").lower()
        return normalise_pinyin(val) if col == "hanyupinyin" else val

    all_rows.sort(key=sort_key, reverse=not asc)

    return {
        "results": all_rows[offset : offset + limit],
        "total": total,
        "query_type": query_type,
    }


async def get_random_entry() -> dict | None:
    """Fetch a random entry from a randomly chosen letter table."""
    letter = random.choice(AVAILABLE_LETTERS)
    rows = await asyncio.to_thread(_fetch_table_sync, letter, "", "all")
    if not rows:
        return None
    return random.choice(rows)
