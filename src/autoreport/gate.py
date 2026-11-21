"""The data-quality gate. Every check returns findings; any `fail` stops the run."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import median

from autoreport.config import Config
from autoreport.findings import FAIL, INFO, WARN, Finding, sort_findings
from autoreport.ingest import (
    AMOUNT_COLUMN,
    DATE_COLUMN,
    KEY_COLUMNS,
    KINDS,
    ControlTotals,
    Table,
    period_days,
    period_end,
)
from autoreport.state import State

__all__ = ["Finding", "check_control", "check_files", "run_gate", "has_failures"]

NON_NEGATIVE = {
    "orders": ("amount", "items"),
    "refunds": ("amount",),
    "ad_spend": ("spend", "clicks"),
    "tickets": ("first_response_minutes",),
}
CHANNEL_KINDS = ("orders", "ad_spend")
OUTLIER_COLUMNS = {"orders": "amount", "refunds": "amount", "ad_spend": "spend"}
OUTLIER_MIN_GROUP = 5


def has_failures(findings: list[Finding]) -> bool:
    return any(f.level == FAIL for f in findings)


def _plural(count: int, word: str) -> str:
    return f"{count:,} {word}" if count == 1 else f"{count:,} {word}s"


def check_files(files: dict[str, list[Path]], period: date) -> list[Finding]:
    """Each kind must arrive exactly once for the period."""
    findings = []
    for kind in KINDS:
        paths = files.get(kind, [])
        if not paths:
            findings.append(
                Finding(
                    FAIL,
                    "missing_file",
                    f"{kind}_{period.isoformat()}.csv",
                    f"no {kind} export for the week of {period.isoformat()} (.csv or .xlsx)",
                )
            )
        elif len(paths) > 1:
            names = ", ".join(p.name for p in paths)
            findings.append(
                Finding(
                    FAIL,
                    "duplicate_file",
                    paths[1].name,
                    f"{len(paths)} {kind} files for the same week ({names}); keep one",
                )
            )
    return findings


def _schema(table: Table) -> list[Finding]:
    out = []
    if table.error:
        return [Finding(FAIL, "unreadable_file", table.name, f"file {table.error}")]
    if table.missing_columns:
        columns = ", ".join(f"'{c}'" for c in table.missing_columns)
        found = ", ".join(table.headers) or "none"
        out.append(
            Finding(
                FAIL,
                "missing_column",
                table.name,
                f"missing required column {columns} (columns found: {found})",
            )
        )
    for column, bad in sorted(table.bad_values.items()):
        row, raw = bad[0]
        what = "left blank" if all(text == "" for _, text in bad) else "could not be read"
        example = "blank" if raw == "" else f"'{raw}'"
        out.append(
            Finding(
                FAIL,
                "bad_value",
                table.name,
                f"{_plural(len(bad), 'value')} in column '{column}' {what}"
                f" (first at row {row}: {example})",
            )
        )
    return out


def _empty(table: Table) -> list[Finding]:
    if table.rows:
        return []
    if table.kind == "orders":
        return [Finding(FAIL, "empty_file", table.name, "file has a header but no rows")]
    return [
        Finding(
            WARN,
            "empty_file",
            table.name,
            f"file has a header but no rows; {table.kind} are reported as zero",
        )
    ]


def _duplicates(table: Table) -> list[Finding]:
    keys = KEY_COLUMNS[table.kind]
    if not all(table.has(k) for k in keys):
        return []
    counts = Counter(tuple(row[k] for k in keys) for row in table.rows)
    repeated = sorted(
        (key for key, n in counts.items() if n > 1 and None not in key), key=lambda k: str(k)
    )
    if not repeated:
        return []
    extra = sum(counts[key] - 1 for key in repeated)
    label = " + ".join(keys)
    first = " / ".join(str(v) for v in repeated[0])
    return [
        Finding(
            FAIL,
            "duplicate_id",
            table.name,
            f"{_plural(len(repeated), f'{label} value')} appear more than once"
            f" ({_plural(extra, 'extra row')}; first: {first})",
        )
    ]


def _negatives(table: Table) -> list[Finding]:
    out = []
    for column in NON_NEGATIVE[table.kind]:
        if not table.has(column):
            continue
        hits = [
            (number, row[column])
            for number, row in enumerate(table.rows, start=2)
            if row[column] is not None and row[column] < 0
        ]
        if hits:
            out.append(
                Finding(
                    FAIL,
                    "negative_value",
                    table.name,
                    f"{_plural(len(hits), 'negative value')} in column '{column}'"
                    f" (first at row {hits[0][0]})",
                )
            )
    return out


def _dates(table: Table, period: date, cfg: Config) -> list[Finding]:
    column = DATE_COLUMN[table.kind]
    if not table.has(column):
        return []
    out = []
    start, end = period, period_end(period)
    dates = [row[column] for row in table.rows if row[column] is not None]
    outside = [d for d in dates if not start <= d <= end]
    if outside:
        out.append(
            Finding(
                FAIL,
                "date_out_of_period",
                table.name,
                f"{_plural(len(outside), 'row')} dated outside {start.isoformat()} to"
                f" {end.isoformat()} (earliest {min(outside).isoformat()},"
                f" latest {max(outside).isoformat()}); is this the right week's file?",
            )
        )

    days = period_days(period)
    if table.kind == "orders" and dates:
        seen = set(dates)
        gaps = [d for d in days if d not in seen]
        if gaps:
            level = FAIL if len(gaps) >= cfg.date_gap_fail_days else WARN
            listed = ", ".join(d.strftime("%a %Y-%m-%d") for d in gaps)
            out.append(Finding(level, "date_gap", table.name, f"no orders at all on {listed}"))
    if table.kind == "ad_spend" and dates and table.has("channel"):
        seen_pairs = {
            (row[column], cfg.canonical_channel(row["channel"]))
            for row in table.rows
            if row[column] is not None and row["channel"] is not None
        }
        gaps = [(d, c) for c in cfg.paid_channels for d in days if (d, c) not in seen_pairs]
        if gaps:
            listed = ", ".join(f"{c} {d.strftime('%a %Y-%m-%d')}" for d, c in gaps[:4])
            more = f" and {len(gaps) - 4} more" if len(gaps) > 4 else ""
            out.append(
                Finding(
                    WARN,
                    "date_gap",
                    table.name,
                    f"no spend row for {listed}{more}; spend for those days counts as zero",
                )
            )
    return out


def _channels(table: Table, cfg: Config) -> list[Finding]:
    if table.kind not in CHANNEL_KINDS or not table.has("channel"):
        return []
    unknown = Counter(
        row["channel"]
        for row in table.rows
        if row["channel"] is not None and cfg.canonical_channel(row["channel"]) is None
    )
    if not unknown:
        return []
    listed = ", ".join(f"'{name}' ({n:,})" for name, n in sorted(unknown.items()))
    return [
        Finding(
            WARN,
            "unknown_channel",
            table.name,
            f"{_plural(sum(unknown.values()), 'row')} use a channel that is not in the config:"
            f" {listed}; reported under 'Unmapped'",
        )
    ]


def _outliers(table: Table, cfg: Config) -> list[Finding]:
    """A value far above its group's typical value: a slipped decimal point, most often."""
    column = OUTLIER_COLUMNS.get(table.kind)
    if column is None or not table.has(column):
        return []
    by_channel = table.kind == "ad_spend" and table.has("channel")
    groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for number, row in enumerate(table.rows, start=2):
        if row[column] is not None and row[column] > 0:
            groups[str(row["channel"]) if by_channel else ""].append((number, row[column]))
    hits = []
    for values in groups.values():
        if len(values) < OUTLIER_MIN_GROUP:
            continue
        typical = median(v for _, v in values)
        hits += [(n, v, typical) for n, v in values if v > typical * cfg.outlier_multiple]
    if not hits:
        return []
    number, value, typical = max(hits, key=lambda h: h[1])
    return [
        Finding(
            WARN,
            "outlier_value",
            table.name,
            f"{_plural(len(hits), 'value')} in column '{column}' above"
            f" {cfg.outlier_multiple:g}x the typical value (largest {value / 100:,.2f} at row"
            f" {number}, typical {typical / 100:,.2f}); check for a slipped decimal point",
        )
    ]


