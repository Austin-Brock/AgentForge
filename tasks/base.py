"""Task definition shared by the family modules."""
from dataclasses import dataclass

# The only documentation the agent is given. It deliberately omits kiln's conventions.
API_DOCS = """\
kiln API reference
  kiln.sku(text) -> str                canonical SKU
  kiln.fee(amount, rate) -> int        fee on amount at rate
  kiln.merge(a, b) -> list             merge two lists of (key, qty) records, summing qty for equal keys
  kiln.Inventory()                     stock by SKU
    .add(code, qty)                    add units
    .count(code) -> int                units on hand
    .skus() -> list[str]               SKUs on hand
  kiln.Shelf(size)                     numbered slots
    .size -> int                       number of slots
    .put(slot, item)                   place item in slot
    .get(slot)                         item in slot, or None
    .find(item) -> int                 slot holding item
  kiln.Ledger()                        dated account entries
    .post(account, amount, on=None)    record an entry (on: datetime.date)
    .balance(account) -> int           account balance
    .between(start, end) -> list       entries dated from start to end, as (date, account, amount)
    .entries() -> list                 all entries, as (date, account, amount)
"""

TRAIN_POSITIONS = {1, 4, 7}  # position within a family; the rest are held out


@dataclass(frozen=True)
class Task:
    id: str
    family: str
    position: int
    signature: str
    prompt: str
    ref: str    # reference solution: must pass the hidden tests
    naive: str  # falls for the family's trap: must fail the hidden tests
    tests: str  # hidden tests, never shown to the agent

    @property
    def split(self):
        return "train" if self.position in TRAIN_POSITIONS else "heldout"

    def render(self):
        """The text the agent sees."""
        return (
            f"{API_DOCS}\nTask: write a Python module that defines\n\n    def {self.signature}\n\n"
            f"{self.prompt}\n\nThe module may `import kiln` and the standard library."
        )


def family(name, *specs):
    """Build a family's task list from (id, signature, prompt, ref, naive, tests) tuples."""
    return [Task(s[0], name, n, *s[1:]) for n, s in enumerate(specs, 1)]
