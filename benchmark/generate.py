"""Seeded generator: weekly exports for an invented shop, plus the true KPIs for each week.

The truth is worked out here from the generated records, with its own arithmetic, and never
imports the library's KPI code. If the two agree, it is because both are right.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path
from statistics import median

import xlsxwriter

SEED = 20260803
FIRST_WEEK = date(2026, 8, 3)
WEEKS = 12
COMPANY = "Fernhollow Supply Co."

# channel: (share of orders, typical order in dollars)
ORDER_MIX = {
    "Paid Search": (0.32, 49.0),
    "Paid Social": (0.24, 44.0),
    "Email": (0.16, 52.0),
    "Organic": (0.28, 46.0),
}
# label as the ad platform exports it -> (configured channel, dollars a day, cost per click)
AD_PLATFORMS = {
    "Google Ads": ("Paid Search", 520.0, 1.35),
    "Meta Ads": ("Paid Social", 430.0, 0.92),
    "Email": ("Email", 45.0, 0.11),
}
WEEKDAY_LIFT = (1.00, 0.95, 0.97, 1.02, 1.15, 1.25, 1.10)
REFUND_REASONS = (
    ("Changed mind", 30),
    ("Wrong size", 26),
    ("Damaged in transit", 16),
    ("Arrived late", 14),
    ("Not as described", 14),
)
TICKET_CATEGORIES = (
    ("Order status", 36),
    ("Returns", 24),
    ("Product question", 20),
    ("Billing", 11),
    ("Shipping damage", 9),
)
# One week gets a burst of transit damage, so the sample report has a KPI alert to show.
DAMAGE_WEEK = 7
SLA_MINUTES = 240

CONFIG_TOML = f"""\
# Weekly report settings. Paths are relative to this file.

[company]
name = "{COMPANY}"
currency_symbol = "$"

[paths]
inbox = "inbox"
output = "output"
outbox = "outbox"
state = "state"

[period]
# "latest" reports the newest week in the inbox. Or pin a week start date: "2026-09-21".
default = "latest"
trailing_weeks = 4

[channels]
names = ["Paid Search", "Paid Social", "Email", "Organic"]
paid = ["Paid Search", "Paid Social", "Email"]

# Labels as they appear in the exports, mapped to the names above.
[channels.aliases]
"google ads" = "Paid Search"
"meta ads" = "Paid Social"
"newsletter" = "Email"

# A KPI outside these limits is flagged on the report. It does not stop the run.
[thresholds]
refund_rate_max = 0.06
paid_roas_min = 3.0
first_response_minutes_max = 120
sla_minutes = {SLA_MINUTES}

# The data-quality gate. A swing or gap at the fail level stops the run.
[quality]
row_swing_warn = 0.30
row_swing_fail = 0.60
row_swing_min_rows = 100
date_gap_warn_days = 1
date_gap_fail_days = 2
outlier_multiple = 25
# Set to true once the source system sends a control totals file every week.
require_control_totals = false
control_tolerance = 0.00

[input]
# How slash dates are read: "mdy" (09/21/2026) or "dmy" (21/09/2026). ISO dates always work.
date_order = "mdy"
# Keep a copy of every accepted input file under state/archive/.
archive = true

[alerts]
# Optional heartbeat URL (Healthchecks.io and similar). Empty means no network call at all.
heartbeat_url = ""

