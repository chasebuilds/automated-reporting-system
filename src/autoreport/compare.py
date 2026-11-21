"""Parallel-run check: the tool's numbers for a week against a report made by hand.

Before a manual report is retired, both are produced for a few weeks and every difference
is explained. A difference is not automatically the tool's bug; hand-built spreadsheets
are often the side that is wrong, so each row is listed for a person to decide.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

# name in the manual file -> (key in the week's totals, divisor, tolerance, decimals shown)
METRICS: dict[str, tuple[str, int, float, int]] = {
    "revenue": ("revenue_cents", 100, 0.005, 2),
    "orders": ("orders", 1, 0, 0),
    "average_order_value": ("aov_cents", 100, 0.005, 2),
    "refunds": ("refunds", 1, 0, 0),
    "refund_amount": ("refund_cents", 100, 0.005, 2),
    "refund_rate": ("refund_rate", 1, 0.00005, 4),
    "net_revenue": ("net_revenue_cents", 100, 0.005, 2),
    "ad_spend": ("spend_cents", 100, 0.005, 2),
    "paid_roas": ("paid_roas", 1, 0.005, 2),
    "tickets": ("tickets", 1, 0, 0),
    "avg_first_response_min": ("avg_first_response_min", 1, 0.05, 1),
}


@dataclass(frozen=True)
class Row:
    metric: str
    manual: float | None
    tool: float | None
    note: str

    @property
    def matches(self) -> bool:
        return self.note == "match"


def _number(text: str) -> float:
    cleaned = text.replace("$", "").replace(",", "").strip()
    if cleaned.endswith("%"):
        return float(Decimal(cleaned[:-1]) / 100)
    if cleaned.endswith("x"):
        cleaned = cleaned[:-1]
    return float(Decimal(cleaned))


def compare_period(totals: dict, manual_file: Path) -> list[Row]:
    with manual_file.open(newline="", encoding="utf-8-sig") as handle:
        raw = [row for row in csv.reader(handle) if any(cell.strip() for cell in row)]
    header = [h.strip().lower() for h in raw[0]] if raw else []
    if "metric" not in header or "value" not in header:
        raise ValueError(f"{manual_file.name}: needs the columns 'metric' and 'value'")
    name_at, value_at = header.index("metric"), header.index("value")
    rows = []
    for cells in raw[1:]:
        name = cells[name_at].strip().lower().replace(" ", "_")
        text = cells[value_at].strip() if value_at < len(cells) else ""
        if name not in METRICS:
            rows.append(Row(name, None, None, "not a metric this tool reports"))
            continue
        key, divisor, tolerance, _ = METRICS[name]
        tool = None if totals.get(key) is None else totals[key] / divisor
        try:
            manual = _number(text)
        except (InvalidOperation, ValueError):
            rows.append(Row(name, None, tool, f"manual value '{text}' could not be read"))
            continue
        if tool is None:
            rows.append(Row(name, manual, None, "tool has no value for this week"))
        elif abs(manual - tool) <= tolerance + 1e-9:
            rows.append(Row(name, manual, tool, "match"))
        else:
            rows.append(Row(name, manual, tool, "DIFFERENT"))
    return rows


def format_rows(rows: list[Row]) -> list[str]:
    def show(metric: str, value: float | None) -> str:
        if value is None:
            return "n/a"
        return f"{value:,.{METRICS[metric][3]}f}" if metric in METRICS else f"{value:,}"

    out = [f"{'metric':<24}{'manual':>14}{'tool':>14}{'difference':>14}  result"]
    for row in rows:
        gap = (
            ""
            if row.manual is None or row.tool is None
            else f"{row.tool - row.manual:+,.{METRICS[row.metric][3]}f}"
        )
        out.append(
            f"{row.metric:<24}{show(row.metric, row.manual):>14}{show(row.metric, row.tool):>14}"
            f"{gap:>14}  {row.note}"
        )
    return out
