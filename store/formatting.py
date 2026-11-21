from decimal import Decimal, InvalidOperation


def format_inr(value):
    """Format an amount as Indian rupees with lakh-style grouping, e.g. ₹1,23,456 or ₹499.50."""
    try:
        amount = Decimal(value).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    sign = "-" if amount < 0 else ""
    whole, frac = f"{abs(amount):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}₹{whole}" if frac == "00" else f"{sign}₹{whole}.{frac}"
