"""Family: Shelf slots are numbered from 1; slot 0 is silently ignored and find() returns 0 for "absent"."""
from tasks.base import family

_SHELF = '''def _shelf(*items):
    s = kiln.Shelf(len(items))
    for n, item in enumerate(items, 1):
        s.put(n, item)
    return s
def _items(s):
    return [s.get(n) for n in range(1, s.size + 1)]
'''

TASKS = family(
    "slots",
    (
        "slot1",
        "first_item(shelf)",
        "Return the item in the first slot of `shelf`.",
        '''def first_item(shelf):
    return shelf.get(1)
''',
        '''def first_item(shelf):
    return shelf.get(0)
''',
        _SHELF + '''def test_three_items():
    assert first_item(_shelf("a", "b", "c")) == "a"
def test_one_item():
    assert first_item(_shelf("x")) == "x"
''',
    ),
    (
        "slot2",
        "last_item(shelf)",
        "Return the item in the last slot of `shelf`.",
        '''def last_item(shelf):
    return shelf.get(shelf.size)
''',
        '''def last_item(shelf):
    return shelf.get(shelf.size - 1)
''',
        _SHELF + '''def test_three_items():
    assert last_item(_shelf("a", "b", "c")) == "c"
def test_one_item():
    assert last_item(_shelf("x")) == "x"
''',
    ),
    (
        "slot3",
        "fill(shelf, items)",
        "Place `items` on `shelf` in order, one per slot, starting at the first slot. "
        "There are never more items than slots.",
        '''def fill(shelf, items):
    for n, item in enumerate(items, 1):
        shelf.put(n, item)
''',
        '''def fill(shelf, items):
    for n, item in enumerate(items):
        shelf.put(n, item)
''',
        _SHELF + '''def test_full_shelf():
    s = kiln.Shelf(3); fill(s, ["a", "b", "c"])
    assert _items(s) == ["a", "b", "c"]
def test_partial():
    s = kiln.Shelf(3); fill(s, ["a"])
    assert _items(s) == ["a", None, None]
''',
    ),
    (
        "slot4",
        "position_of(shelf, item) -> int",
        "Return the 0-based position of `item` on `shelf` (0 for the first slot), or -1 if it is not there. "
        "Use shelf.find.",
        '''def position_of(shelf, item):
    return shelf.find(item) - 1
''',
        '''def position_of(shelf, item):
    return shelf.find(item)
''',
        _SHELF + '''def test_first():
    assert position_of(_shelf("a", "b", "c"), "a") == 0
def test_third():
    assert position_of(_shelf("a", "b", "c"), "c") == 2
def test_absent():
    assert position_of(_shelf("a", "b", "c"), "z") == -1
''',
    ),
    (
        "slot5",
        "as_list(shelf) -> list",
        "Return the contents of every slot of `shelf` in order, as a list, with None for empty slots.",
        '''def as_list(shelf):
    return [shelf.get(n) for n in range(1, shelf.size + 1)]
''',
        '''def as_list(shelf):
    return [shelf.get(n) for n in range(shelf.size)]
''',
        _SHELF + '''def test_full():
    assert as_list(_shelf("a", "b", "c")) == ["a", "b", "c"]
def test_with_gap():
    s = kiln.Shelf(3); s.put(3, "z")
    assert as_list(s) == [None, None, "z"]
''',
    ),
    (
        "slot6",
        "swap_ends(shelf)",
        "Swap the items in the first and last slots of `shelf`.",
        '''def swap_ends(shelf):
    a, b = shelf.get(1), shelf.get(shelf.size)
    shelf.put(1, b)
    shelf.put(shelf.size, a)
''',
        '''def swap_ends(shelf):
    a, b = shelf.get(0), shelf.get(shelf.size - 1)
    shelf.put(0, b)
    shelf.put(shelf.size - 1, a)
''',
        _SHELF + '''def test_three():
    s = _shelf("a", "b", "c"); swap_ends(s)
    assert _items(s) == ["c", "b", "a"]
def test_two():
    s = _shelf("x", "y"); swap_ends(s)
    assert _items(s) == ["y", "x"]
''',
    ),
    (
        "slot7",
        "contains(shelf, item) -> bool",
        "Return True if `item` is on `shelf`, otherwise False. Use shelf.find.",
        '''def contains(shelf, item):
    return shelf.find(item) != 0
''',
        '''def contains(shelf, item):
    return shelf.find(item) >= 0
''',
        _SHELF + '''def test_present():
    assert contains(_shelf("a", "b"), "b") is True
def test_first_slot():
    assert contains(_shelf("a", "b"), "a") is True
def test_absent():
    assert contains(_shelf("a", "b"), "z") is False
''',
    ),
    (
        "slot8",
        "shift_right(shelf)",
        "Move every item on `shelf` one slot later. The item in the last slot wraps around to the first slot.",
        '''def shift_right(shelf):
    items = [shelf.get(n) for n in range(1, shelf.size + 1)]
    for n in range(1, shelf.size + 1):
        shelf.put(n, items[n - 2])
''',
        '''def shift_right(shelf):
    items = [shelf.get(n) for n in range(shelf.size)]
    for n in range(shelf.size):
        shelf.put(n, items[n - 1])
''',
        _SHELF + '''def test_three():
    s = _shelf("a", "b", "c"); shift_right(s)
    assert _items(s) == ["c", "a", "b"]
def test_two():
    s = _shelf("x", "y"); shift_right(s)
    assert _items(s) == ["y", "x"]
''',
    ),
)
