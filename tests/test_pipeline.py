from __future__ import annotations

import email
import random
import shutil
from email import policy
from pathlib import Path

import openpyxl
import pytest
from benchmark.faults import FAULTS, duplicate_orders
from benchmark.generate import SEED, read_csv, write_csv
from benchmark.run import compare

from autoreport.cli import main
from autoreport.config import load_config
from autoreport.findings import FAIL, WARN
from autoreport.pipeline import run_period

from .conftest import HISTORY_WEEKS

ROOT = Path(__file__).resolve().parent.parent


def outputs(folder: Path) -> list[Path]:
    return sorted(p for name in ("output", "outbox") for p in (folder / name).rglob("*.*"))


def test_clean_weeks_match_truth_exactly_and_raise_no_alarm(seeded, weeks, truth):
    for week, result in zip(weeks, seeded[1], strict=False):
        assert result.ok
        assert [f for f in result.findings if f.level in (FAIL, WARN)] == []
        checked, wrong = compare(result.kpis, truth[week.stamp])
        assert checked == 73 and wrong == []


def test_week_with_history_has_comparisons(ws, truth):
    config, week = ws
    result = run_period(load_config(config), week.start)
    assert compare(result.kpis, truth[week.stamp])[1] == []
    revenue = result.kpis["comparisons"]["revenue_cents"]
    assert revenue["trailing_weeks"] == 4 and revenue["wow_pct"] is not None


@pytest.mark.parametrize("fault", FAULTS, ids=lambda f: f.name)
def test_planted_fault(fault, ws, weeks):
    config, week = ws
    folder = config.parent
    fault.apply(folder / "inbox", week, weeks[HISTORY_WEEKS - 1], random.Random(SEED))
    result = run_period(load_config(config), week.start)
    if fault.name == "small_silent_loss":
        # Known blind spot, documented in LIMITATIONS.md. Pinned so a change is noticed.
        assert result.ok and not result.warnings
        return
    wanted = FAIL if fault.expected_level == "fail" else WARN
    assert {f.check for f in result.findings if f.level == wanted} & set(fault.expected_checks)
    if fault.expected_level == "fail":
        assert not result.ok
        assert [p.name for p in outputs(folder)] == [f"no_report_{week.stamp}.eml"]
        state = load_config(config).state
        assert week.stamp not in (state / "history.json").read_text()
    else:
        assert result.ok and not result.failures
        book = openpyxl.load_workbook(result.outputs["workbook"])
        levels = [row[0] for row in book["Data Quality"].iter_rows(min_row=7, values_only=True)]
        assert "WARN" in levels


def test_cli_failure_exit_code_and_message(ws, weeks, capsys):
    config, week = ws
    duplicate_orders(config.parent / "inbox", week, weeks[0], random.Random(1))
    assert main(["run", "--config", str(config)]) == 1
    err = capsys.readouterr().err
    assert f"orders_{week.stamp}.csv" in err and "appear more than once" in err
    assert not (config.parent / "output").exists()


def test_cli_success_check_and_status(ws, capsys):
    config, week = ws
    assert main(["check", "--config", str(config)]) == 0
    assert outputs(config.parent) == []
    assert main(["run", "--config", str(config), "--period", week.stamp]) == 0
    assert len(outputs(config.parent)) == 4
    assert main(["status", "--config", str(config)]) == 0
    assert week.stamp in capsys.readouterr().out


def test_cli_usage_errors(tmp_path, ws):
    assert main(["run", "--config", str(tmp_path / "nope.toml")]) == 2
    assert main(["run", "--config", str(ws[0]), "--period", "last tuesday"]) == 2


def test_rerun_is_byte_identical_and_not_double_counted(ws):
    config, week = ws
    cfg = load_config(config)
    run_period(cfg, week.start)
    first = {p: p.read_bytes() for p in outputs(config.parent)}
    state = {p.name: p.read_bytes() for p in cfg.state.glob("*.json")}
    again = run_period(cfg, week.start)
    assert again.ok and not again.warnings
    assert {p: p.read_bytes() for p in outputs(config.parent)} == first
    assert {p.name: p.read_bytes() for p in cfg.state.glob("*.json")} == state


def test_changed_file_is_flagged_as_restated(ws):
    config, week = ws
    cfg = load_config(config)
    run_period(cfg, week.start)
    path = cfg.inbox / f"tickets_{week.stamp}.csv"
    header, rows = read_csv(path)
    write_csv(path, header, rows[:-1])
    result = run_period(cfg, week.start)
    assert result.ok and [f.check for f in result.warnings] == ["restated_file"]


def test_same_content_under_another_week_is_refused(ws, weeks, seeded):
    config, week = ws
    cfg = load_config(config)
    old = weeks[HISTORY_WEEKS - 1]
    source = seeded[0] / "inbox" / f"refunds_{old.stamp}.csv"
    shutil.copy(source, cfg.inbox / f"refunds_{week.stamp}.csv")
    result = run_period(cfg, week.start)
    assert "already_processed" in {f.check for f in result.failures}


def test_email_is_a_dry_run_file_with_attachments(ws):
    config, week = ws
    result = run_period(load_config(config), week.start)
    message = email.message_from_bytes(result.outputs["email"].read_bytes(), policy=policy.default)
    assert week.stamp[:4] in message["Subject"]
    names = sorted(part.get_filename() for part in message.iter_attachments())
    assert names == [f"dashboard_{week.stamp}.html", f"weekly_report_{week.stamp}.xlsx"]
    assert "Revenue" in message.get_body(("plain",)).get_content()
    attached = next(p for p in message.iter_attachments() if p.get_filename().endswith(".xlsx"))
    assert attached.get_content() == result.outputs["workbook"].read_bytes()


def test_no_mail_sending_code_in_package():
    source = "".join(p.read_text("utf-8") for p in (ROOT / "src").rglob("*.py"))
    assert "smtplib" not in source and "sendmail" not in source


def test_dashboard_is_self_contained(ws):
    config, week = ws
    html = run_period(load_config(config), week.start).outputs["dashboard"].read_text("utf-8")
    for needle in ("http://", "https://", "<link", "src=", "@import", "url("):
        assert needle not in html
    assert 'name="viewport"' in html and html.count("<svg") == 2


def test_workbook_layout(ws):
    config, week = ws
    result = run_period(load_config(config), week.start)
    book = openpyxl.load_workbook(result.outputs["workbook"])
    assert book.sheetnames == [
        "Summary",
        "Channels",
        "Daily",
        "Trend",
        "Refunds",
        "Support",
        "Data Quality",
        "Definitions",
    ]
    assert len(book["Summary"]._charts) == 4
    assert book["Channels"].freeze_panes == "A5"
    assert book["Channels"].print_title_rows == "$4:$4"
    assert book["Channels"]["B5"].number_format == '"$"#,##0.00'
    total = result.kpis["totals"]["revenue_cents"] / 100
    assert book["Channels"]["B9"].value == pytest.approx(total)


def test_no_email_flag(ws):
    config, _week = ws
    assert main(["run", "--config", str(config), "--no-email"]) == 0
    assert not (config.parent / "outbox").exists()
