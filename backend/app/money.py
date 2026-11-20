"""Exact currency amount helpers and the shared account balance limit."""

MAX_BALANCE_MINOR = 9_000_000_000_000_000


def format_minor_units(amount_minor: int, minor_unit: int) -> str:
    sign = "-" if amount_minor < 0 else ""
    whole, fraction = divmod(abs(amount_minor), 10**minor_unit)
    if minor_unit == 0:
        return f"{sign}{whole}"
    return f"{sign}{whole}.{fraction:0{minor_unit}d}"
