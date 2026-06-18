from __future__ import annotations
import base64
from dataclasses import dataclass
from typing import Any


@dataclass
class Page:
    items: list[Any]
    next_cursor: str | None   # None means no more pages
    total: int | None = None  # optional total count


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode()


def decode_cursor(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode()).decode()


def paginate_list(items: list[Any], limit: int, cursor_field: str = "id") -> Page:
    """
    Given a list already fetched from DB (fetch limit+1 to detect next page),
    return a Page with next_cursor set if there are more items.
    items should be dicts or objects with a cursor_field attribute/key.
    """
    has_more = len(items) > limit
    page_items = items[:limit]
    next_cursor = None
    if has_more:
        last = page_items[-1]
        val = last[cursor_field] if isinstance(last, dict) else getattr(last, cursor_field)
        next_cursor = encode_cursor(str(val))
    return Page(items=page_items, next_cursor=next_cursor)