def _row_swing(table: Table, period: date, cfg: Config, state: State) -> list[Finding]:
    prior = [
        week["row_counts"][table.kind]
        for week in state.prior_weeks(period, cfg.trailing_weeks)
        if table.kind in week.get("row_counts", {})
    ]
    if not prior:
        if table.kind == "orders":
            return [
                Finding(
                    INFO,
                    "row_count_swing",
                    table.name,
                    "no earlier week on record, so the row-count check was skipped",
                )
            ]
        return []
    average = sum(prior) / len(prior)
    # Small files swing a lot by chance; checking them would train people to ignore warnings.
    if average < cfg.row_swing_min_rows:
        return []
    change = (len(table.rows) - average) / average
    if abs(change) < cfg.row_swing_warn:
        return []
    level = FAIL if abs(change) >= cfg.row_swing_fail else WARN
    hint = "a cut-off export" if change < 0 else "a doubled-up export"
    return [
        Finding(
            level,
            "row_count_swing",
            table.name,
            f"{len(table.rows):,} rows is {change:+.0%} against the average of {average:,.0f}"
            f" over the last {_plural(len(prior), 'week')}; check for {hint}",
        )
    ]


def _ledger(table: Table, period: date, state: State) -> list[Finding]:
    seen = state.find_content(table.sha256, period, table.kind)
    if seen:
        other_period, other_kind, other_file = seen
        return [
            Finding(
                FAIL,
                "already_processed",
                table.name,
                f"content is identical to {other_file}, already processed as {other_kind}"
                f" for the week of {other_period}",
            )
        ]
    previous = state.previous_sha(period, table.kind)
    if previous and previous != table.sha256:
        return [
            Finding(
                WARN,
                "restated_file",
                table.name,
                "content changed since this week was last processed; the week is restated",
            )
        ]
    return []


