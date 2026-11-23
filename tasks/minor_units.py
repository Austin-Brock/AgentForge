"""Family: Ledger amounts are whole minor units (cents); floats are silently truncated."""
from tasks.base import family

TASKS = family(
    "minor_units",
    (
        "mu1",
        "record_payments(ledger, payments)",
        'Post each payment in `payments` (dollar amounts, floats) to the "cash" account of `ledger`.',
        '''def record_payments(ledger, payments):
    for p in payments:
        ledger.post("cash", round(p * 100))
''',
        '''def record_payments(ledger, payments):
    for p in payments:
        ledger.post("cash", p)
''',
        '''def test_two_payments():
    l = kiln.Ledger(); record_payments(l, [12.50, 0.75])
    assert l.balance("cash") == 1325
def test_repeated_price():
    l = kiln.Ledger(); record_payments(l, [19.99] * 3)
    assert l.balance("cash") == 5997
def test_entry_count():
    l = kiln.Ledger(); record_payments(l, [1.0, 2.0])
    assert len(l.entries()) == 2
''',
    ),
    (
        "mu2",
        "cash_in_dollars(ledger) -> float",
        'Return the balance of the "cash" account of `ledger`, in dollars.',
        '''def cash_in_dollars(ledger):
    return ledger.balance("cash") / 100
''',
        '''def cash_in_dollars(ledger):
    return float(ledger.balance("cash"))
''',
        '''def test_balance():
    l = kiln.Ledger(); l.post("cash", 1325)
    assert cash_in_dollars(l) == 13.25
def test_other_accounts_ignored():
    l = kiln.Ledger(); l.post("cash", 500); l.post("bank", 900)
    assert cash_in_dollars(l) == 5.0
''',
    ),
    (
        "mu3",
        "refund(ledger, account, dollars)",
        "Record a refund of `dollars` (a float) against `account`, reducing its balance.",
        '''def refund(ledger, account, dollars):
    ledger.post(account, -round(dollars * 100))
''',
        '''def refund(ledger, account, dollars):
    ledger.post(account, -dollars)
''',
        '''def test_refund():
    l = kiln.Ledger(); l.post("cash", 5000); refund(l, "cash", 12.5)
    assert l.balance("cash") == 3750
def test_small_refund():
    l = kiln.Ledger(); l.post("cash", 100); refund(l, "cash", 0.25)
    assert l.balance("cash") == 75
''',
    ),
    (
        "mu4",
        "largest_entry_dollars(ledger) -> float",
        "Return the largest single entry amount in `ledger`, in dollars. The ledger has at least one entry.",
        '''def largest_entry_dollars(ledger):
    return max(a for _, _, a in ledger.entries()) / 100
''',
        '''def largest_entry_dollars(ledger):
    return float(max(a for _, _, a in ledger.entries()))
''',
        '''def test_largest():
    l = kiln.Ledger()
    for a in (250, 1999, 500):
        l.post("cash", a)
    assert largest_entry_dollars(l) == 19.99
def test_single():
    l = kiln.Ledger(); l.post("bank", 100)
    assert largest_entry_dollars(l) == 1.0
''',
    ),
    (
        "mu5",
        "transfer(ledger, src, dst, dollars)",
        "Move `dollars` (a float) from account `src` to account `dst` by posting one entry to each.",
        '''def transfer(ledger, src, dst, dollars):
    cents = round(dollars * 100)
    ledger.post(src, -cents)
    ledger.post(dst, cents)
''',
        '''def transfer(ledger, src, dst, dollars):
    ledger.post(src, -dollars)
    ledger.post(dst, dollars)
''',
        '''def test_transfer():
    l = kiln.Ledger(); l.post("cash", 10000); transfer(l, "cash", "bank", 25.5)
    assert l.balance("cash") == 7450
    assert l.balance("bank") == 2550
def test_cents_only():
    l = kiln.Ledger(); transfer(l, "a", "b", 0.99)
    assert l.balance("b") == 99
''',
    ),
    (
        "mu6",
        "can_afford(ledger, account, price_dollars) -> bool",
        "Return True if the balance of `account` covers a price of `price_dollars` (a float).",
        '''def can_afford(ledger, account, price_dollars):
    return ledger.balance(account) >= round(price_dollars * 100)
''',
        '''def can_afford(ledger, account, price_dollars):
    return ledger.balance(account) >= price_dollars
''',
        '''def _l():
    l = kiln.Ledger(); l.post("cash", 1000); return l
def test_too_expensive():
    assert can_afford(_l(), "cash", 25.0) is False
def test_exact():
    assert can_afford(_l(), "cash", 10.0) is True
def test_one_cent_short():
    assert can_afford(_l(), "cash", 10.01) is False
''',
    ),
    (
        "mu7",
        "month_revenue_dollars(ledger, year, month) -> float",
        'Return the total of the "sales" entries dated in the given calendar month, in dollars.',
        '''from datetime import date

def month_revenue_dollars(ledger, year, month):
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return sum(a for _, acc, a in ledger.between(start, end) if acc == "sales") / 100
''',
        '''import calendar
from datetime import date

def month_revenue_dollars(ledger, year, month):
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return float(sum(a for _, acc, a in ledger.between(start, end) if acc == "sales"))
''',
        '''def test_january():
    l = kiln.Ledger()
    l.post("sales", 1000, on=date(2025, 1, 1))
    l.post("sales", 2550, on=date(2025, 1, 31))
    l.post("sales", 999, on=date(2025, 2, 1))
    l.post("cash", 500, on=date(2025, 1, 15))
    assert month_revenue_dollars(l, 2025, 1) == 35.5
def test_december():
    l = kiln.Ledger()
    l.post("sales", 100, on=date(2024, 12, 31))
    l.post("sales", 300, on=date(2025, 1, 1))
    assert month_revenue_dollars(l, 2024, 12) == 1.0
''',
    ),
    (
        "mu8",
        "post_with_fee(ledger, account, dollars, percent)",
        "Post `dollars` (a float) to `account`. Also post the fee on that amount, at `percent` percent "
        'and computed with kiln.fee, to the "fees" account.',
        '''import kiln

def post_with_fee(ledger, account, dollars, percent):
    cents = round(dollars * 100)
    ledger.post(account, cents)
    ledger.post("fees", kiln.fee(cents, round(percent * 100)))
''',
        '''import kiln

def post_with_fee(ledger, account, dollars, percent):
    ledger.post(account, dollars)
    ledger.post("fees", kiln.fee(dollars, percent))
''',
        '''def test_sale_with_fee():
    l = kiln.Ledger(); post_with_fee(l, "sales", 200.0, 2.5)
    assert l.balance("sales") == 20000
    assert l.balance("fees") == 500
def test_small_sale():
    l = kiln.Ledger(); post_with_fee(l, "sales", 19.99, 10)
    assert l.balance("sales") == 1999
    assert l.balance("fees") == 200
''',
    ),
)
