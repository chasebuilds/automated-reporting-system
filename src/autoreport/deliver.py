"""Delivery as a dry run: build the email and save it as an .eml file. Nothing is sent.

There is no SMTP code here on purpose. To send for real, hand the saved file to a mail
tool you already trust; see docs/scheduling.md.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime

from autoreport import fmt
from autoreport.config import Config
from autoreport.findings import WARN, Finding
from autoreport.kpis import week_label

MIME = {
    ".xlsx": ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".html": ("text", "html"),
}


def summary_text(report: dict, cfg: Config) -> str:
    kpis = report["kpis"]
    totals, compared = kpis["totals"], kpis["comparisons"]
    sym = cfg.currency

    def line(label: str, value: str, metric: str) -> str:
        return (
            f"  {label:<24}{value:>14}   {fmt.delta(compared[metric]['wow_pct']):>8} vs last week"
        )

    out = [
        f"{cfg.company}: weekly report, {kpis['period']['label']}",
        "",
        line("Revenue", fmt.money(totals["revenue_cents"], sym), "revenue_cents"),
        line("Orders", fmt.count(totals["orders"]), "orders"),
        line("Average order value", fmt.money(totals["aov_cents"], sym), "aov_cents"),
        line("Refund rate", fmt.pct(totals["refund_rate"]), "refund_rate"),
        line("Ad spend", fmt.money(totals["spend_cents"], sym), "spend_cents"),
        line("Return on ad spend", fmt.times(totals["paid_roas"]), "paid_roas"),
        line("Support tickets", fmt.count(totals["tickets"]), "tickets"),
        line(
            "Avg first response",
            fmt.minutes(totals["avg_first_response_min"]),
            "avg_first_response_min",
        ),
        "",
    ]
    if kpis["alerts"]:
        out += ["Needs attention:"] + [f"  - {a['message']}" for a in kpis["alerts"]] + [""]
    warnings = [f for f in report["findings"] if f["level"] == WARN]
    if warnings:
        out.append(f"Data quality: {len(warnings)} warning(s), details in the workbook.")
        out += [f"  - {w['file']}: {w['message']}" for w in warnings]
    else:
        out.append("Data quality: all checks passed, no warnings.")
    out += ["", "Attached: the Excel workbook and the HTML dashboard (open it in any browser)."]
    return "\n".join(out) + "\n"


def build_eml(report: dict, cfg: Config, attachments: dict[str, bytes]) -> bytes:
    period = report["kpis"]["period"]
    digest = hashlib.sha256()
    for name, data in sorted(attachments.items()):
        digest.update(name.encode())
        digest.update(data)
    token = digest.hexdigest()

    message = EmailMessage()
    message["From"] = cfg.mail_from
    message["To"] = ", ".join(cfg.mail_to)
    message["Subject"] = f"{cfg.company} weekly report: {period['label']}"
    # Date, id and boundary all derive from the data so the same inputs give the same bytes.
    sent = datetime.combine(
        datetime.fromisoformat(period["end"]).date() + timedelta(days=1), time(8), UTC
    )
    message["Date"] = format_datetime(sent)
    message["Message-ID"] = f"<{token[:24]}@{cfg.mail_from.rpartition('@')[2]}>"
    message.set_content(summary_text(report, cfg))
    for name, data in sorted(attachments.items()):
        maintype, subtype = MIME[name[name.rindex(".") :]]
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    message.set_boundary(f"=_report_{token[24:48]}")
    return message.as_bytes(policy=SMTP)


def build_failure_eml(cfg: Config, period: date, failures: list[Finding]) -> bytes:
    """The notice saved when the gate refuses a week: no report, and the reasons."""
    end = period + timedelta(days=6)
    reasons = [f"  - {f.file}: {f.message}" for f in failures]
    body = "\n".join(
        [
            f"{cfg.company}: no weekly report for {week_label(period)}.",
            "",
            "The report was not produced because the input data failed these checks:",
            "",
            *reasons,
            "",
            "Nothing was published. Replace or correct the files named above in the inbox and",
            "run the report again. Earlier reports are unchanged.",
            "",
        ]
    )
    message = EmailMessage()
    message["From"] = cfg.mail_from
    message["To"] = ", ".join(cfg.mail_to)
    message["Subject"] = f"{cfg.company}: NO weekly report for {week_label(period)}"
    message["Date"] = format_datetime(datetime.combine(end + timedelta(days=1), time(8), UTC))
    token = hashlib.sha256(body.encode()).hexdigest()
    message["Message-ID"] = f"<{token[:24]}@{cfg.mail_from.rpartition('@')[2]}>"
    message.set_content(body)
    return message.as_bytes(policy=SMTP)
