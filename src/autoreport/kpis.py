"""Transform the typed tables and compute the week's KPIs.

Money is integer cents and every ratio is rounded once, half up, from an exact fraction.
That is what lets the benchmark demand an exact match against known truth.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from statistics import median

from autoreport.config import Config
from autoreport.ingest import Table, period_days, period_end

UNMAPPED = "Unmapped"

# metric -> decimal places used for its trailing average
COMPARED = {
    "revenue_cents": 0,
    "orders": 1,
    "aov_cents": 0,
    "refund_rate": 4,
    "spend_cents": 0,
    "paid_roas": 2,
    "tickets": 1,
    "avg_first_response_min": 1,
}


def round_half_up(value: Fraction, places: int) -> float | int:
    quantum = Decimal(1).scaleb(-places)
    rounded = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        quantum, rounding=ROUND_HALF_UP
    )
    return int(rounded) if places == 0 else float(rounded)


def ratio(numerator: int, denominator: int, places: int) -> float | int | None:
    if denominator == 0:
        return None
    return round_half_up(Fraction(numerator, denominator), places)


def _exact(value: float | int) -> Fraction:
    return Fraction(Decimal(str(value)))


def week_label(period: date) -> str:
    end = period_end(period)
    return f"{period.day} {period:%b} to {end.day} {end:%b %Y}"


def transform(tables: dict[str, Table], cfg: Config) -> dict[str, list[dict]]:
    """Copy rows with the channel mapped to its configured name."""
    out: dict[str, list[dict]] = {}
    for kind, table in tables.items():
        rows = []
        for row in table.rows:
            row = dict(row)
            if "channel" in row:
                row["channel"] = cfg.canonical_channel(row["channel"]) or UNMAPPED
            rows.append(row)
        out[kind] = rows
    return out


def compare(value: float | int | None, prior: list[float | int | None], places: int) -> dict:
    """Week over week and versus the trailing average. `prior` is oldest first."""
    previous = prior[-1] if prior else None
    usable = [_exact(v) for v in prior if v is not None]
    average = sum(usable, Fraction(0)) / len(usable) if usable else None
    return {
        "value": value,
        "previous": previous,
        "wow_pct": (
            round_half_up((_exact(value) - _exact(previous)) / _exact(previous), 4)
            if value is not None and previous
            else None
        ),
        "trailing_avg": round_half_up(average, places) if average is not None else None,
        "trailing_weeks": len(usable),
        "vs_trailing_pct": (
            round_half_up((_exact(value) - average) / average, 4)
            if value is not None and average
            else None
        ),
    }


def compute(
    rows: dict[str, list[dict]], period: date, cfg: Config, prior_weeks: list[dict]
) -> dict:
    orders, refunds = rows["orders"], rows["refunds"]
    spend_rows, tickets = rows["ad_spend"], rows["tickets"]

    revenue = sum(o["amount"] for o in orders)
    refund_total = sum(r["amount"] for r in refunds)
    spend = sum(s["spend"] for s in spend_rows)
    clicks = sum(s["clicks"] for s in spend_rows)

    by_channel: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for o in orders:
        by_channel[o["channel"]]["revenue_cents"] += o["amount"]
        by_channel[o["channel"]]["orders"] += 1
    for s in spend_rows:
        by_channel[s["channel"]]["spend_cents"] += s["spend"]
        by_channel[s["channel"]]["clicks"] += s["clicks"]
    names = list(cfg.channels) + ([UNMAPPED] if UNMAPPED in by_channel else [])
    channels = []
    for name in names:
        c = by_channel[name]
        channels.append(
            {
                "channel": name,
                "revenue_cents": c["revenue_cents"],
                "orders": c["orders"],
                "aov_cents": ratio(c["revenue_cents"], c["orders"], 0),
                "revenue_share": ratio(c["revenue_cents"], revenue, 4),
                "spend_cents": c["spend_cents"],
                "clicks": c["clicks"],
                "roas": ratio(c["revenue_cents"], c["spend_cents"], 2),
                "cpc_cents": ratio(c["spend_cents"], c["clicks"], 0),
            }
        )
    paid_revenue = sum(by_channel[name]["revenue_cents"] for name in cfg.paid_channels)

    response = [t["first_response_minutes"] for t in tickets]
    answered = [m for m in response if m is not None]
    within_sla = sum(1 for m in answered if m <= cfg.sla_minutes)

    totals = {
        "revenue_cents": revenue,
        "orders": len(orders),
        "items": sum(o["items"] for o in orders),
        "aov_cents": ratio(revenue, len(orders), 0),
        "refund_cents": refund_total,
        "refunds": len(refunds),
        "refund_rate": ratio(refund_total, revenue, 4),
        "net_revenue_cents": revenue - refund_total,
        "spend_cents": spend,
        "clicks": clicks,
        "paid_revenue_cents": paid_revenue,
        "paid_roas": ratio(paid_revenue, spend, 2),
        "tickets": len(tickets),
        "tickets_answered": len(answered),
        "avg_first_response_min": ratio(sum(answered), len(answered), 1),
        "median_first_response_min": (
            round_half_up(_exact(median(answered)), 1) if answered else None
        ),
        "sla_met_rate": ratio(within_sla, len(tickets), 4),
    }

    daily = []
    for day in period_days(period):
        day_orders = [o for o in orders if o["order_date"] == day]
        daily.append(
            {
                "date": day.isoformat(),
                "revenue_cents": sum(o["amount"] for o in day_orders),
                "orders": len(day_orders),
                "spend_cents": sum(s["spend"] for s in spend_rows if s["date"] == day),
                "tickets": sum(1 for t in tickets if t["created_at"] == day),
            }
        )

    reasons: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in refunds:
        reasons[r["reason"]][0] += 1
        reasons[r["reason"]][1] += r["amount"]
    refund_reasons = [
        {"reason": name, "count": n, "amount_cents": cents}
        for name, (n, cents) in sorted(reasons.items(), key=lambda kv: (-kv[1][1], kv[0]))
    ]

    categories: dict[str, list[int]] = defaultdict(list)
    waiting: dict[str, int] = defaultdict(int)
    for t in tickets:
        minutes = categories[t["category"]]
        if t["first_response_minutes"] is None:
            waiting[t["category"]] += 1
        else:
            minutes.append(t["first_response_minutes"])
    ticket_categories = [
        {
            "category": name,
            "count": len(minutes) + waiting[name],
            "awaiting_reply": waiting[name],
            "avg_first_response_min": ratio(sum(minutes), len(minutes), 1),
        }
        for name, minutes in sorted(
            categories.items(), key=lambda kv: (-(len(kv[1]) + waiting[kv[0]]), kv[0])
        )
    ]

    comparisons = {
        metric: compare(totals[metric], [w["totals"].get(metric) for w in prior_weeks], places)
        for metric, places in COMPARED.items()
    }

    alerts = []
    if totals["refund_rate"] is not None and totals["refund_rate"] > cfg.refund_rate_max:
        alerts.append(
            {
                "metric": "refund_rate",
                "message": f"Refund rate {totals['refund_rate']:.1%} is above the"
                f" {cfg.refund_rate_max:.1%} limit",
            }
        )
    if totals["paid_roas"] is not None and totals["paid_roas"] < cfg.paid_roas_min:
        alerts.append(
            {
                "metric": "paid_roas",
                "message": f"Return on ad spend {totals['paid_roas']:.2f}x is below the"
                f" {cfg.paid_roas_min:.2f}x floor",
            }
        )
    slow = totals["avg_first_response_min"]
    if slow is not None and slow > cfg.first_response_minutes_max:
        alerts.append(
            {
                "metric": "avg_first_response_min",
                "message": f"Average first response {slow:.0f} min is above the"
                f" {cfg.first_response_minutes_max:.0f} min limit",
            }
        )

    return {
        "company": cfg.company,
        "period": {
            "start": period.isoformat(),
            "end": period_end(period).isoformat(),
            "label": week_label(period),
        },
        "totals": totals,
        "channels": channels,
        "daily": daily,
        "refund_reasons": refund_reasons,
        "ticket_categories": ticket_categories,
        "comparisons": comparisons,
        "alerts": alerts,
        "row_counts": {kind: len(rows[kind]) for kind in sorted(rows)},
    }