def check_control(
    tables: dict[str, Table], controls: list[ControlTotals], period: date, cfg: Config
) -> list[Finding]:
    """Reconcile row counts and amount totals with the source system's own figures."""
    expected_name = f"control_totals_{period.isoformat()}.csv"
    if not controls:
        if cfg.require_control_totals:
            return [
                Finding(
                    FAIL,
                    "missing_file",
                    expected_name,
                    "no control totals file for the week, and the config requires one",
                )
            ]
        return []
    if len(controls) > 1:
        names = ", ".join(c.name for c in controls)
        return [
            Finding(
                FAIL,
                "duplicate_file",
                controls[1].name,
                f"{len(controls)} control totals files for the same week ({names}); keep one",
            )
        ]
    control = controls[0]
    out = [Finding(FAIL, "control_total", control.name, p) for p in control.problems]
    matched = 0
    for (kind, metric), expected in sorted(control.expected.items()):
        table = tables.get(kind)
        if table is None or table.error:
            continue
        if metric == "rows":
            actual, tolerance = len(table.rows), 0
            shown = f"file has {actual:,} rows, source system says {expected:,}"
        else:
            column = AMOUNT_COLUMN[kind]
            if not table.has(column):
                continue
            actual = sum(row[column] or 0 for row in table.rows)
            tolerance = cfg.control_tolerance_cents
            shown = (
                f"column '{column}' adds up to {actual / 100:,.2f}, source system says"
                f" {expected / 100:,.2f}"
            )
        if abs(actual - expected) > tolerance:
            gap = actual - expected
            gap_text = f"{gap:+,}" if metric == "rows" else f"{gap / 100:+,.2f}"
            out.append(
                Finding(FAIL, "control_total", table.name, f"{shown} (difference {gap_text})")
            )
        else:
            matched += 1
    if matched and not out:
        out.append(
            Finding(
                INFO,
                "control_total",
                control.name,
                f"{matched} control totals from the source system match the files exactly"
                if cfg.control_tolerance_cents == 0
                else f"{matched} control totals from the source system match within tolerance",
            )
        )
    return out


def run_gate(tables: dict[str, Table], period: date, cfg: Config, state: State) -> list[Finding]:
    findings: list[Finding] = []
    for kind in KINDS:
        table = tables.get(kind)
        if table is None:
            continue
        findings += _schema(table)
        if table.error:
            continue
        findings += _empty(table)
        findings += _duplicates(table)
        findings += _negatives(table)
        findings += _dates(table, period, cfg)
        findings += _channels(table, cfg)
        findings += _outliers(table, cfg)
        findings += _row_swing(table, period, cfg, state)
        findings += _ledger(table, period, state)
    return sort_findings(findings)
