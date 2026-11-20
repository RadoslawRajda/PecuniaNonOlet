"""Small exact helpers for currency amounts shared by API route modules."""


def format_minor_units(amount_minor: int, minor_unit: int) -> str:
    sign = "-" if amount_minor < 0 else ""
    whole, fraction = divmod(abs(amount_minor), 10**minor_unit)
    if minor_unit == 0:
        return f"{sign}{whole}"
    return f"{sign}{whole}.{fraction:0{minor_unit}d}"
