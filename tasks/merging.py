"""Family: kiln.merge assumes both inputs are sorted by key; out-of-order records are silently dropped."""
from tasks.base import family

TASKS = family(
    "merging",
    (
        "mg1",
        "combine(a, b) -> list",
        "`a` and `b` are lists of (key, qty) records in no particular order. Combine them with kiln.merge "
        "into one list sorted by key, with quantities summed for equal keys.",
        '''import kiln

def combine(a, b):
    return kiln.merge(sorted(a), sorted(b))
''',
        '''import kiln

def combine(a, b):
    return kiln.merge(a, b)
''',
        '''def test_mixed_order():
    a = [("pear", 2), ("apple", 1)]
    b = [("fig", 5), ("apple", 3)]
    assert combine(a, b) == [("apple", 4), ("fig", 5), ("pear", 2)]
def test_one_empty():
    assert combine([("b", 1), ("a", 2)], []) == [("a", 2), ("b", 1)]
''',
    ),
    (
        "mg2",
        "combine_all(lists) -> list",
        "`lists` is a list of lists of (key, qty) records, each in no particular order. Combine them all "
        "with kiln.merge into one list sorted by key, with quantities summed for equal keys.",
        '''import kiln

def combine_all(lists):
    out = []
    for records in lists:
        out = kiln.merge(out, sorted(records))
    return out
''',
        '''import kiln

def combine_all(lists):
    out = []
    for records in lists:
        out = kiln.merge(out, records)
    return out
''',
        '''def test_three_lists():
    lists = [[("c", 1), ("a", 1)], [("b", 2)], [("c", 3), ("b", 1), ("a", 4)]]
    assert combine_all(lists) == [("a", 5), ("b", 3), ("c", 4)]
def test_none():
    assert combine_all([]) == []
''',
    ),
    (
        "mg3",
        "total_qty(a, b) -> int",
        "`a` and `b` are lists of (key, qty) records in no particular order. Combine them with kiln.merge "
        "and return the total quantity across the combined records.",
        '''import kiln

def total_qty(a, b):
    return sum(q for _, q in kiln.merge(sorted(a), sorted(b)))
''',
        '''import kiln

def total_qty(a, b):
    return sum(q for _, q in kiln.merge(a, b))
''',
        '''def test_total():
    assert total_qty([("z", 1), ("c", 6)], [("m", 5), ("c", 4)]) == 16
def test_empty():
    assert total_qty([], []) == 0
''',
    ),
    (
        "mg4",
        "restock(stock, delivery) -> list",
        "`stock` is a list of (key, qty) records sorted by key. `delivery` is a dict of key -> qty in the "
        "order the items arrived. Use kiln.merge to return the updated stock, sorted by key.",
        '''import kiln

def restock(stock, delivery):
    return kiln.merge(stock, sorted(delivery.items()))
''',
        '''import kiln

def restock(stock, delivery):
    return kiln.merge(stock, list(delivery.items()))
''',
        '''def test_delivery():
    stock = [("bolt", 10), ("nut", 4)]
    delivery = {"washer": 7, "bolt": 5, "anchor": 2}
    assert restock(stock, delivery) == [("anchor", 2), ("bolt", 15), ("nut", 4), ("washer", 7)]
def test_nothing_delivered():
    assert restock([("bolt", 10)], {}) == [("bolt", 10)]
''',
    ),
    (
        "mg5",
        "merge_desc(a, b) -> list",
        "`a` and `b` are lists of (key, qty) records, each sorted by key in descending order. Combine them "
        "with kiln.merge and return the result sorted by key in descending order, quantities summed for equal keys.",
        '''import kiln

def merge_desc(a, b):
    return kiln.merge(a[::-1], b[::-1])[::-1]
''',
        '''import kiln

def merge_desc(a, b):
    return kiln.merge(a, b)
''',
        '''def test_descending():
    a = [("pear", 1), ("fig", 2)]
    b = [("kiwi", 3), ("apple", 4)]
    assert merge_desc(a, b) == [("pear", 1), ("kiwi", 3), ("fig", 2), ("apple", 4)]
def test_shared_key():
    assert merge_desc([("b", 1), ("a", 1)], [("b", 2)]) == [("b", 3), ("a", 1)]
''',
    ),
    (
        "mg6",
        "dedupe(records) -> list",
        "`records` is a list of (key, qty) records in no particular order, possibly with repeated keys. "
        "Use kiln.merge to return one record per key, sorted by key, with quantities summed.",
        '''import kiln

def dedupe(records):
    return kiln.merge(sorted(records), [])
''',
        '''import kiln

def dedupe(records):
    return kiln.merge(records, [])
''',
        '''def test_repeats():
    assert dedupe([("b", 1), ("a", 2), ("b", 3)]) == [("a", 2), ("b", 4)]
def test_already_unique():
    assert dedupe([("c", 1), ("a", 1)]) == [("a", 1), ("c", 1)]
''',
    ),
    (
        "mg7",
        "top_key(a, b) -> str",
        "`a` and `b` are lists of (key, qty) records in no particular order. Combine them with kiln.merge "
        "and return the key with the largest combined quantity.",
        '''import kiln

def top_key(a, b):
    return max(kiln.merge(sorted(a), sorted(b)), key=lambda r: r[1])[0]
''',
        '''import kiln

def top_key(a, b):
    return max(kiln.merge(a, b), key=lambda r: r[1])[0]
''',
        '''def test_shared_key_wins():
    assert top_key([("z", 1), ("c", 6)], [("m", 5), ("c", 4)]) == "c"
def test_single_list():
    assert top_key([("b", 9), ("a", 2)], []) == "b"
''',
    ),
    (
        "mg8",
        "combine_skus(a, b) -> list",
        "`a` and `b` are lists of (sku, qty) records in no particular order, where the SKU strings vary in "
        "letter case and surrounding spaces. Combine them with kiln.merge into one list keyed by canonical "
        "SKU, sorted by key, with quantities summed.",
        '''import kiln

def combine_skus(a, b):
    def norm(records):
        return sorted((kiln.sku(k), q) for k, q in records)
    return kiln.merge(norm(a), norm(b))
''',
        '''import kiln

def combine_skus(a, b):
    return kiln.merge(a, b)
''',
        '''def test_messy_skus():
    a = [(" nut-2", 1), ("bolt-1", 2)]
    b = [("BOLT-1 ", 3), ("nut-2", 4)]
    assert combine_skus(a, b) == [("BOLT-1", 5), ("NUT-2", 5)]
def test_repeat_within_list():
    assert combine_skus([("ab-1", 1), ("AB-1", 2)], []) == [("AB-1", 3)]
''',
    ),
)
