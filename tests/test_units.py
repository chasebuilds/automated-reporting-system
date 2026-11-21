from __future__ import annotations

from datetime import date
from decimal import InvalidOperation
from fractions import Fraction
from pathlib import Path

import pytest

from autoreport.config import ConfigError, load_config
from autoreport.ingest import parse_date, parse_int, parse_money, read_table, scan_inbox
from autoreport.kpis import compare, ratio, round_half_up

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("text", "cents"),
    [("12.34", 1234), ("$1,234.50", 123450), ("7", 700), ("(5.00)", -500), ("0.005", 1)],
)
def test_parse_money(text, cents):
    assert parse_money(text) == cents


@pytest.mark.parametrize("text", ["N/A", "", "12.3.4", "NaN"])
def test_parse_money_rejects(text):
    with pytest.raises((InvalidOperation, ValueError)):
        parse_money(text)


def test_parse_date_and_int():
    assert parse_date("2026-09-21 14:05") == date(2026, 9, 21)
    assert parse_date("09/21/2026") == date(2026, 9, 21)
    assert parse_int("1,200") == 1200 and parse_int("3.0") == 3
    with pytest.raises(ValueError):
        parse_int("3.5")
    with pytest.raises(ValueError):
        parse_date("21st of September")


def test_rounding_is_half_up_not_bankers():
    assert round_half_up(Fraction(5, 2), 0) == 3
    assert round_half_up(Fraction(125, 1000), 2) == 0.13
    assert ratio(1, 0, 2) is None


def test_compare_skips_missing_weeks_in_average():
    out = compare(120, [100, None, 80], 1)
    assert out["previous"] == 80 and out["wow_pct"] == 0.5
    assert out["trailing_avg"] == 90.0 and out["trailing_weeks"] == 2
    assert compare(5, [], 1)["wow_pct"] is None


def test_read_table_reports_bad_cells_without_dropping_rows(tmp_path):
    path = tmp_path / "orders_2026-09-21.csv"
    path.write_text(
        "Order ID,Order Date,Channel,Items,Amount\n"
        "A1,2026-09-21,Email,1,10.00\n"
        "A2,not a date,Email,1,\n",
        encoding="utf-8",
    )
    table = read_table("orders", path)
    assert len(table.rows) == 2 and table.missing_columns == []
    assert table.bad_values == {"order_date": [(3, "not a date")], "amount": [(3, "")]}


def test_scan_inbox_ignores_other_files(tmp_path):
    for name in (
        "orders_2026-09-21.csv",
        "notes.txt",
        "~$orders_2026-09-21.xlsx",
        "orders_2026-13-45.csv",
        "tickets_2026-09-21 (1).csv",
    ):
        (tmp_path / name).write_text("x", encoding="utf-8")
    found = scan_inbox(tmp_path)
    assert list(found) == [date(2026, 9, 21)]
    assert sorted(found[date(2026, 9, 21)]) == ["orders", "tickets"]


def test_config_aliases_and_errors(tmp_path):
    good = tmp_path / "report.toml"
    good.write_text(
        '[channels]\nnames = ["A", "B"]\npaid = ["A"]\n[channels.aliases]\n"a ads" = "A"\n'
    )
    cfg = load_config(good)
    assert cfg.canonical_channel("  A  ADS ") == "A" and cfg.canonical_channel("b") == "B"
    assert cfg.canonical_channel("C") is None and cfg.inbox == tmp_path / "inbox"
    for body in (
        '[channels]\nnames = ["A"]\npaid = ["Z"]\n',
        "[quality]\nrow_swing_warn = 0.9\n",
        "not toml [",
    ):
        bad = tmp_path / "bad.toml"
        bad.write_text(body)
        with pytest.raises(ConfigError):
            load_config(bad)


def test_repo_text_has_no_em_dash():
    skip = {".venv", ".git", "_work", "__pycache__", ".pytest_cache", ".ruff_cache"}
    for path in ROOT.rglob("*"):
        if skip & set(path.parts) or path.suffix not in {".py", ".md", ".toml", ".yml", ".html"}:
            continue
        assert chr(0x2014) not in path.read_text(encoding="utf-8"), path
