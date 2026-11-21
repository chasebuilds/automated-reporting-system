"""Chat message payloads (Slack and Microsoft Teams) built from a week's KPI JSON.

This module only builds the JSON body. It never makes a network request: posting it is a
separate step, for example `curl -X POST -H "Content-Type: application/json" -d @msg.json
<incoming webhook URL>`, so a test run can never message a client's channel by accident.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from autoreport.findings import Finding
from autoreport.fmt import count, delta, minutes, money, pct, times

STYLES = ("slack", "teams")

# (label, totals key, number kind) in the order a reader scans them.
HEADLINE = (
    ("Revenue", "revenue_cents", "money"),
    ("Orders", "orders", "count"),
    ("Average order value", "aov_cents", "money"),
    ("Refund rate", "refund_rate", "pct"),
    ("Ad spend", "spend_cents", "money"),
    ("Paid ROAS", "paid_roas", "times"),
    ("Support tickets", "tickets", "count"),
    ("Avg first response", "avg_first_response_min", "minutes"),
)


def load_kpis(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    kpis = doc.get("kpis", doc)
    if not isinstance(kpis, dict) or "totals" not in kpis or "period" not in kpis:
        raise ValueError(f"{path} is not a KPI file written by autoreport run")
    return kpis


def headline_rows(kpis: dict[str, Any], currency: str = "$") -> list[tuple[str, str]]:
    """Label and display text for each headline KPI, with the week-over-week change."""
    totals = kpis["totals"]
    comparisons = kpis.get("comparisons", {})
    formatters: dict[str, Callable[[Any], str]] = {
        "money": lambda v: money(v, currency, decimals=False),
        "count": count,
        "pct": pct,
        "times": times,
        "minutes": minutes,
    }
    rows = []
    for label, key, kind in HEADLINE:
        text = formatters[kind](totals.get(key))
        wow = comparisons.get(key, {}).get("wow_pct")
        if wow is not None:
            text += f" ({delta(wow)} vs last week)"
        rows.append((label, text))
    return rows


def _title(kpis: dict[str, Any]) -> str:
    return f"{kpis.get('company', 'Weekly report')}: week of {kpis['period']['label']}"


def _alerts(kpis: dict[str, Any]) -> list[str]:
    return [a["message"] for a in kpis.get("alerts", [])]


def report_payload(
    kpis: dict[str, Any], style: str, link: str | None = None, currency: str = "$"
) -> dict[str, Any]:
    """Message announcing a published week: headline KPIs, alerts, optional report link."""
    rows = headline_rows(kpis, currency)
    alerts = _alerts(kpis)
    if style == "slack":
        blocks: list[dict[str, Any]] = [
            {"type": "header", "text": {"type": "plain_text", "text": _title(kpis)}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*{label}*\n{text}"} for label, text in rows
                ],
            },
        ]
        if alerts:
            lines = "\n".join(f"- {a}" for a in alerts)
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*Alerts*\n{lines}"}}
            )
        if link:
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": f"<{link}|Open the report>"}}
            )
        return {"text": _title(kpis), "blocks": blocks}
    if style == "teams":
        body: list[dict[str, Any]] = [
            {"type": "TextBlock", "text": _title(kpis), "weight": "Bolder", "size": "Medium"},
            {"type": "FactSet", "facts": [{"title": label, "value": text} for label, text in rows]},
        ]
        for alert in alerts:
            body.append({"type": "TextBlock", "text": alert, "color": "Attention", "wrap": True})
        actions = [{"type": "Action.OpenUrl", "title": "Open the report", "url": link}]
        return _teams_card(body, actions if link else [])
    raise ValueError(f"unknown style {style!r}; use one of {', '.join(STYLES)}")


def refused_payload(period_label: str, failures: list[Finding], style: str) -> dict[str, Any]:
    """Message saying there is no report this week, and why."""
    title = f"No report for the week of {period_label}"
    reasons = [f"{f.file}: {f.message}" for f in failures]
    if style == "slack":
        lines = "\n".join(f"- {r}" for r in reasons)
        return {
            "text": title,
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": title}},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{len(reasons)} data problem(s) must be fixed first:\n{lines}",
                    },
                },
            ],
        }
    if style == "teams":
        body: list[dict[str, Any]] = [
            {"type": "TextBlock", "text": title, "weight": "Bolder", "color": "Attention"}
        ]
        body += [{"type": "TextBlock", "text": r, "wrap": True} for r in reasons]
        return _teams_card(body, [])
    raise ValueError(f"unknown style {style!r}; use one of {', '.join(STYLES)}")


def _teams_card(body: list[dict[str, Any]], actions: list[dict[str, Any]]) -> dict[str, Any]:
    card: dict[str, Any] = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }
    if actions:
        card["actions"] = actions
    return {
        "type": "message",
        "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
        ],
    }
