"""Command line entry point.

Exit codes: 0 done, 1 the gate refused the data (or `compare` found a difference),
2 bad command, bad config, nothing to run, or another run in progress.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from autoreport.alerts import ping
from autoreport.compare import compare_period, format_rows
from autoreport.config import Config, ConfigError, load_config
from autoreport.ingest import parse_period, scan_inbox
from autoreport.pipeline import NoInputError, resolve_period, run_period
from autoreport.state import RunLockedError, State

EXIT_OK, EXIT_GATE, EXIT_USAGE = 0, 1, 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoreport",
        description="Build the weekly report from the inbox, or refuse if the data is bad.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("run", "validate the week's files and write the report"),
        ("check", "run the data-quality gate only, write nothing"),
    ):
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("--config", default="report.toml", help="path to the TOML config")
        cmd.add_argument("--period", help="week start date, e.g. 2026-09-21 (default: config)")
        cmd.add_argument("--inbox", help="read exports from this folder instead of the config's")
        if name == "run":
            cmd.add_argument("--all", action="store_true", help="every week in the inbox, in order")
            cmd.add_argument("--no-email", action="store_true", help="skip the outbox .eml files")
    status = sub.add_parser("status", help="list the weeks already processed")
    status.add_argument("--config", default="report.toml")
    compare = sub.add_parser(
        "compare", help="compare a processed week with a hand-made report (parallel run)"
    )
    compare.add_argument("--config", default="report.toml")
    compare.add_argument("--period", required=True, help="week start date already processed")
    compare.add_argument("--manual", required=True, help="CSV with the columns metric,value")
    return parser


def _load(args: argparse.Namespace) -> Config:
    cfg = load_config(args.config)
    if getattr(args, "inbox", None):
        cfg = replace(cfg, inbox=Path(args.inbox).resolve())
    return cfg


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = _load(args)
        if args.command == "status":
            return _status(cfg)
        if args.command == "compare":
            return _compare(cfg, args.period, Path(args.manual))
        if getattr(args, "all", False):
            periods = sorted(scan_inbox(cfg.inbox))
            if not periods:
                raise NoInputError(f"no export files found in {cfg.inbox}")
        else:
            periods = [parse_period(args.period) if args.period else resolve_period(cfg, None)]
        return _run(cfg, args, periods)
    except (ConfigError, NoInputError, RunLockedError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


def _run(cfg: Config, args: argparse.Namespace, periods: list) -> int:
    # The heartbeat belongs to scheduled runs. A check or an ad hoc inbox must not report
    # "this week's job ran" to the monitor.
    beat = cfg.heartbeat_url if args.command == "run" and not args.inbox else ""
    for period in periods:
        result = run_period(
            cfg,
            period,
            deliver=not getattr(args, "no_email", False),
            check_only=args.command == "check",
            echo=print,
        )
        if not result.ok:
            if beat:
                print(f"[alert    ] {ping(beat, ok=False)}")
            print(
                f"\nNo report for the week of {period.isoformat()}:"
                f" {len(result.failures)} data problem(s) must be fixed first.",
                file=sys.stderr,
            )
            for finding in result.failures:
                print(f"  {finding.file}: {finding.message}", file=sys.stderr)
            return EXIT_GATE
        print()
    if beat:
        print(f"[alert    ] {ping(beat, ok=True)}")
    return EXIT_OK


def _status(cfg: Config) -> int:
    state = State(cfg.state)
    if not state.history:
        print("no weeks processed yet")
        return EXIT_OK
    print(f"{'week of':12} {'revenue':>14} {'orders':>8}  files")
    for period, entry in sorted(state.history.items()):
        totals = entry["totals"]
        files = ", ".join(e["file"] for _, e in sorted(state.ledger.get(period, {}).items()))
        print(
            f"{period:12} {totals['revenue_cents'] / 100:>14,.2f} {totals['orders']:>8,}  {files}"
        )
    return EXIT_OK


def _compare(cfg: Config, period_text: str, manual: Path) -> int:
    period = parse_period(period_text).isoformat()
    entry = State(cfg.state).history.get(period)
    if entry is None:
        raise NoInputError(f"week of {period} has not been processed yet; run it first")
    rows = compare_period(entry["totals"], manual)
    print(f"Week of {period}: tool against {manual.name}")
    print("\n".join(format_rows(rows)))
    different = [r for r in rows if not r.matches]
    print(f"\n{len(rows) - len(different)} of {len(rows)} lines match.")
    if different:
        print("Explain each other line before retiring the manual report.")
    return EXIT_GATE if different else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
