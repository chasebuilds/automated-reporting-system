"""Run one reporting period end to end: ingest, validate, transform, KPIs, render, deliver."""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from autoreport import kpis as kpi_stage
from autoreport.config import Config
from autoreport.deliver import build_eml, build_failure_eml
from autoreport.findings import FAIL, WARN, Finding, sort_findings
from autoreport.gate import check_control, check_files, has_failures, run_gate
from autoreport.ingest import (
    CONTROL,
    KINDS,
    SCHEMAS,
    ControlTotals,
    Table,
    read_control,
    read_table,
    scan_inbox,
)
from autoreport.render_html import render_html
from autoreport.render_xlsx import render_xlsx
from autoreport.state import State, atomic_write, dump_json, run_lock


class NoInputError(ValueError):
    pass


@dataclass
class RunResult:
    period: date
    ok: bool
    findings: list[Finding]
    kpis: dict | None = None
    outputs: dict[str, Path] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.level == FAIL]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == WARN]


def _show(path: Path) -> str:
    """Path relative to the working folder when possible, so logs do not carry a home folder."""
    try:
        return Path(os.path.relpath(path)).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_period(cfg: Config, requested: str | None) -> date:
    choice = requested or cfg.period
    if choice != "latest":
        return date.fromisoformat(choice)
    periods = scan_inbox(cfg.inbox)
    if not periods:
        raise NoInputError(f"no export files found in {cfg.inbox}")
    return max(periods)


def run_period(
    cfg: Config,
    period: date,
    *,
    deliver: bool = True,
    check_only: bool = False,
    echo: Callable[[str], None] | None = None,
) -> RunResult:
    """Run one week. Raises RunLockedError if another run holds the state folder."""
    with run_lock(cfg.state):
        return _run(cfg, period, deliver=deliver, check_only=check_only, echo=echo)


