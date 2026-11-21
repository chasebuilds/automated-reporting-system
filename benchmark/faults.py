"""Deliberately corrupted weeks. Each fault changes one thing in a clean week's inbox."""

from __future__ import annotations

import random
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from benchmark.generate import (
    Week,
    read_csv,
    spend_rows,
    write_csv,
    write_spend_xlsx,
    write_week,
)


@dataclass(frozen=True)
class Fault:
    name: str
    what: str
    expected_level: str  # fail | warn
    expected_checks: tuple[str, ...]
    apply: Callable[[Path, Week, Week, random.Random], None]


def _orders(inbox: Path, week: Week) -> Path:
    return inbox / f"orders_{week.stamp}.csv"


def _edit(path: Path, change: Callable[[list[str], list[list[str]]], list[list[str]]]) -> None:
    header, rows = read_csv(path)
    rows = change(header, rows)
    write_csv(path, header, rows)


def _drop_share(share: float):
    def apply(inbox: Path, week: Week, _prev: Week, rng: random.Random) -> None:
        def change(_header, rows):
            keep = set(rng.sample(range(len(rows)), round(len(rows) * (1 - share))))
            return [row for i, row in enumerate(rows) if i in keep]

        _edit(_orders(inbox, week), change)

    return apply


def _drop_days(*offsets: int):
    def apply(inbox: Path, week: Week, _prev: Week, _rng: random.Random) -> None:
        days = {(week.start + timedelta(days=o)).isoformat() for o in offsets}
        _edit(_orders(inbox, week), lambda _h, rows: [r for r in rows if r[1] not in days])

    return apply


def missing_file(inbox, week, _prev, _rng):
    (inbox / f"refunds_{week.stamp}.csv").unlink()


def missing_column(inbox, week, _prev, _rng):
    path = _orders(inbox, week)
    header, rows = read_csv(path)
    drop = header.index("amount")
    write_csv(path, [h for h in header if h != "amount"], [r[:drop] + r[drop + 1 :] for r in rows])


def duplicate_orders(inbox, week, _prev, _rng):
    _edit(_orders(inbox, week), lambda _h, rows: rows + rows[200:240])


def negative_amount(inbox, week, _prev, rng):
    def change(header, rows):
        row = rows[rng.randrange(len(rows))]
        row[header.index("amount")] = "-" + row[header.index("amount")]
        return rows

    _edit(_orders(inbox, week), change)


def text_in_amount(inbox, week, _prev, rng):
    def change(header, rows):
        for i in rng.sample(range(len(rows)), 3):
            rows[i][header.index("amount")] = "N/A"
        return rows

    _edit(_orders(inbox, week), change)


def wrong_week(inbox, week, prev, _rng):
    scratch = inbox / "_previous"
    write_week(prev, scratch)
    shutil.copy(scratch / f"orders_{prev.stamp}.csv", _orders(inbox, week))
    shutil.rmtree(scratch)


def delivered_twice(inbox, week, _prev, _rng):
    shutil.copy(_orders(inbox, week), inbox / f"orders_{week.stamp} (1).csv")


def unknown_channel(inbox, week, _prev, rng):
    def change(header, rows):
        for i in rng.sample(range(len(rows)), 30):
            rows[i][header.index("channel")] = "TikTok Shop"
        return rows

    _edit(_orders(inbox, week), change)


def missing_spend_day(inbox, week, _prev, _rng):
    gap: date = week.start + timedelta(days=3)
    write_spend_xlsx(
        inbox / f"ad_spend_{week.stamp}.xlsx", [r for r in spend_rows(week) if r[0] != gap]
    )


def decimal_slip(inbox, week, _prev, _rng):
    rows = spend_rows(week)
    rows[4][2] = rows[4][2] * 100
    write_spend_xlsx(inbox / f"ad_spend_{week.stamp}.xlsx", rows)


def corrupt_workbook(inbox, week, _prev, _rng):
    path = inbox / f"ad_spend_{week.stamp}.xlsx"
    path.write_bytes(path.read_bytes()[:900])


def negative_response(inbox, week, _prev, _rng):
    def change(header, rows):
        rows[10][header.index("first_response_minutes")] = "-15"
        return rows

    _edit(inbox / f"tickets_{week.stamp}.csv", change)


def empty_refunds(inbox, week, _prev, _rng):
    _edit(inbox / f"refunds_{week.stamp}.csv", lambda _h, _rows: [])


FAULTS: tuple[Fault, ...] = (
    Fault("missing_file", "Refunds export not delivered", "fail", ("missing_file",), missing_file),
    Fault(
        "missing_column",
        "Orders export has no amount column",
        "fail",
        ("missing_column",),
        missing_column,
    ),
    Fault(
        "duplicate_orders",
        "40 order rows pasted in twice",
        "fail",
        ("duplicate_id",),
        duplicate_orders,
    ),
    Fault(
        "negative_amount",
        "One order amount is negative",
        "fail",
        ("negative_value",),
        negative_amount,
    ),
    Fault("text_in_amount", "Three order amounts say N/A", "fail", ("bad_value",), text_in_amount),
    Fault(
        "wrong_week",
        "Last week's orders file sent again under this week's name",
        "fail",
        ("date_out_of_period", "already_processed"),
        wrong_week,
    ),
    Fault(
        "delivered_twice",
        "Orders file present twice, second copy named (1)",
        "fail",
        ("duplicate_file",),
        delivered_twice,
    ),
    Fault(
        "truncated_export",
        "Orders export lost 65% of its rows",
        "fail",
        ("row_count_swing",),
        _drop_share(0.65),
    ),
    Fault(
        "weekend_missing",
        "No orders for Saturday or Sunday",
        "fail",
        ("date_gap",),
        _drop_days(5, 6),
    ),
    Fault(
        "corrupt_workbook",
        "Ad spend workbook cut off mid-download",
        "fail",
        ("unreadable_file",),
        corrupt_workbook,
    ),
    Fault(
        "negative_response",
        "One ticket has a negative response time",
        "fail",
        ("negative_value",),
        negative_response,
    ),
    Fault(
        "partial_export",
        "Orders export lost 38% of its rows",
        "warn",
        ("row_count_swing",),
        _drop_share(0.38),
    ),
    Fault("one_day_missing", "No orders for Wednesday", "warn", ("date_gap",), _drop_days(2)),
    Fault(
        "unknown_channel",
        "30 orders tagged with a channel not in the config",
        "warn",
        ("unknown_channel",),
        unknown_channel,
    ),
    Fault(
        "missing_spend_day",
        "Ad spend has no rows for Thursday",
        "warn",
        ("date_gap",),
        missing_spend_day,
    ),
    Fault(
        "decimal_slip",
        "One ad spend value is 100 times too large",
        "warn",
        ("outlier_value",),
        decimal_slip,
    ),
    Fault(
        "empty_refunds",
        "Refunds export has a header and no rows",
        "warn",
        ("empty_file",),
        empty_refunds,
    ),
    Fault(
        "small_silent_loss",
        "Orders export lost 3% of its rows at random",
        "warn",
        ("row_count_swing",),
        _drop_share(0.03),
    ),
)