# Dry run only: the message is saved to the outbox as an .eml file and never sent.
[delivery]
from = "reports@fernhollow.example"
to = ["owner@fernhollow.example"]
"""


@dataclass
class Week:
    start: date
    orders: list[dict] = field(default_factory=list)
    refunds: list[dict] = field(default_factory=list)
    ad_spend: list[dict] = field(default_factory=list)
    tickets: list[dict] = field(default_factory=list)

    @property
    def stamp(self) -> str:
        return self.start.isoformat()


def _pick(rng: random.Random, weighted: tuple[tuple[str, int], ...]) -> str:
    return rng.choices([w[0] for w in weighted], weights=[w[1] for w in weighted])[0]


def _dollars(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def generate(seed: int = SEED, weeks: int = WEEKS) -> list[Week]:
    rng = random.Random(seed)
    out: list[Week] = []
    order_no, refund_no, ticket_no = 100000, 5000, 70000
    channels = list(ORDER_MIX)
    weights = [ORDER_MIX[c][0] for c in channels]
    for index in range(weeks):
        week = Week(FIRST_WEEK + timedelta(weeks=index))
        growth = 1.015**index
        for offset in range(7):
            day = week.start + timedelta(days=offset)
            count = round(150 * growth * WEEKDAY_LIFT[offset] * rng.uniform(0.94, 1.06))
            for _ in range(count):
                order_no += 1
                channel = rng.choices(channels, weights=weights)[0]
                amount = max(600, round(ORDER_MIX[channel][1] * rng.lognormvariate(0, 0.42) * 100))
                week.orders.append(
                    {
                        "order_id": f"FH-{order_no}",
                        "order_date": day,
                        "channel": channel,
                        "items": rng.choices((1, 2, 3, 4), weights=(52, 30, 12, 6))[0],
                        "amount": amount,
                    }
                )
            for label, (_, per_day, cpc) in AD_PLATFORMS.items():
                spend = round(per_day * growth * rng.uniform(0.9, 1.1) * 100)
                week.ad_spend.append(
                    {
                        "date": day,
                        "channel": label,
                        "spend": spend,
                        "clicks": round(spend / 100 / (cpc * rng.uniform(0.9, 1.1))),
                    }
                )

        # Refunds booked this week come from this week's orders and last week's.
        pool = week.orders + (out[-1].orders[-300:] if out else [])
        rate = rng.uniform(0.028, 0.042) + (0.055 if index == DAMAGE_WEEK else 0)
        for order in rng.sample(pool, round(len(week.orders) * rate)):
            refund_no += 1
            full = rng.random() < 0.7
            reason = _pick(rng, REFUND_REASONS)
            if index == DAMAGE_WEEK and rng.random() < 0.5:
                reason = "Damaged in transit"
            week.refunds.append(
                {
                    "refund_id": f"RF-{refund_no}",
                    "order_id": order["order_id"],
                    "refund_date": max(order["order_date"], week.start)
                    + timedelta(days=rng.randint(0, 2)),
                    "amount": order["amount"]
                    if full
                    else round(order["amount"] * rng.uniform(0.2, 0.8)),
                    "reason": reason,
                }
            )
        for refund in week.refunds:
            refund["refund_date"] = min(refund["refund_date"], week.start + timedelta(days=6))
        week.refunds.sort(key=lambda r: (r["refund_date"], r["refund_id"]))

        for _ in range(round(len(week.orders) * 0.11) + rng.randint(-4, 4)):
            ticket_no += 1
            created = datetime.combine(week.start, datetime.min.time()) + timedelta(
                minutes=rng.randrange(7 * 24 * 60)
            )
            week.tickets.append(
                {
                    "ticket_id": f"T-{ticket_no}",
                    "created_at": created,
                    "category": _pick(rng, TICKET_CATEGORIES),
                    "first_response_minutes": None
                    if rng.random() < 0.04
                    else max(2, round(rng.lognormvariate(3.9, 0.9))),
                }
            )
        week.tickets.sort(key=lambda t: (t["created_at"], t["ticket_id"]))
        out.append(week)
    return out


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]


def write_spend_xlsx(path: Path, rows: list[list]) -> None:
    """rows: [date, channel, dollars, clicks]. A fixed created stamp keeps the file repeatable."""
    book = xlsxwriter.Workbook(str(path))
    book.set_properties({"created": datetime(2026, 1, 1)})
    sheet = book.add_worksheet("ad_spend")
    day = book.add_format({"num_format": "yyyy-mm-dd"})
    sheet.write_row(0, 0, ["Date", "Channel", "Spend", "Clicks"])
    for r, (when, channel, spend, clicks) in enumerate(rows, start=1):
        sheet.write_datetime(r, 0, when, day)
        sheet.write(r, 1, channel)
        sheet.write(r, 2, spend)
        sheet.write(r, 3, clicks)
    book.close()


def spend_rows(week: Week) -> list[list]:
    return [[s["date"], s["channel"], s["spend"] / 100, s["clicks"]] for s in week.ad_spend]


def write_control(week: Week, inbox: Path) -> None:
    """Totals as the source systems would state them, from the generated records."""
    write_csv(
        inbox / f"control_totals_{week.stamp}.csv",
        ["file", "metric", "value"],
        [
            ["orders", "rows", len(week.orders)],
            ["orders", "amount", _dollars(sum(o["amount"] for o in week.orders))],
            ["refunds", "rows", len(week.refunds)],
            ["refunds", "amount", _dollars(sum(r["amount"] for r in week.refunds))],
            ["ad_spend", "amount", _dollars(sum(s["spend"] for s in week.ad_spend))],
            ["tickets", "rows", len(week.tickets)],
        ],
    )


def write_week(week: Week, inbox: Path, control: bool = True) -> None:
    inbox.mkdir(parents=True, exist_ok=True)
    if control:
        write_control(week, inbox)
    write_csv(
        inbox / f"orders_{week.stamp}.csv",
        ["order_id", "order_date", "channel", "items", "amount"],
        [
            [
                o["order_id"],
                o["order_date"].isoformat(),
                o["channel"],
                o["items"],
                _dollars(o["amount"]),
            ]
            for o in week.orders
        ],
    )
    write_csv(
        inbox / f"refunds_{week.stamp}.csv",
        ["refund_id", "order_id", "refund_date", "amount", "reason"],
        [
            [
                r["refund_id"],
                r["order_id"],
                r["refund_date"].isoformat(),
                _dollars(r["amount"]),
                r["reason"],
            ]
            for r in week.refunds
        ],
    )
    write_spend_xlsx(inbox / f"ad_spend_{week.stamp}.xlsx", spend_rows(week))
    write_csv(
        inbox / f"tickets_{week.stamp}.csv",
        ["ticket_id", "created_at", "category", "first_response_minutes"],
        [
            [
                t["ticket_id"],
                t["created_at"].strftime("%Y-%m-%d %H:%M"),
                t["category"],
                "" if t["first_response_minutes"] is None else t["first_response_minutes"],
            ]
            for t in week.tickets
        ],
    )


# -- truth ------------------------------------------------------------------------


def _round(value: Fraction, places: int):
    quantum = Decimal(10) ** -places
    shown = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        quantum, rounding=ROUND_HALF_UP
    )
    return int(shown) if places == 0 else float(shown)


def _div(top: int, bottom: int, places: int):
    return None if bottom == 0 else _round(Fraction(top, bottom), places)


TRAILING_PLACES = {
    "revenue_cents": 0,
    "orders": 1,
    "aov_cents": 0,
    "refund_rate": 4,
    "spend_cents": 0,
    "paid_roas": 2,
    "tickets": 1,
    "avg_first_response_min": 1,
}


def truth_for(weeks: list[Week], trailing: int = 4) -> dict[str, dict]:
    """True KPIs per week start date, straight from the generated records."""
    platform_to_channel = {label: channel for label, (channel, _, _) in AD_PLATFORMS.items()}
    paid = set(platform_to_channel.values())
    result: dict[str, dict] = {}
    history: list[dict] = []
    for week in weeks:
        revenue = sum(o["amount"] for o in week.orders)
        refunded = sum(r["amount"] for r in week.refunds)
        spend = sum(s["spend"] for s in week.ad_spend)
        answered = [
            t["first_response_minutes"]
            for t in week.tickets
            if t["first_response_minutes"] is not None
        ]
        paid_revenue = sum(o["amount"] for o in week.orders if o["channel"] in paid)
        totals = {
            "revenue_cents": revenue,
            "orders": len(week.orders),
            "items": sum(o["items"] for o in week.orders),
            "aov_cents": _div(revenue, len(week.orders), 0),
            "refund_cents": refunded,
            "refunds": len(week.refunds),
            "refund_rate": _div(refunded, revenue, 4),
            "net_revenue_cents": revenue - refunded,
            "spend_cents": spend,
            "clicks": sum(s["clicks"] for s in week.ad_spend),
            "paid_revenue_cents": paid_revenue,
            "paid_roas": _div(paid_revenue, spend, 2),
            "tickets": len(week.tickets),
            "tickets_answered": len(answered),
            "avg_first_response_min": _div(sum(answered), len(answered), 1),
            "median_first_response_min": _round(Fraction(median(answered)), 1),
            "sla_met_rate": _div(
                sum(1 for m in answered if m <= SLA_MINUTES), len(week.tickets), 4
            ),
        }
        channels = {}
        for name in ORDER_MIX:
            mine = [o for o in week.orders if o["channel"] == name]
            ads = [s for s in week.ad_spend if platform_to_channel[s["channel"]] == name]
            channel_revenue = sum(o["amount"] for o in mine)
            channel_spend = sum(s["spend"] for s in ads)
            channel_clicks = sum(s["clicks"] for s in ads)
            channels[name] = {
                "revenue_cents": channel_revenue,
                "orders": len(mine),
                "aov_cents": _div(channel_revenue, len(mine), 0),
                "revenue_share": _div(channel_revenue, revenue, 4),
                "spend_cents": channel_spend,
                "clicks": channel_clicks,
                "roas": _div(channel_revenue, channel_spend, 2),
                "cpc_cents": _div(channel_spend, channel_clicks, 0),
            }
        comparisons = {}
        window = history[-trailing:]
        for metric, places in TRAILING_PLACES.items():
            now = Fraction(str(totals[metric]))
            before = [Fraction(str(h[metric])) for h in window]
            mean = sum(before) / len(before) if before else None
            comparisons[metric] = {
                "wow_pct": _round((now - before[-1]) / before[-1], 4) if before else None,
                "trailing_avg": _round(mean, places) if before else None,
                "vs_trailing_pct": _round((now - mean) / mean, 4) if before else None,
            }
        history.append(totals)
        result[week.stamp] = {"totals": totals, "channels": channels, "comparisons": comparisons}
    return result
