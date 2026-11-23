"""Family: Ledger.between(start, end) excludes the end date."""
from tasks.base import family

_LEDGER = '''def _ledger():
    l = kiln.Ledger()
    for d, amt in [(1, 100), (2, 200), (3, 300), (4, 400), (4, 50)]:
        l.post("cash", amt, on=date(2025, 3, d))
    return l
'''

TASKS = family(
    "windows",
    (
        "win1",
        "entries_in_range(ledger, first_day, last_day) -> list",
        "Return the entries of `ledger` dated from `first_day` through `last_day`, both included "
        "(datetime.date values), as (date, account, amount) tuples.",
        '''from datetime import timedelta

def entries_in_range(ledger, first_day, last_day):
    return ledger.between(first_day, last_day + timedelta(days=1))
''',
        '''def entries_in_range(ledger, first_day, last_day):
    return ledger.between(first_day, last_day)
''',
        _LEDGER + '''def test_middle_range():
    got = entries_in_range(_ledger(), date(2025, 3, 2), date(2025, 3, 3))
    assert [e[2] for e in got] == [200, 300]
def test_single_day():
    got = entries_in_range(_ledger(), date(2025, 3, 1), date(2025, 3, 1))
    assert [e[2] for e in got] == [100]
def test_before_any():
    assert list(entries_in_range(_ledger(), date(2025, 2, 1), date(2025, 2, 28))) == []
''',
    ),
    (
        "win2",
        "total_on_day(ledger, day) -> int",
        "Return the sum of the amounts of all entries dated `day` (a datetime.date), in the units kiln stores.",
        '''from datetime import timedelta

def total_on_day(ledger, day):
    return sum(e[2] for e in ledger.between(day, day + timedelta(days=1)))
''',
        '''def total_on_day(ledger, day):
    return sum(e[2] for e in ledger.between(day, day))
''',
        _LEDGER + '''def test_busy_day():
    assert total_on_day(_ledger(), date(2025, 3, 4)) == 450
def test_quiet_day():
    assert total_on_day(_ledger(), date(2025, 3, 2)) == 200
def test_no_entries():
    assert total_on_day(_ledger(), date(2025, 3, 9)) == 0
''',
    ),
    (
        "win3",
        "count_in_january(ledger, year) -> int",
        "Return how many entries of `ledger` are dated in January of `year`.",
        '''from datetime import date

def count_in_january(ledger, year):
    return len(ledger.between(date(year, 1, 1), date(year, 2, 1)))
''',
        '''from datetime import date

def count_in_january(ledger, year):
    return len(ledger.between(date(year, 1, 1), date(year, 1, 31)))
''',
        '''def test_month_edges():
    l = kiln.Ledger()
    for d in (date(2025, 1, 1), date(2025, 1, 31), date(2025, 2, 1), date(2024, 12, 31)):
        l.post("cash", 100, on=d)
    assert count_in_january(l, 2025) == 2
def test_empty():
    assert count_in_january(kiln.Ledger(), 2025) == 0
''',
    ),
    (
        "win4",
        "year_total(ledger, account, year) -> int",
        "Return the sum of the amounts posted to `account` during calendar year `year`, in the units kiln stores.",
        '''from datetime import date

def year_total(ledger, account, year):
    rows = ledger.between(date(year, 1, 1), date(year + 1, 1, 1))
    return sum(a for _, acc, a in rows if acc == account)
''',
        '''from datetime import date

def year_total(ledger, account, year):
    rows = ledger.between(date(year, 1, 1), date(year, 12, 31))
    return sum(a for _, acc, a in rows if acc == account)
''',
        '''def test_year_edges():
    l = kiln.Ledger()
    l.post("cash", 100, on=date(2024, 1, 1))
    l.post("cash", 200, on=date(2024, 12, 31))
    l.post("cash", 400, on=date(2025, 1, 1))
    l.post("bank", 800, on=date(2024, 6, 1))
    assert year_total(l, "cash", 2024) == 300
def test_other_year():
    l = kiln.Ledger(); l.post("cash", 100, on=date(2023, 5, 5))
    assert year_total(l, "cash", 2024) == 0
''',
    ),
    (
        "win5",
        "busiest_day(ledger, first_day, last_day)",
        "Among the days from `first_day` through `last_day`, both included, return the date with the most "
        "entries. On a tie return the earliest such date. Return None if there are no entries in the range.",
        '''from collections import Counter
from datetime import timedelta

def busiest_day(ledger, first_day, last_day):
    counts = Counter(e[0] for e in ledger.between(first_day, last_day + timedelta(days=1)))
    if not counts:
        return None
    top = max(counts.values())
    return min(d for d, c in counts.items() if c == top)
''',
        '''from collections import Counter

def busiest_day(ledger, first_day, last_day):
    counts = Counter(e[0] for e in ledger.between(first_day, last_day))
    if not counts:
        return None
    top = max(counts.values())
    return min(d for d, c in counts.items() if c == top)
''',
        _LEDGER + '''def test_last_day_is_busiest():
    assert busiest_day(_ledger(), date(2025, 3, 1), date(2025, 3, 4)) == date(2025, 3, 4)
def test_tie_takes_earliest():
    assert busiest_day(_ledger(), date(2025, 3, 1), date(2025, 3, 3)) == date(2025, 3, 1)
def test_empty_range():
    assert busiest_day(_ledger(), date(2025, 4, 1), date(2025, 4, 30)) is None
''',
    ),
    (
        "win6",
        "week_entries(ledger, monday) -> list",
        "Given `monday`, the date of a Monday, return the entries of `ledger` dated in that week, "
        "Monday through Sunday, as (date, account, amount) tuples.",
        '''from datetime import timedelta

def week_entries(ledger, monday):
    return ledger.between(monday, monday + timedelta(days=7))
''',
        '''from datetime import timedelta

def week_entries(ledger, monday):
    return ledger.between(monday, monday + timedelta(days=6))
''',
        '''def test_full_week():
    l = kiln.Ledger()
    l.post("cash", 1, on=date(2025, 3, 2))   # Sunday before
    l.post("cash", 2, on=date(2025, 3, 3))   # Monday
    l.post("cash", 3, on=date(2025, 3, 9))   # Sunday
    l.post("cash", 4, on=date(2025, 3, 10))  # next Monday
    assert [e[2] for e in week_entries(l, date(2025, 3, 3))] == [2, 3]
''',
    ),
    (
        "win7",
        "has_activity(ledger, day) -> bool",
        "Return True if `ledger` has at least one entry dated `day` (a datetime.date), otherwise False.",
        '''from datetime import timedelta

def has_activity(ledger, day):
    return bool(ledger.between(day, day + timedelta(days=1)))
''',
        '''def has_activity(ledger, day):
    return bool(ledger.between(day, day))
''',
        _LEDGER + '''def test_active_day():
    assert has_activity(_ledger(), date(2025, 3, 2)) is True
def test_idle_day():
    assert has_activity(_ledger(), date(2025, 3, 7)) is False
''',
    ),
    (
        "win8",
        "range_total_dollars(ledger, account, first_day, last_day) -> float",
        "Return the total posted to `account` from `first_day` through `last_day`, both included, in dollars.",
        '''from datetime import timedelta

def range_total_dollars(ledger, account, first_day, last_day):
    rows = ledger.between(first_day, last_day + timedelta(days=1))
    return sum(a for _, acc, a in rows if acc == account) / 100
''',
        '''def range_total_dollars(ledger, account, first_day, last_day):
    rows = ledger.between(first_day, last_day)
    return float(sum(a for _, acc, a in rows if acc == account))
''',
        _LEDGER + '''def test_whole_range():
    assert range_total_dollars(_ledger(), "cash", date(2025, 3, 1), date(2025, 3, 4)) == 10.5
def test_other_account():
    assert range_total_dollars(_ledger(), "bank", date(2025, 3, 1), date(2025, 3, 4)) == 0
''',
    ),
)
