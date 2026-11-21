"""Rebuild samples/ from the seeded generator.

    python -m benchmark.build_samples

Seven earlier weeks are run in a scratch folder so the sample week has history to compare
against. Only that history, the sample week's inbox and its outputs are kept in samples/.
"""

from __future__ import annotations

import random
import shutil
import sys
from dataclasses import replace

from autoreport.config import load_config
from autoreport.pipeline import run_period
from benchmark.faults import duplicate_orders
from benchmark.generate import CONFIG_TOML, SEED, generate, write_csv, write_week
from benchmark.run import ROOT, WORK, workspace

SAMPLE_WEEK = 7
SAMPLES = ROOT / "samples"


def main() -> int:
    weeks = generate()[: SAMPLE_WEEK + 1]
    scratch = WORK / "samples"
    if scratch.exists():
        shutil.rmtree(scratch)
    cfg = load_config(workspace(scratch))
    for week in weeks:
        write_week(week, scratch / "inbox")
        if not run_period(cfg, week.start).ok:
            print(f"sample history week {week.stamp} failed the gate", file=sys.stderr)
            return 1

    for name in ("inbox", "inbox_bad", "state", "output", "outbox"):
        if (SAMPLES / name).exists():
            shutil.rmtree(SAMPLES / name)
    SAMPLES.mkdir(exist_ok=True)
    (SAMPLES / "report.toml").write_text(CONFIG_TOML, encoding="utf-8", newline="\n")
    (SAMPLES / "state").mkdir()
    for name in ("ledger.json", "history.json"):
        shutil.copy(scratch / "state" / name, SAMPLES / "state" / name)

    sample = weeks[SAMPLE_WEEK]
    write_week(sample, SAMPLES / "inbox")
    write_week(sample, SAMPLES / "inbox_bad")
    duplicate_orders(SAMPLES / "inbox_bad", sample, weeks[SAMPLE_WEEK - 1], random.Random(SEED))

    sample_cfg = load_config(SAMPLES / "report.toml")
    result = run_period(sample_cfg, sample.start, echo=print)
    if not result.ok:
        return 1

    # A hand-made report for the same week, for `autoreport compare`. One figure is planted
    # wrong (two digits of ad spend swapped) so the comparison has a difference to show.
    totals = result.kpis["totals"]
    spend = f"{totals['spend_cents'] / 100:.2f}"
    swapped = spend[:2] + spend[3] + spend[2] + spend[4:]
    write_csv(
        SAMPLES / f"manual_report_{sample.stamp}.csv",
        ["metric", "value"],
        [
            ["revenue", f"{totals['revenue_cents'] / 100:.2f}"],
            ["orders", totals["orders"]],
            ["average_order_value", f"{totals['aov_cents'] / 100:.2f}"],
            ["refund_amount", f"{totals['refund_cents'] / 100:.2f}"],
            ["refund_rate", f"{totals['refund_rate'] * 100:.2f}%"],
            ["ad_spend", swapped],
            ["tickets", totals["tickets"]],
        ],
    )

    # The notice the refused week leaves behind, kept as an example. It is built in the
    # scratch folder so the sample outbox holds only the real report.
    refused = run_period(
        replace(sample_cfg, inbox=SAMPLES / "inbox_bad", outbox=scratch / "refused_outbox"),
        sample.start,
    )
    shutil.copy(refused.outputs["notice"], SAMPLES / f"no_report_example_{sample.stamp}.eml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
