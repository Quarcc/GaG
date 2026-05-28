"""
watchlist_manager.py
──────────────────────────────────────────────────────────────
Handles per-user watchlists stored as JSON files.
Each chat_id gets its own watchlist_{chat_id}.json in the
project root.

Also handles items_db.json for validation and search.
"""

import json
import os
import difflib

WATCHLIST_DIR  = os.path.dirname(os.path.abspath(__file__))
ITEMS_DB_PATH  = os.path.join(WATCHLIST_DIR, "items_db.json")

# ─── Items DB ─────────────────────────────────────────────────

def load_items_db() -> dict:
    try:
        with open(ITEMS_DB_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def all_items_flat() -> list[str]:
    """Returns every item name in the DB as a flat list."""
    db    = load_items_db()
    items = []
    for category, value in db.items():
        if isinstance(value, dict):
            for rarity, names in value.items():
                items.extend(names)
        elif isinstance(value, list):
            items.extend(value)
    return items


def find_item(query: str) -> str | None:
    """
    Case-insensitive exact match first, then closest fuzzy match.
    Returns the canonical name or None if no good match found.
    """
    all_items = all_items_flat()

    # Exact match (case-insensitive)
    for item in all_items:
        if item.lower() == query.lower():
            return item

    # Fuzzy match — must be at least 70% similar
    matches = difflib.get_close_matches(
        query, all_items, n=1, cutoff=0.7
    )
    return matches[0] if matches else None


def search_items(query: str, limit: int = 8) -> list[str]:
    """
    Returns up to `limit` items whose name contains the query string.
    Case-insensitive substring match, supplemented by fuzzy matching.
    """
    all_items = all_items_flat()
    q         = query.lower()

    # Substring matches first
    results = [i for i in all_items if q in i.lower()]

    # If few results, add fuzzy matches
    if len(results) < 3:
        fuzzy = difflib.get_close_matches(query, all_items, n=limit, cutoff=0.5)
        for f in fuzzy:
            if f not in results:
                results.append(f)

    return results[:limit]


def get_item_rarity(name: str) -> str | None:
    """Returns the rarity string for a seed, or None if not a seed / not found."""
    db = load_items_db()
    seeds = db.get("seeds", {})
    for rarity, names in seeds.items():
        if any(n.lower() == name.lower() for n in names):
            return rarity
    return None

# ─── Watchlist per user ───────────────────────────────────────

def _watchlist_path(chat_id: str) -> str:
    return os.path.join(WATCHLIST_DIR, f"watchlist_{chat_id}.json")


def load_watchlist(chat_id: str) -> list[str]:
    path = _watchlist_path(chat_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_watchlist(chat_id: str, items: list[str]):
    path = _watchlist_path(chat_id)
    with open(path, "w") as f:
        json.dump(items, f, indent=2)


def watchlist_add(chat_id: str, query: str) -> tuple[bool, str]:
    """
    Adds an item to the user's watchlist.
    Returns (success, message).
    """
    canonical = find_item(query)
    if not canonical:
        # Try to suggest close matches
        suggestions = search_items(query, limit=5)
        if suggestions:
            sugg_str = "\n".join(f"  • {s}" for s in suggestions)
            return False, (
                f'❌ <b>"{query}"</b> not found in the item database.\n\n'
                f'Did you mean:\n{sugg_str}\n\n'
                f'Use /watchlist search {query} for more results.'
            )
        return False, (
            f'❌ <b>"{query}"</b> not found in the item database.\n'
            f'Try /watchlist search {query} to look it up.'
        )

    current = load_watchlist(chat_id)
    if any(i.lower() == canonical.lower() for i in current):
        return False, f'⚠️ <b>{canonical}</b> is already in your watchlist.'

    current.append(canonical)
    save_watchlist(chat_id, current)

    rarity = get_item_rarity(canonical)
    rarity_str = f" <i>({rarity})</i>" if rarity else ""
    return True, f'✅ Added <b>{canonical}</b>{rarity_str} to your watchlist.'


def watchlist_remove(chat_id: str, query: str) -> tuple[bool, str]:
    """
    Removes an item from the user's watchlist.
    Returns (success, message).
    """
    current = load_watchlist(chat_id)

    # Find in current watchlist (case-insensitive)
    match = next((i for i in current if i.lower() == query.lower()), None)

    if not match:
        # Check if it exists in DB at all
        canonical = find_item(query)
        if canonical:
            return False, (
                f'⚠️ <b>{canonical}</b> is not in your watchlist.\n'
                f'Use /watchlist to see what you\'re watching.'
            )
        return False, (
            f'❌ <b>"{query}"</b> not found in your watchlist or the item database.\n'
            f'Use /watchlist to see your current list.'
        )

    current.remove(match)
    save_watchlist(chat_id, current)
    return True, f'🗑 Removed <b>{match}</b> from your watchlist.'