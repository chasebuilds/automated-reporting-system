"""Number formatting shared by the HTML dashboard and the email summary."""

from __future__ import annotations


def money(cents: int | None, symbol: str = "$", decimals: bool = True) -> str:
    if cents is None:
        return "n/a"
    sign = "-" if cents < 0 else ""
    if decimals:
        return f"{sign}{symbol}{abs(cents) / 100:,.2f}"
    return f"{sign}{symbol}{round(abs(cents) / 100):,}"


def pct(value: float | None, places: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{places}f}%"


def delta(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:+.1f}%"


def times(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}x"


def minutes(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.0f} min"


def count(value: float | int | None) -> str:
    return "n/a" if value is None else f"{value:,}"
