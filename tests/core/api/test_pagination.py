from __future__ import annotations
import pytest
from core.api.pagination import encode_cursor, decode_cursor, paginate_list, Page


def test_encode_decode_roundtrip():
    original = "some-uuid-1234"
    assert decode_cursor(encode_cursor(original)) == original


def test_encode_decode_roundtrip_special_chars():
    original = "abc+def/xyz=="
    assert decode_cursor(encode_cursor(original)) == original


def test_paginate_list_fewer_than_limit_returns_no_cursor():
    items = [{"id": str(i)} for i in range(3)]
    page = paginate_list(items, limit=10)
    assert page.next_cursor is None
    assert len(page.items) == 3


def test_paginate_list_exact_limit_returns_no_cursor():
    items = [{"id": str(i)} for i in range(10)]
    page = paginate_list(items, limit=10)
    assert page.next_cursor is None
    assert len(page.items) == 10


def test_paginate_list_more_than_limit_returns_cursor():
    # Caller passes limit+1 items to detect next page
    items = [{"id": str(i)} for i in range(11)]
    page = paginate_list(items, limit=10)
    assert page.next_cursor is not None
    assert len(page.items) == 10  # capped at limit
    assert decode_cursor(page.next_cursor) == "9"  # last item in page_items


def test_paginate_list_cursor_encodes_last_item_id():
    items = [{"id": f"item-{i}"} for i in range(6)]
    page = paginate_list(items, limit=5)
    assert page.next_cursor is not None
    assert decode_cursor(page.next_cursor) == "item-4"


def test_paginate_list_with_dicts():
    items = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    page = paginate_list(items, limit=2)
    assert page.next_cursor is not None
    assert decode_cursor(page.next_cursor) == "b"
    assert len(page.items) == 2


class FakeObj:
    def __init__(self, id_val):
        self.id = id_val


def test_paginate_list_with_objects():
    items = [FakeObj(f"obj-{i}") for i in range(4)]
    page = paginate_list(items, limit=3)
    assert page.next_cursor is not None
    assert decode_cursor(page.next_cursor) == "obj-2"
    assert len(page.items) == 3


def test_paginate_list_custom_cursor_field():
    items = [{"name": f"x-{i}"} for i in range(4)]
    page = paginate_list(items, limit=3, cursor_field="name")
    assert page.next_cursor is not None
    assert decode_cursor(page.next_cursor) == "x-2"


def test_page_dataclass_total_defaults_none():
    page = Page(items=[], next_cursor=None)
    assert page.total is None
