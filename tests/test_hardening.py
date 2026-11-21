"""Control totals, the no-report notice, the run lock, the heartbeat and the compare command."""

from __future__ import annotations

import email
import random
from datetime import date
from email import policy

import pytest
from benchmark.faults import FAULTS
from benchmark.generate import SEED, read_csv, write_control, write_csv

from autoreport import alerts
from autoreport.cli import main
from autoreport.config import ConfigError, load_config
from autoreport.ingest import parse_date, read_table
from autoreport.pipeline import run_period
from autoreport.state import RunLockedError, run_lock

from .conftest import HISTORY_WEEKS

SMALL_LOSS = next(f for f in FAULTS if f.name == "small_silent_loss")


def test_control_totals_catch_the_small_silent_loss(ws, weeks):
    config, week = ws
    cfg = load_config(config)
    write_control(week, cfg.inbox)
    SMALL_LOSS.apply(cfg.inbox, week, weeks[HISTORY_WEEKS - 1], random.Random(SEED))
    result = run_period(cfg, week.start)
    assert not result.ok
    assert {f.check for f in result.failures} == {"control_total"}
    assert any("source system says" in f.message for f in result.failures)


def test_matching_control_totals_pass_and_are_listed(ws):
    config, week = ws
    cfg = load_config(config)
    write_control(week, cfg.inbox)
    result = run_period(cfg, week.start)
    assert result.ok and not result.warnings
    assert [f.check for f in result.findings if f.level == "info"] == ["control_total"]
    assert (cfg.state / "archive" / week.stamp).is_dir()
    assert len(list((cfg.state / "archive" / week.stamp).iterdir())) == 5


def test_control_tolerance_and_bad_control_lines(ws):
    config, week = ws
    cfg = load_config(config)
    write_control(week, cfg.inbox)
    path = cfg.inbox / f"control_totals_{week.stamp}.csv"
    header, rows = read_csv(path)
    rows[1][2] = f"{float(rows[1][2]) + 0.03:.2f}"
    write_csv(path, header, rows)
    assert not run_period(cfg, week.start).ok
    config.write_text(
        config.read_text().replace("control_tolerance = 0.00", "control_tolerance = 0.05")
    )
    assert run_period(load_config(config), week.start).ok
    write_csv(path, header, rows + [["orders", "weight", "3"]])
    result = run_period(load_config(config), week.start)
    assert "not a known total" in result.failures[0].message


def test_required_control_file_missing_fails(ws):
    config, week = ws
    text = config.read_text()
    config.write_text(
        text.replace("require_control_totals = false", "require_control_totals = true")
    )
    result = run_period(load_config(config), week.start)
    assert [f.file for f in result.failures] == [f"control_totals_{week.stamp}.csv"]


def test_failure_notice_names_the_problem_and_is_cleared_by_a_good_run(ws):
    config, week = ws
    cfg = load_config(config)
    refunds = cfg.inbox / f"refunds_{week.stamp}.csv"
    kept = refunds.read_bytes()
    refunds.unlink()
    result = run_period(cfg, week.start)
    notice = cfg.outbox / f"no_report_{week.stamp}.eml"
    assert result.outputs == {"notice": notice}
    message = email.message_from_bytes(notice.read_bytes(), policy=policy.default)
    assert message["Subject"].startswith(f"{cfg.company}: NO weekly report")
    assert f"refunds_{week.stamp}.csv" in message.get_content()
    assert list(message.iter_attachments()) == []
    assert notice.read_bytes() == (run_period(cfg, week.start), notice.read_bytes())[1]

    refunds.write_bytes(kept)
    assert run_period(cfg, week.start).ok
    assert not notice.exists()


def test_check_and_no_email_write_no_notice(ws):
    config, week = ws
    cfg = load_config(config)
    (cfg.inbox / f"tickets_{week.stamp}.csv").unlink()
    assert main(["check", "--config", str(config)]) == 1
    assert main(["run", "--config", str(config), "--no-email"]) == 1
    assert not cfg.outbox.exists() and not cfg.output.exists()


def test_run_lock_blocks_a_second_run(ws, capsys):
    config, week = ws
    cfg = load_config(config)
    with run_lock(cfg.state):
        with pytest.raises(RunLockedError):
            run_period(cfg, week.start)
        assert main(["run", "--config", str(config)]) == 2
        assert "another run holds" in capsys.readouterr().err
    assert not (cfg.state / "run.lock").exists()
    assert run_period(cfg, week.start).ok


