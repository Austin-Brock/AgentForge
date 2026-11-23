"""The kiln task set: six convention families, eight tasks each."""
from tasks.base import API_DOCS, Task
from tasks import minor_units, windows, slots, rates, merging, skus

FAMILY_LABELS = {
    "minor_units": "Amounts are whole minor units (cents)",
    "windows": "Date windows exclude the end date",
    "slots": "Shelf slots are numbered from 1",
    "rates": "Rates are basis points",
    "merging": "merge() needs sorted inputs",
    "skus": "Lookups need canonical SKUs",
}

_MODULES = [minor_units, windows, slots, rates, merging, skus]


def load_tasks(split=None):
    tasks = [t for m in _MODULES for t in m.TASKS]
    return [t for t in tasks if split is None or t.split == split]


__all__ = ["API_DOCS", "Task", "FAMILY_LABELS", "load_tasks"]
