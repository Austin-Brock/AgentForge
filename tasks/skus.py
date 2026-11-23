"""Family: Inventory.add canonicalises SKUs but Inventory.count looks up the exact string given."""
from tasks.base import family

_INV = '''def _inv():
    inv = kiln.Inventory()
    inv.add("ab-1", 5)
    inv.add("CD-2", 3)
    return inv
'''

TASKS = family(
    "skus",
    (
        "sku1",
        "on_hand(inv, code) -> int",
        "Return how many units of the product `code` are in the inventory `inv`. `code` is typed by a "
        "person, so its letter case and surrounding spaces vary.",
        '''import kiln

def on_hand(inv, code):
    return inv.count(kiln.sku(code))
''',
        '''def on_hand(inv, code):
    return inv.count(code)
''',
        _INV + '''def test_lowercase():
    assert on_hand(_inv(), "ab-1") == 5
def test_padded():
    assert on_hand(_inv(), " cd-2 ") == 3
def test_unknown():
    assert on_hand(_inv(), "zz-9") == 0
''',
    ),
    (
        "sku2",
        "in_stock(inv, code) -> bool",
        "Return True if the inventory `inv` holds at least one unit of the product `code`. `code` is typed "
        "by a person, so its letter case and surrounding spaces vary.",
        '''import kiln

def in_stock(inv, code):
    return inv.count(kiln.sku(code)) > 0
''',
        '''def in_stock(inv, code):
    return inv.count(code) > 0
''',
        _INV + '''def test_lowercase():
    assert in_stock(_inv(), "ab-1") is True
def test_unknown():
    assert in_stock(_inv(), "zz-9") is False
''',
    ),
    (
        "sku3",
        "total_on_hand(inv, codes) -> int",
        "Return the total units in the inventory `inv` across the distinct products listed in `codes`. "
        "The codes are typed by a person, so letter case and surrounding spaces vary.",
        '''import kiln

def total_on_hand(inv, codes):
    return sum(inv.count(c) for c in {kiln.sku(c) for c in codes})
''',
        '''def total_on_hand(inv, codes):
    return sum(inv.count(c) for c in set(codes))
''',
        _INV + '''def test_two_products():
    assert total_on_hand(_inv(), ["ab-1", "cd-2 "]) == 8
def test_same_product_twice():
    assert total_on_hand(_inv(), ["ab-1", "AB-1"]) == 5
''',
    ),
    (
        "sku4",
        "missing(inv, codes) -> list",
        "Return the entries of `codes`, exactly as given and in the same order, for which the inventory "
        "`inv` holds no units. The codes are typed by a person, so letter case and surrounding spaces vary.",
        '''import kiln

def missing(inv, codes):
    return [c for c in codes if inv.count(kiln.sku(c)) == 0]
''',
        '''def missing(inv, codes):
    return [c for c in codes if inv.count(c) == 0]
''',
        _INV + '''def test_one_missing():
    assert missing(_inv(), ["ab-1", "xx-9", " CD-2"]) == ["xx-9"]
def test_none_missing():
    assert missing(_inv(), ["cd-2"]) == []
''',
    ),
    (
        "sku5",
        "same_product(a, b) -> bool",
        "Return True if the code strings `a` and `b` refer to the same product in kiln, otherwise False.",
        '''import kiln

def same_product(a, b):
    return kiln.sku(a) == kiln.sku(b)
''',
        '''def same_product(a, b):
    return a.lower() == b.lower()
''',
        '''def test_padding_and_case():
    assert same_product("ab-1 ", "AB-1") is True
def test_different():
    assert same_product("ab-1", "ab-2") is False
''',
    ),
    (
        "sku6",
        "stock_report(inv, codes) -> dict",
        "Return a dict mapping the canonical SKU of each entry in `codes` to the units of it in the "
        "inventory `inv`. The codes are typed by a person, so letter case and surrounding spaces vary.",
        '''import kiln

def stock_report(inv, codes):
    return {kiln.sku(c): inv.count(kiln.sku(c)) for c in codes}
''',
        '''def stock_report(inv, codes):
    return {c: inv.count(c) for c in codes}
''',
        _INV + '''def test_report():
    assert stock_report(_inv(), ["ab-1", " cd-2", "zz-9"]) == {"AB-1": 5, "CD-2": 3, "ZZ-9": 0}
''',
    ),
    (
        "sku7",
        "receive(inv, shipment) -> int",
        "`shipment` is a dict of product code -> units, with codes as typed by a person. Add every line to "
        "the inventory `inv`, then return the total units now on hand across the products in the shipment.",
        '''import kiln

def receive(inv, shipment):
    for code, qty in shipment.items():
        inv.add(code, qty)
    return sum(inv.count(c) for c in {kiln.sku(c) for c in shipment})
''',
        '''def receive(inv, shipment):
    for code, qty in shipment.items():
        inv.add(code, qty)
    return sum(inv.count(c) for c in shipment)
''',
        _INV + '''def test_existing_and_new():
    inv = _inv()
    assert receive(inv, {"ab-1": 2, "ef-3": 4}) == 11
    assert inv.count("AB-1") == 7
def test_empty_shipment():
    assert receive(_inv(), {}) == 0
''',
    ),
    (
        "sku8",
        "shelf_stock(shelf, inv) -> list",
        "Each slot of the kiln.Shelf `shelf` is empty or holds a product code as typed by a person. Return "
        "a list with one number per slot, in slot order: the units of that product in the inventory `inv`, "
        "or 0 for an empty slot.",
        '''import kiln

def shelf_stock(shelf, inv):
    out = []
    for n in range(1, shelf.size + 1):
        code = shelf.get(n)
        out.append(0 if code is None else inv.count(kiln.sku(code)))
    return out
''',
        '''def shelf_stock(shelf, inv):
    out = []
    for n in range(shelf.size):
        code = shelf.get(n)
        out.append(0 if code is None else inv.count(code))
    return out
''',
        _INV + '''def test_shelf_with_gap():
    s = kiln.Shelf(3); s.put(1, "ab-1"); s.put(3, " cd-2")
    assert shelf_stock(s, _inv()) == [5, 0, 3]
''',
    ),
)
