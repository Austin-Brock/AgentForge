"""Family: kiln.fee takes its rate in basis points (1% = 100); fractional rates are silently truncated."""
from tasks.base import family

TASKS = family(
    "rates",
    (
        "bp1",
        "sales_tax(amount, percent) -> int",
        "Return the tax on `amount` (an int) at `percent` percent, which may be fractional such as 8.25. "
        "Compute it with kiln.fee.",
        '''import kiln

def sales_tax(amount, percent):
    return kiln.fee(amount, round(percent * 100))
''',
        '''import kiln

def sales_tax(amount, percent):
    return kiln.fee(amount, percent)
''',
        '''def test_fractional_rate():
    assert sales_tax(10000, 8.25) == 825
def test_whole_rate():
    assert sales_tax(1999, 10) == 200
''',
    ),
    (
        "bp2",
        "price_with_tax(amount, percent) -> int",
        "Return `amount` (an int) plus the tax on it at `percent` percent. Compute the tax with kiln.fee.",
        '''import kiln

def price_with_tax(amount, percent):
    return amount + kiln.fee(amount, round(percent * 100))
''',
        '''import kiln

def price_with_tax(amount, percent):
    return amount + kiln.fee(amount, percent)
''',
        '''def test_seven_percent():
    assert price_with_tax(5000, 7) == 5350
def test_fractional():
    assert price_with_tax(20000, 6.5) == 21300
''',
    ),
    (
        "bp3",
        "fee_from_fraction(amount, fraction) -> int",
        "Return the fee on `amount` (an int) where the rate is given as a fraction, such as 0.029 for 2.9%. "
        "Compute it with kiln.fee.",
        '''import kiln

def fee_from_fraction(amount, fraction):
    return kiln.fee(amount, round(fraction * 10000))
''',
        '''import kiln

def fee_from_fraction(amount, fraction):
    return kiln.fee(amount, fraction)
''',
        '''def test_card_rate():
    assert fee_from_fraction(10000, 0.029) == 290
def test_half():
    assert fee_from_fraction(400, 0.5) == 200
''',
    ),
    (
        "bp4",
        "total_fees(amounts, percent) -> int",
        "Return the sum of the fees on each amount in `amounts` (ints) at `percent` percent. "
        "Compute each item's fee separately with kiln.fee.",
        '''import kiln

def total_fees(amounts, percent):
    return sum(kiln.fee(a, round(percent * 100)) for a in amounts)
''',
        '''import kiln

def total_fees(amounts, percent):
    return sum(kiln.fee(a, percent) for a in amounts)
''',
        '''def test_rounded_per_item():
    assert total_fees([150, 150, 150], 1.0) == 6
def test_larger():
    assert total_fees([10000, 20000], 2.5) == 750
''',
    ),
    (
        "bp5",
        "net_after_fee(amount, percent) -> int",
        "Return what is left of `amount` (an int) after deducting the fee at `percent` percent. "
        "Compute the fee with kiln.fee.",
        '''import kiln

def net_after_fee(amount, percent):
    return amount - kiln.fee(amount, round(percent * 100))
''',
        '''import kiln

def net_after_fee(amount, percent):
    return amount - kiln.fee(amount, percent)
''',
        '''def test_card_fee():
    assert net_after_fee(20000, 2.9) == 19420
def test_one_percent():
    assert net_after_fee(1000, 1) == 990
''',
    ),
    (
        "bp6",
        "cheapest_processor(amount, rates_percent) -> str",
        "`rates_percent` maps a processor name to its rate in percent. Return the name whose fee on `amount` "
        "(an int), computed with kiln.fee, is lowest. On a tie return the alphabetically first name.",
        '''import kiln

def cheapest_processor(amount, rates_percent):
    return min(sorted(rates_percent), key=lambda n: kiln.fee(amount, round(rates_percent[n] * 100)))
''',
        '''import kiln

def cheapest_processor(amount, rates_percent):
    return min(sorted(rates_percent), key=lambda n: kiln.fee(amount, rates_percent[n]))
''',
        '''def test_close_rates():
    assert cheapest_processor(10000, {"a": 2.9, "b": 2.2}) == "b"
def test_tie():
    assert cheapest_processor(10000, {"z": 1.5, "m": 1.5}) == "m"
def test_sub_percent():
    assert cheapest_processor(100000, {"x": 0.5, "y": 0.25}) == "y"
''',
    ),
    (
        "bp7",
        "tiered_fee(amount, percent_low, percent_high, threshold) -> int",
        "Return the fee on `amount` (an int) where the part up to `threshold` is charged at `percent_low` "
        "percent and the part above it at `percent_high` percent. Compute each part with kiln.fee.",
        '''import kiln

def tiered_fee(amount, percent_low, percent_high, threshold):
    low = min(amount, threshold)
    return kiln.fee(low, round(percent_low * 100)) + kiln.fee(amount - low, round(percent_high * 100))
''',
        '''import kiln

def tiered_fee(amount, percent_low, percent_high, threshold):
    low = min(amount, threshold)
    return kiln.fee(low, percent_low) + kiln.fee(amount - low, percent_high)
''',
        '''def test_above_threshold():
    assert tiered_fee(30000, 1.0, 2.5, 10000) == 600
def test_below_threshold():
    assert tiered_fee(5000, 1.0, 2.5, 10000) == 50
''',
    ),
    (
        "bp8",
        "fee_in_dollars(dollars, percent) -> float",
        "Return the fee, in dollars, on an amount of `dollars` (a float) at `percent` percent. "
        "Compute it with kiln.fee.",
        '''import kiln

def fee_in_dollars(dollars, percent):
    return kiln.fee(round(dollars * 100), round(percent * 100)) / 100
''',
        '''import kiln

def fee_in_dollars(dollars, percent):
    return float(kiln.fee(dollars, percent))
''',
        '''def test_round_amount():
    assert fee_in_dollars(200.0, 2.5) == 5.0
def test_odd_amount():
    assert fee_in_dollars(19.99, 10) == 2.0
''',
    ),
)
