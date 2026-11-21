"""Score the pipeline against known truth and write BENCHMARK.md from the real run.

    python -m benchmark.run

Three questions: do the KPIs match the truth exactly, does the gate catch each planted fault
at the right level, and does it stay quiet on clean weeks. Every fault is run twice: with
only the four exports, and again with a control totals file from the source system.
"""

from __future__ import annotations

import platform
import random
import shutil
import sys
from pathlib import Path
from statistics import median

from autoreport.config import load_config
from autoreport.findings import FAIL, WARN
from autoreport.pipeline import RunResult, run_period
from benchmark.faults import FAULTS, Fault
from benchmark.generate import CONFIG_TOML, SEED, Week, generate, truth_for, write_week

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "benchmark" / "_work"
BASE_WEEK = 8  # the clean week each fault is planted in (ninth of twelve)


def workspace(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    config = folder / "report.toml"
    config.write_text(CONFIG_TOML, encoding="utf-8", newline="\n")
    return config


def compare(kpis: dict, truth: dict) -> tuple[int, list[str]]:
    """Count the values checked and list every one that differs from the truth."""
    checked, wrong = 0, []

    def check(name: str, got, want) -> None:
        nonlocal checked
        checked += 1
        if got != want or type(got) is not type(want):
            wrong.append(f"{name}: report {got!r}, truth {want!r}")

    for key, want in truth["totals"].items():
        check(f"totals.{key}", kpis["totals"][key], want)
    reported = {c["channel"]: c for c in kpis["channels"]}
    for channel, values in truth["channels"].items():
        for key, want in values.items():
            check(f"{channel}.{key}", reported[channel][key], want)
    for metric, values in truth["comparisons"].items():
        for key, want in values.items():
            check(f"{metric}.{key}", kpis["comparisons"][metric][key], want)
    return checked, wrong


def outcome(result: RunResult) -> str:
    if not result.ok:
        return "fail"
    return "warn" if result.warnings else "pass"


def run_fault(fault: Fault, weeks: list[Week], state_before: Path, control: bool) -> dict:
    folder = WORK / ("faults_control" if control else "faults") / fault.name
    config = workspace(folder)
    shutil.copytree(state_before, folder / "state")
    week = weeks[BASE_WEEK]
    write_week(week, folder / "inbox", control=control)
    fault.apply(folder / "inbox", week, weeks[BASE_WEEK - 1], random.Random(SEED))
    result = run_period(load_config(config), week.start)
    level = outcome(result)
    wanted = FAIL if level == "fail" else WARN
    checks = sorted({f.check for f in result.findings if f.level == wanted})
    report_written = any((folder / "output").rglob("*.xlsx"))
    notice_written = any((folder / "outbox").glob("no_report_*.eml"))
    if control:
        # With a control file the gate may rightly be stricter than the bare expectation:
        # a week with a day of orders missing no longer balances, so it stops.
        caught = level == "fail" or (level == fault.expected_level and report_written)
    else:
        caught = (
            level == fault.expected_level
            and any(c in checks for c in fault.expected_checks)
            and report_written == (fault.expected_level == "warn")
        )
    if level == "fail":
        caught = caught and notice_written and not report_written
    preferred = [c for c in fault.expected_checks if c in checks] or checks
    message = next(
        (f.message for f in result.findings if f.level == wanted and f.check in preferred), ""
    )
    return {
        "fault": fault,
        "level": level,
        "checks": checks,
        "caught": caught,
        "report_written": report_written,
        "message": message,
    }


def main() -> int:
    if WORK.exists():
        shutil.rmtree(WORK)
    weeks = generate()
    truth = truth_for(weeks)
    clean = WORK / "clean"
    config = workspace(clean)
    for week in weeks:
        write_week(week, clean / "inbox")
    cfg = load_config(config)

    rows, total_checked, total_wrong, alarms = [], 0, [], 0
    for index, week in enumerate(weeks):
        if index == BASE_WEEK:
            shutil.copytree(
                clean / "state",
                WORK / "state_before_base",
                ignore=shutil.ignore_patterns("archive", "logs"),
            )
        result = run_period(cfg, week.start)
        noisy = [f for f in result.findings if f.level in (FAIL, WARN)]
        alarms += len(noisy)
        checked, wrong = (
            compare(result.kpis, truth[week.stamp]) if result.kpis else (0, ["no report"])
        )
        total_checked += checked
        total_wrong += [f"{week.stamp} {w}" for w in wrong]
        rows.append((week, result, checked, wrong, noisy))

    last = weeks[-1]
    produced = sorted((clean / "output" / last.stamp).iterdir()) + sorted(
        (clean / "outbox").glob(f"*{last.stamp}*")
    )
    before = {p: p.read_bytes() for p in produced}
    run_period(cfg, last.start)
    stable = {p.name: p.read_bytes() == data for p, data in before.items()}

    state_before = WORK / "state_before_base"
    bare = [run_fault(f, weeks, state_before, control=False) for f in FAULTS]
    with_control = [run_fault(f, weeks, state_before, control=True) for f in FAULTS]
    caught = sum(1 for f in bare if f["caught"])
    caught_control = sum(1 for f in with_control if f["caught"])
    missed = [f for f in bare if not f["caught"]]
    missed_control = [f for f in with_control if not f["caught"]]
    times = [r[1].seconds * 1000 for r in rows]
    input_rows = [sum(r[1].kpis["row_counts"].values()) for r in rows if r[1].kpis]

    def money(cents: int) -> str:
        return f"${cents / 100:,.2f}"

    out = [
        "# Benchmark",
        "",
        "Written by `python -m benchmark.run` from a real run. Nothing here is typed by hand.",
        "",
        f"- Generator seed: `{SEED}`. 12 clean weeks of orders, refunds, ad spend and support"
        " tickets for an invented shop, with the true KPIs worked out separately in"
        " `benchmark/generate.py`.",
        f"- {len(FAULTS)} corrupted copies of one week, one planted fault each"
        " (`benchmark/faults.py`). Each is run twice: with the four exports only, and with a"
        " control totals file (row counts and amount totals as the source system states them).",
        f"- Run on Python {platform.python_version()}, {platform.system()} {platform.release()}.",
        "",
        "## Result",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| KPI values matching truth exactly | {total_checked - len(total_wrong):,} of"
        f" {total_checked:,} |",
        f"| Planted faults caught, exports only | {caught} of {len(bare)} |",
        f"| Planted faults caught, with a control totals file | {caught_control} of"
        f" {len(with_control)} |",
        f"| False alarms on the 12 clean weeks (control totals checked) | {alarms} |",
        f"| Median run time per week | {median(times):.0f} ms"
        f" (min {min(times):.0f}, max {max(times):.0f}) for about"
        f" {median(input_rows):,.0f} input rows |",
        f"| Outputs byte-identical on a second run | {sum(stable.values())} of {len(stable)}"
        " files |",
        "",
        "## KPIs against truth, week by week",
        "",
        "Each week, every total, every per-channel figure and every week-over-week and"
        " trailing-average figure is compared with the truth. A value counts only if it is"
        " equal, not close.",
        "",
        "| Week of | Revenue, report | Revenue, truth | Orders, report | Orders, truth |"
        " Refund rate, report | Refund rate, truth | Values equal | Gate alarms | Run time |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for week, result, checked, wrong, noisy in rows:
        got, want = result.kpis["totals"], truth[week.stamp]["totals"]
        out.append(
            f"| {week.stamp} | {money(got['revenue_cents'])} | {money(want['revenue_cents'])} |"
            f" {got['orders']:,} | {want['orders']:,} | {got['refund_rate']:.2%} |"
            f" {want['refund_rate']:.2%} | {checked - len(wrong)} of {checked} | {len(noisy)} |"
            f" {result.seconds * 1000:.0f} ms |"
        )
    if total_wrong:
        out += ["", "Mismatches:", ""] + [f"- {w}" for w in total_wrong]
    out += [
        "",
        "## Planted faults",
        "",
        "Exports only: a fault counts as caught when the gate answers at the expected level"
        " with the expected check. A fail must stop the run, write no report and leave a"
        " no-report notice in the outbox. A warn must still produce the report, with the"
        " warning on its Data Quality sheet.",
        "",
        "With control totals: the gate may be stricter than the expected level, because a week"
        " that does not balance with the source system is stopped. A fault counts as caught"
        " when the run stops, or when it warns at the expected level.",
        "",
        "| Fault | What was done to the week | Expected | Exports only | Caught |"
        " With control totals | Caught |",
        "|---|---|---|---|---|---|---|",
    ]

    def said(f: dict) -> str:
        return f["level"] + (f" ({', '.join(f['checks'])})" if f["checks"] else "")

    def mark(f: dict) -> str:
        return "yes" if f["caught"] else "**no**"

    for one, two in zip(bare, with_control, strict=True):
        fault: Fault = one["fault"]
        out.append(
            f"| `{fault.name}` | {fault.what} | {fault.expected_level} | {said(one)} |"
            f" {mark(one)} | {said(two)} | {mark(two)} |"
        )
    out += ["", "### What the gate said, exports only", ""]
    out += [f"- `{f['fault'].name}`: {f['message']}" for f in bare if f["message"]]
    out += ["", "### Missed", ""]
    for label, group in (("Exports only", missed), ("With control totals", missed_control)):
        if not group:
            out.append(f"- {label}: none.")
        for f in group:
            out.append(
                f"- {label}: `{f['fault'].name}` ({f['fault'].what.lower()}), expected"
                f" {f['fault'].expected_level}, gate said {f['level']}."
            )
    if [f["fault"].name for f in missed] == ["small_silent_loss"] and not missed_control:
        caught_as = next(f for f in with_control if f["fault"].name == "small_silent_loss")
        out += [
            "",
            "A loss this small sits inside normal week-to-week movement, so no rule that looks"
            " only at the export can flag it without also raising false alarms on clean weeks."
            " With a control totals file it is caught: "
            f"{caught_as['message']}. Without one it passes. See `LIMITATIONS.md`.",
        ]
    out += [
        "",
        "## Byte stability",
        "",
        "The last week was run twice and each output compared byte for byte.",
        "",
        "| File | Identical on rerun |",
        "|---|---|",
    ]
    out += [
        f"| `{name}` | {'yes' if same else '**no**'} |" for name, same in sorted(stable.items())
    ]
    out.append("")
    (ROOT / "BENCHMARK.md").write_text("\n".join(out), encoding="utf-8", newline="\n")
    print("\n".join(out))
    return 0 if not total_wrong and not alarms else 1


if __name__ == "__main__":
    sys.exit(main())