def test_no_temp_files_left_behind(ws):
    config, week = ws
    run_period(load_config(config), week.start)
    assert list(config.parent.rglob("*.tmp")) == []


def test_heartbeat_is_off_by_default_and_pings_when_set(ws, monkeypatch, capsys):
    config, week = ws
    called = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        called.append(request.full_url)
        return Response()

    monkeypatch.setattr(alerts, "urlopen", fake_urlopen)
    assert main(["run", "--config", str(config)]) == 0
    assert called == []

    text = config.read_text().replace('heartbeat_url = ""', 'heartbeat_url = "https://hb.test/abc"')
    config.write_text(text)
    assert main(["run", "--config", str(config)]) == 0
    assert main(["check", "--config", str(config)]) == 0
    (load_config(config).inbox / f"orders_{week.stamp}.csv").unlink()
    assert main(["run", "--config", str(config)]) == 1
    assert called == ["https://hb.test/abc", "https://hb.test/abc/fail"]
    assert "heartbeat failure ping sent" in capsys.readouterr().out


def test_heartbeat_outage_does_not_change_the_result(monkeypatch):
    def refuse(request, timeout):
        raise OSError("network is down")

    monkeypatch.setattr(alerts, "urlopen", refuse)
    assert "not delivered" in alerts.ping("https://hb.test/abc", ok=True)


def test_compare_command(ws, tmp_path, capsys):
    config, week = ws
    manual = tmp_path / "manual.csv"
    assert main(["compare", "--config", str(config), "--period", week.stamp,
                 "--manual", str(manual)]) == 2  # fmt: skip
    result = run_period(load_config(config), week.start)
    totals = result.kpis["totals"]
    manual.write_text(
        "Metric,Value\n"
        f'revenue,"${totals["revenue_cents"] / 100:,.2f}"\n'
        f"orders,{totals['orders']}\n"
        f"refund rate,{totals['refund_rate'] * 100:.2f}%\n"
        f"paid_roas,{totals['paid_roas']}x\n",
        encoding="utf-8",
    )
    args = ["compare", "--config", str(config), "--period", week.stamp, "--manual", str(manual)]
    assert main(args) == 0
    assert "4 of 4 lines match" in capsys.readouterr().out
    with manual.open("a", encoding="utf-8") as handle:
        handle.write(f"tickets,{totals['tickets'] + 2}\nheadcount,12\n")
    assert main(args) == 1
    out = capsys.readouterr().out
    assert "DIFFERENT" in out and "not a metric this tool reports" in out


def test_slash_dates_follow_the_configured_order(tmp_path):
    assert parse_date("03/04/2026") == date(2026, 3, 4)
    assert parse_date("03/04/2026", "dmy") == date(2026, 4, 3)
    with pytest.raises(ValueError):
        parse_date("21/09/2026")
    path = tmp_path / "orders_2026-09-21.csv"
    path.write_text(
        "order_id,order_date,channel,items,amount\nA1,21/09/2026,Email,1,10.00\n", encoding="utf-8"
    )
    assert read_table("orders", path).bad_values == {"order_date": [(2, "21/09/2026")]}
    assert read_table("orders", path, "dmy").rows[0]["order_date"] == date(2026, 9, 21)


def test_new_config_keys_are_validated(tmp_path):
    for body in (
        '[input]\ndate_order = "ymd"\n',
        '[alerts]\nheartbeat_url = "ftp://example.test/x"\n',
        "[quality]\ncontrol_tolerance = -1\n",
    ):
        bad = tmp_path / "bad.toml"
        bad.write_text(body)
        with pytest.raises(ConfigError):
            load_config(bad)


def test_summary_states_data_through_and_definitions_exist(ws):
    import openpyxl

    config, week = ws
    result = run_period(load_config(config), week.start)
    book = openpyxl.load_workbook(result.outputs["workbook"])
    assert f"Data through {result.kpis['period']['end']}" in book["Summary"]["A2"].value
    assert book["Definitions"].max_row >= 13
    html = result.outputs["dashboard"].read_text("utf-8")
    assert f"Data through {result.kpis['period']['end']}" in html
