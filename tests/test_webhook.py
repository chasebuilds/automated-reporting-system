import json
import socket
from pathlib import Path

import pytest

from autoreport.cli import main
from autoreport.findings import FAIL, Finding
from autoreport.webhook import headline_rows, load_kpis, refused_payload, report_payload

KPIS = (
    Path(__file__).resolve().parent.parent / "samples/output/2026-09-21/kpis_2026-09-21.json"
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("webhook code must not open a connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_headline_rows_use_the_report_numbers():
    rows = dict(headline_rows(load_kpis(KPIS)))
    assert rows["Revenue"] == "$63,611 (-0.9% vs last week)"
    assert rows["Orders"] == "1,238 (-0.8% vs last week)"
    assert rows["Refund rate"].startswith("7.0% ")
    assert rows["Paid ROAS"].startswith("5.78x ")


def test_slack_payload_has_kpis_alert_and_link():
    payload = report_payload(load_kpis(KPIS), "slack", link="https://example.com/r")
    assert payload["text"] == "Fernhollow Supply Co.: week of 21 Sep to 27 Sep 2026"
    blocks = payload["blocks"]
    assert blocks[0]["type"] == "header"
    assert len(blocks[1]["fields"]) == 8  # Slack allows at most 10 fields per section
    text = json.dumps(payload)
    assert "Refund rate 7.0% is above the 6.0% limit" in text
    assert "<https://example.com/r|Open the report>" in text


def test_teams_payload_is_an_adaptive_card():
    payload = report_payload(load_kpis(KPIS), "teams", link="https://example.com/r")
    card = payload["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"
    facts = card["body"][1]["facts"]
    assert facts[0] == {"title": "Revenue", "value": "$63,611 (-0.9% vs last week)"}
    assert card["actions"][0]["url"] == "https://example.com/r"
    assert "actions" not in report_payload(load_kpis(KPIS), "teams")["attachments"][0]["content"]


def test_refused_payload_lists_each_failure():
    failures = [
        Finding(FAIL, "duplicate", "orders_2026-09-21.csv", "40 order_id values appear twice"),
        Finding(FAIL, "control_total", "orders_2026-09-21.csv", "row count is off by 40"),
    ]
    slack = json.dumps(refused_payload("2026-09-21", failures, "slack"))
    assert "No report for the week of 2026-09-21" in slack
    assert "2 data problem(s)" in slack and "row count is off by 40" in slack
    teams = refused_payload("2026-09-21", failures, "teams")
    assert len(teams["attachments"][0]["content"]["body"]) == 3


def test_unknown_style_and_bad_file_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        report_payload(load_kpis(KPIS), "discord")
    with pytest.raises(ValueError):
        refused_payload("2026-09-21", [], "discord")
    bad = tmp_path / "x.json"
    bad.write_text('{"hello": 1}')
    with pytest.raises(ValueError):
        load_kpis(bad)
    assert main(["webhook", "--kpis", str(bad)]) == 2


def test_cli_prints_or_writes_the_payload(tmp_path, capsys):
    assert main(["webhook", "--kpis", str(KPIS), "--style", "teams"]) == 0
    assert json.loads(capsys.readouterr().out)["type"] == "message"
    out = tmp_path / "msg.json"
    assert main(["webhook", "--kpis", str(KPIS), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["blocks"][0]["type"] == "header"
