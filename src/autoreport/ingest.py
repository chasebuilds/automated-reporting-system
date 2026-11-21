"""Find the period's files in the inbox, read them, and parse every cell to a typed value.

Nothing is dropped here. A value that does not parse is kept as None and recorded in
`Table.bad_values`, so the gate can name the file, column and row.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

import openpyxl

KINDS = ("orders", "refunds", "ad_spend", "tickets")
FILE_RE = re.compile(
    r"^(orders|refunds|ad_spend|tickets|control_totals)_(\d{4}-\d{2}-\d{2})(.*)\.(csv|xlsx)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Column:
    name: str
    type: str  # str | date | money | int
    blank_ok: bool = False


SCHEMAS: dict[str, tuple[Column, ...]] = {
    "orders": (
        Column("order_id", "str"),
        Column("order_date", "date"),
        Column("channel", "str"),
        Column("items", "int"),
        Column("amount", "money"),
    ),
    "refunds": (
        Column("refund_id", "str"),
        Column("order_id", "str"),
        Column("refund_date", "date"),
        Column("amount", "money"),
        Column("reason", "str"),
    ),
    "ad_spend": (
        Column("date", "date"),
        Column("channel", "str"),
        Column("spend", "money"),
        Column("clicks", "int"),
    ),
    "tickets": (
        Column("ticket_id", "str"),
        Column("created_at", "date"),
        Column("category", "str"),
        # Blank means the ticket has not had a first reply yet.
        Column("first_response_minutes", "int", blank_ok=True),
    ),
}
DATE_COLUMN = {
    "orders": "order_date",
    "refunds": "refund_date",
    "ad_spend": "date",
    "tickets": "created_at",
}
KEY_COLUMNS = {
    "orders": ("order_id",),
    "refunds": ("refund_id",),
    "ad_spend": ("date", "channel"),
    "tickets": ("ticket_id",),
}
ISO_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S")
# Slash dates are read one way only, set in the config. Guessing between month-first
# and day-first would silently move the first twelve days of every month.
SLASH_FORMATS = {"mdy": "%m/%d/%Y", "dmy": "%d/%m/%Y"}
CONTROL = "control_totals"
AMOUNT_COLUMN = {"orders": "amount", "refunds": "amount", "ad_spend": "spend"}


@dataclass
class Table:
    kind: str
    path: Path
    sha256: str
    headers: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    # column -> [(spreadsheet row number, raw text)]
    bad_values: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    error: str | None = None

    @property
    def name(self) -> str:
        return self.path.name

    def has(self, column: str) -> bool:
        return column not in self.missing_columns


def period_end(period: date) -> date:
    return period + timedelta(days=6)


def period_days(period: date) -> list[date]:
    return [period + timedelta(days=i) for i in range(7)]


def parse_period(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"period must be a week start date like 2026-09-21, got '{text}'") from exc


def scan_inbox(inbox: Path) -> dict[date, dict[str, list[Path]]]:
    """Group inbox files by week start date and kind. Unrecognised names are ignored."""
    found: dict[date, dict[str, list[Path]]] = {}
    if not inbox.is_dir():
        return found
    for path in sorted(inbox.iterdir()):
        match = FILE_RE.match(path.name)
        if not path.is_file() or not match or path.name.startswith("~$"):
            continue
        try:
            period = date.fromisoformat(match.group(2))
        except ValueError:
            continue
        found.setdefault(period, {}).setdefault(match.group(1).lower(), []).append(path)
    return found


def _header(text: object) -> str:
    return re.sub(r"[\s\-]+", "_", str(text or "").strip().lower())


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _read_raw(path: Path) -> list[list[str]]:
    if path.suffix.lower() == ".xlsx":
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            return [
                [_cell(v) for v in row] for row in book.worksheets[0].iter_rows(values_only=True)
            ]
        finally:
            book.close()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [[_cell(v) for v in row] for row in csv.reader(handle)]


def parse_money(text: str) -> int:
    """Dollars as text to integer cents, so sums never pick up float error."""
    cleaned = text.replace("$", "").replace(",", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    value = Decimal(cleaned)
    if not value.is_finite():
        raise InvalidOperation(text)
    return int((value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def parse_date(text: str, order: str = "mdy") -> date:
    for fmt in (*ISO_FORMATS, SLASH_FORMATS[order]):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(text)


def parse_int(text: str) -> int:
    value = Decimal(text.replace(",", ""))
    if value != value.to_integral_value():
        raise ValueError(text)
    return int(value)


PARSERS = {"str": str, "date": parse_date, "money": parse_money, "int": parse_int}


def read_table(kind: str, path: Path, date_order: str = "mdy") -> Table:
    table = Table(kind=kind, path=path, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    try:
        raw = _read_raw(path)
    except Exception as exc:  # noqa: BLE001 - any unreadable file is a gate failure, not a crash
        table.error = f"could not be read ({type(exc).__name__}: {exc})"
        return table
    raw = [row for row in raw if any(cell != "" for cell in row)]
    if not raw:
        table.error = "is empty (no header row)"
        return table

    table.headers = [_header(h) for h in raw[0]]
    index = {name: i for i, name in enumerate(table.headers) if name}
    schema = SCHEMAS[kind]
    table.missing_columns = [c.name for c in schema if c.name not in index]
    present = [c for c in schema if c.name in index]

    for row_number, cells in enumerate(raw[1:], start=2):
        row: dict = {}
        for column in present:
            position = index[column.name]
            text = cells[position] if position < len(cells) else ""
            if text == "":
                row[column.name] = None
                if not column.blank_ok:
                    table.bad_values.setdefault(column.name, []).append((row_number, ""))
                continue
            try:
                row[column.name] = (
                    parse_date(text, date_order)
                    if column.type == "date"
                    else PARSERS[column.type](text)
                )
            except (ValueError, InvalidOperation):
                row[column.name] = None
                table.bad_values.setdefault(column.name, []).append((row_number, text))
        table.rows.append(row)
    return table


@dataclass
class ControlTotals:
    """Totals from the source system, to reconcile the exports against."""

    path: Path
    sha256: str
    # (file kind, "rows" or "amount") -> expected value; amounts in cents
    expected: dict[tuple[str, str], int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name


def read_control(path: Path) -> ControlTotals:
    """Read control_totals_<week>.csv: columns file, metric (rows or amount), value."""
    control = ControlTotals(path=path, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    try:
        raw = [row for row in _read_raw(path) if any(cell != "" for cell in row)]
    except Exception as exc:  # noqa: BLE001 - reported by the gate, not raised
        control.problems.append(f"could not be read ({type(exc).__name__}: {exc})")
        return control
    headers = [_header(h) for h in raw[0]] if raw else []
    if missing := [c for c in ("file", "metric", "value") if c not in headers]:
        control.problems.append(f"missing required column {', '.join(missing)}")
        return control
    at = {name: headers.index(name) for name in ("file", "metric", "value")}
    for number, cells in enumerate(raw[1:], start=2):
        cells = cells + [""] * (len(headers) - len(cells))
        kind, metric, text = (cells[at[c]].strip().lower() for c in ("file", "metric", "value"))
        if kind not in KINDS or metric not in ("rows", "amount"):
            control.problems.append(f"row {number}: '{kind} {metric}' is not a known total")
            continue
        if metric == "amount" and kind not in AMOUNT_COLUMN:
            control.problems.append(f"row {number}: {kind} has no amount column to total")
            continue
        try:
            value = parse_int(text) if metric == "rows" else parse_money(text)
        except (ValueError, InvalidOperation):
            control.problems.append(f"row {number}: value '{text}' could not be read")
            continue
        control.expected[(kind, metric)] = value
    return control