def _run(
    cfg: Config,
    period: date,
    *,
    deliver: bool,
    check_only: bool,
    echo: Callable[[str], None] | None,
) -> RunResult:
    started = time.perf_counter()
    lines: list[str] = []
    stage_started = started
    stamp = period.isoformat()
    notice = cfg.outbox / f"no_report_{stamp}.eml"

    def log(stage: str, message: str) -> None:
        line = f"[{stage:9}] {message}"
        lines.append(line)
        if echo:
            echo(line)

    def stage_done(stage: str) -> None:
        nonlocal stage_started
        now = time.perf_counter()
        log(stage, f"done in {(now - stage_started) * 1000:.0f} ms")
        stage_started = now

    def finish(result: RunResult) -> RunResult:
        result.log = lines
        result.seconds = time.perf_counter() - started
        atomic_write(cfg.state / "logs" / f"{stamp}.log", ("\n".join(lines) + "\n").encode())
        return result

    state = State(cfg.state)
    log("start", f"{cfg.company}, week of {stamp}, inbox {_show(cfg.inbox)}")

    files = scan_inbox(cfg.inbox).get(period, {})
    findings = check_files(files, period)
    tables: dict[str, Table] = {}
    for kind in KINDS:
        paths = files.get(kind, [])
        if len(paths) != 1:
            continue
        table = tables[kind] = read_table(kind, paths[0], cfg.date_order)
        if table.error:
            log("ingest", f"{table.name}: {table.error}")
        else:
            schema = (
                f"missing {', '.join(table.missing_columns)}"
                if table.missing_columns
                else f"all {len(SCHEMAS[kind])} required columns present"
            )
            log("ingest", f"{table.name}: {len(table.rows):,} rows, {schema}")
    controls: list[ControlTotals] = [read_control(p) for p in files.get(CONTROL, [])]
    for control in controls:
        log("ingest", f"{control.name}: {len(control.expected)} control totals")
    stage_done("ingest")

    findings = sort_findings(
        findings
        + run_gate(tables, period, cfg, state)
        + check_control(tables, controls, period, cfg)
    )
    for finding in findings:
        log("validate", finding.line())
    failures = [f for f in findings if f.level == FAIL]
    warnings = [f for f in findings if f.level == WARN]
    log("validate", f"{len(failures)} failures, {len(warnings)} warnings")
    stage_done("validate")
    if has_failures(findings):
        log("stopped", "REPORT NOT WRITTEN. Fix the failures above and run again.")
        result = RunResult(period, False, findings)
        if deliver and not check_only:
            # Silence looks like breakage, so the people who expect the report get the reason.
            atomic_write(notice, build_failure_eml(cfg, period, failures))
            result.outputs["notice"] = notice
            log("deliver", f"wrote {_show(notice)}: a no-report notice, saved and not sent")
        return finish(result)
    if check_only:
        log("stopped", "check only: gate passed, nothing written")
        return finish(RunResult(period, True, findings))

    rows = kpi_stage.transform(tables, cfg)
    log("transform", ", ".join(f"{kind} {len(rows[kind]):,}" for kind in KINDS) + " rows typed")
    stage_done("transform")

    kpis = kpi_stage.compute(rows, period, cfg, state.prior_weeks(period, cfg.trailing_weeks))
    totals = kpis["totals"]
    log(
        "kpis",
        f"revenue {totals['revenue_cents'] / 100:,.2f}, orders {totals['orders']:,},"
        f" refund rate {totals['refund_rate']}, paid ROAS {totals['paid_roas']},"
        f" tickets {totals['tickets']:,}",
    )
    stage_done("kpis")

    entry = {"period": kpis["period"], "totals": totals, "row_counts": kpis["row_counts"]}
    report = {
        "kpis": kpis,
        "findings": [f.as_dict() for f in findings],
        "files": [
            {
                "file": tables[kind].name,
                "kind": kind,
                "rows": len(tables[kind].rows),
                "sha256": tables[kind].sha256,
            }
            for kind in KINDS
        ]
        + [
            {"file": c.name, "kind": CONTROL, "rows": len(c.expected), "sha256": c.sha256}
            for c in controls
        ],
        "trend": state.trend(period) + [entry],
    }
    out_dir = cfg.output / stamp
    payloads: dict[Path, bytes] = {
        out_dir / f"weekly_report_{stamp}.xlsx": render_xlsx(report, cfg),
        out_dir / f"dashboard_{stamp}.html": render_html(report, cfg).encode("utf-8"),
        out_dir / f"kpis_{stamp}.json": dump_json(
            {k: report[k] for k in ("kpis", "findings", "files")}
        ),
    }
    outputs = dict(zip(("workbook", "dashboard", "kpis"), payloads, strict=True))
    if deliver:
        eml = cfg.outbox / f"weekly_report_{stamp}.eml"
        attachments = {p.name: b for p, b in payloads.items() if p.suffix != ".json"}
        payloads[eml] = build_eml(report, cfg, attachments)
        outputs["email"] = eml
    # Everything is rendered in memory first and each file is swapped in whole, so a crash
    # leaves either the old file or the new one, never half of one.
    for path, data in payloads.items():
        atomic_write(path, data)
        stage = "deliver" if path.suffix == ".eml" else "render"
        log(stage, f"wrote {_show(path)} ({len(data):,} bytes)")
    if deliver:
        log("deliver", "dry run: message saved to the outbox, nothing was sent")
        notice.unlink(missing_ok=True)
    stage_done("render")

    sources = [tables[kind] for kind in KINDS] + controls
    if cfg.archive_inputs:
        # The ledger proves which file was used; the archive keeps the file itself, because
        # the inbox may be overwritten next week.
        archive = cfg.state / "archive" / stamp
        archive.mkdir(parents=True, exist_ok=True)
        for source in sources:
            kept = archive / f"{source.sha256[:12]}_{source.name}"
            if not kept.exists():
                shutil.copyfile(source.path, kept)
        log("state", f"archived {len(sources)} input files in {_show(archive)}")

    # State is saved last: if anything above fails, the week is simply not recorded.
    state.ledger[stamp] = {
        kind: {"file": t.name, "sha256": t.sha256, "rows": len(t.rows)}
        for kind, t in tables.items()
    }
    state.history[stamp] = entry
    state.save()
    log("state", f"recorded {len(tables)} files and the week's KPIs in {_show(cfg.state)}")
    return finish(RunResult(period, True, findings, kpis, outputs))
