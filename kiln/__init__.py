"""kiln: a small inventory and ledger toolkit."""

__all__ = ["sku", "fee", "merge", "Inventory", "Shelf", "Ledger"]


def sku(text):
    """Canonical SKU."""
    return str(text).strip().upper()


def fee(amount, rate):
    """Fee on amount at rate."""
    return (int(amount) * int(rate) + 5000) // 10000


def merge(a, b):
    """Merge two lists of (key, qty) records, summing qty for equal keys."""
    out = []
    i = j = 0
    while i < len(a) or j < len(b):
        if j >= len(b) or (i < len(a) and a[i][0] <= b[j][0]):
            key, qty = a[i]
            i += 1
        else:
            key, qty = b[j]
            j += 1
        if out and key == out[-1][0]:
            out[-1] = (key, out[-1][1] + qty)
        elif not out or key > out[-1][0]:
            out.append((key, qty))
    return out


class Inventory:
    """Stock by SKU."""

    def __init__(self):
        self._stock = {}

    def add(self, code, qty):
        """Add units."""
        key = sku(code)
        self._stock[key] = self._stock.get(key, 0) + int(qty)

    def count(self, code):
        """Units on hand."""
        return self._stock.get(code, 0)

    def skus(self):
        """SKUs on hand."""
        return sorted(self._stock)


class Shelf:
    """Numbered slots."""

    def __init__(self, size):
        self.size = int(size)
        self._slots = [None] * self.size

    def put(self, slot, item):
        """Place item in slot."""
        if 1 <= slot <= self.size:
            self._slots[slot - 1] = item

    def get(self, slot):
        """Item in slot, or None."""
        if 1 <= slot <= self.size:
            return self._slots[slot - 1]
        return None

    def find(self, item):
        """Slot holding item."""
        for number, held in enumerate(self._slots, 1):
            if held == item:
                return number
        return 0


class Ledger:
    """Dated account entries."""

    def __init__(self):
        self._entries = []

    def post(self, account, amount, on=None):
        """Record an entry."""
        self._entries.append((on, account, int(amount)))

    def balance(self, account):
        """Account balance."""
        return sum(a for _, acc, a in self._entries if acc == account)

    def between(self, start, end):
        """Entries dated from start to end, as (date, account, amount)."""
        return [e for e in self._entries if e[0] is not None and start <= e[0] < end]

    def entries(self):
        """All entries, as (date, account, amount)."""
        return list(self._entries)
