"""The Excel workbook: KPI tiles and native charts on top, detail sheets behind."""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime

import xlsxwriter

from autoreport import fmt
from autoreport.config import Config
from autoreport.findings import WARN

INK, MUTED, RULE = "#1F2933", "#667085", "#D9DEE5"
BLUE, PALE = "#2A78D6", "#F4F6F9"
GOOD, BAD, AMBER = "#1A7F4B", "#C0392B", "#B7791F"
MONEY, MONEY0 = '"$"#,##0.00', '"$"#,##0'

# metric, label, value format, True when a rise is good news (None: neither)
TILES = (
    ("revenue_cents", "Revenue", "money0", True),
    ("orders", "Orders", "int", True),
    ("aov_cents", "Average order value", "money", True),
    ("refund_rate", "Refund rate", "pct", False),
    ("spend_cents", "Ad spend", "money0", None),
    ("paid_roas", "Return on ad spend", "times", True),
    ("tickets", "Support tickets", "int", False),
    ("avg_first_response_min", "Avg first response", "minutes", False),
)


def _dollars(cents: int | None) -> float | None:
    return None if cents is None else cents / 100


def _tile_value(kind: str, value):
    return _dollars(value) if kind.startswith("money") else value


def delta_tone(change: float | None, rise_is_good: bool | None) -> str:
    """good, bad or flat, for colouring a change. Shared with the HTML dashboard."""
    if change is None or change == 0 or rise_is_good is None:
        return "flat"
    return "good" if (change > 0) == rise_is_good else "bad"


class _Book:
    def __init__(self, report: dict, cfg: Config):
        self.report, self.cfg = report, cfg
        self.kpis = report["kpis"]
        self.buffer = io.BytesIO()
        self.wb = xlsxwriter.Workbook(self.buffer, {"in_memory": True})
        end = date.fromisoformat(self.kpis["period"]["end"])
        self.wb.set_properties(
            {
                "title": f"{cfg.company} weekly report, {self.kpis['period']['label']}",
                "author": cfg.company,
                # A fixed stamp from the data, not the clock, keeps reruns byte-identical.
                "created": datetime(end.year, end.month, end.day, 12),
            }
        )
        money = cfg.currency.join(('"', '"')) + "#,##0.00"
        money0 = cfg.currency.join(('"', '"')) + "#,##0"
        base = {"font_name": "Calibri", "font_size": 11, "font_color": INK}
        f = self.wb.add_format
        self.f = {
            "title": f({**base, "bold": True, "font_size": 20}),
            "subtitle": f({**base, "font_color": MUTED, "font_size": 11}),
            "h2": f({**base, "bold": True, "font_size": 13}),
            "note": f({**base, "font_color": MUTED, "italic": True, "text_wrap": True}),
            "head": f(
                {
                    **base,
                    "bold": True,
                    "bg_color": INK,
                    "font_color": "#FFFFFF",
                    "border": 1,
                    "border_color": INK,
                    "valign": "vcenter",
                    "text_wrap": True,
                }
            ),
            "text": f({**base, "border": 1, "border_color": RULE}),
            "wrap": f(
                {**base, "border": 1, "border_color": RULE, "text_wrap": True, "valign": "top"}
            ),
            "mono": f(
                {**base, "font_name": "Consolas", "font_size": 9, "border": 1, "border_color": RULE}
            ),
            "int": f({**base, "num_format": "#,##0", "border": 1, "border_color": RULE}),
            "money": f({**base, "num_format": money, "border": 1, "border_color": RULE}),
            "pct": f({**base, "num_format": "0.0%", "border": 1, "border_color": RULE}),
            "times": f({**base, "num_format": '0.00"x"', "border": 1, "border_color": RULE}),
            "minutes": f({**base, "num_format": "#,##0.0", "border": 1, "border_color": RULE}),
            "date": f(
                {
                    **base,
                    "num_format": "yyyy-mm-dd",
                    "border": 1,
                    "border_color": RULE,
                    "align": "left",
                }
            ),
            "total_text": f({**base, "bold": True, "top": 2, "bg_color": PALE}),
            "total_int": f(
                {**base, "bold": True, "top": 2, "bg_color": PALE, "num_format": "#,##0"}
            ),
            "total_money": f(
                {**base, "bold": True, "top": 2, "bg_color": PALE, "num_format": money}
            ),
            "total_pct": f(
                {**base, "bold": True, "top": 2, "bg_color": PALE, "num_format": "0.0%"}
            ),
            "total_times": f(
                {**base, "bold": True, "top": 2, "bg_color": PALE, "num_format": '0.00"x"'}
            ),
            "lvl_fail": f(
                {
                    **base,
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": BAD,
                    "border": 1,
                    "border_color": RULE,
                    "valign": "top",
                }
            ),
            "lvl_warn": f(
                {
                    **base,
                    "bold": True,
                    "bg_color": "#FCE9B8",
                    "border": 1,
                    "border_color": RULE,
                    "valign": "top",
                }
            ),
            "lvl_info": f(
                {**base, "bg_color": PALE, "border": 1, "border_color": RULE, "valign": "top"}
            ),
            "lvl_pass": f(
                {
                    **base,
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": GOOD,
                    "border": 1,
                    "border_color": RULE,
                    "valign": "top",
                }
            ),
        }
        tile = {**base, "bg_color": PALE, "left": 1, "right": 1, "border_color": RULE}
        self.tile = {
            "label": f({**tile, "font_color": MUTED, "font_size": 10, "top": 1, "indent": 1}),
            "money": f(
                {
                    **tile,
                    "bold": True,
                    "font_size": 20,
                    "num_format": money,
                    "indent": 1,
                    "align": "left",
                }
            ),
            "money0": f(
                {
                    **tile,
                    "bold": True,
                    "font_size": 20,
                    "num_format": money0,
                    "indent": 1,
                    "align": "left",
                }
            ),
            "int": f(
                {
                    **tile,
                    "bold": True,
                    "font_size": 20,
                    "num_format": "#,##0",
                    "indent": 1,
                    "align": "left",
                }
            ),
            "pct": f(
                {
                    **tile,
                    "bold": True,
                    "font_size": 20,
                    "num_format": "0.0%",
                    "indent": 1,
                    "align": "left",
                }
            ),
            "times": f(
                {
                    **tile,
                    "bold": True,
                    "font_size": 20,
                    "num_format": '0.00"x"',
                    "indent": 1,
                    "align": "left",
                }
            ),
            "minutes": f(
                {
                    **tile,
                    "bold": True,
                    "font_size": 20,
                    "num_format": '#,##0" min"',
                    "indent": 1,
                    "align": "left",
                }
            ),
            "text": f({**tile, "bold": True, "font_size": 20, "indent": 1}),
            "good": f({**tile, "font_color": GOOD, "font_size": 10, "indent": 1}),
            "bad": f({**tile, "font_color": BAD, "font_size": 10, "indent": 1}),
            "flat": f({**tile, "font_color": MUTED, "font_size": 10, "indent": 1}),
            "foot": f({**tile, "font_color": MUTED, "font_size": 10, "bottom": 1, "indent": 1}),
        }
        self.alert = f({**base, "font_color": AMBER, "bold": True})
        self.fine = f({**base, "font_color": GOOD, "bold": True})

    def sheet(self, name: str, widths: list[float], header_row: int | None = None):
        ws = self.wb.add_worksheet(name)
        for column, width in enumerate(widths):
            ws.set_column(column, column, width)
        ws.set_landscape()
        ws.set_paper(1)
        ws.fit_to_pages(1, 0)
        ws.set_margins(left=0.5, right=0.5, top=0.6, bottom=0.6)
        ws.set_footer(f"&L&8{self.cfg.company}&C&8{name}&R&8Page &P of &N")
        ws.hide_gridlines(2)
        if header_row is not None:
            ws.freeze_panes(header_row + 1, 0)
            ws.repeat_rows(header_row)
        return ws

    def table(self, ws, top: int, headers: list[str], rows: list[list], kinds: list[str]) -> int:
        """Write a header and rows; return the index of the row after the last one."""
        ws.set_row(top, 30)
        ws.write_row(top, 0, headers, self.f["head"])
        for r, row in enumerate(rows, start=top + 1):
            for c, (value, kind) in enumerate(zip(row, kinds, strict=True)):
                if value is None:
                    ws.write_blank(r, c, None, self.f[kind])
                elif kind == "date":
                    ws.write_datetime(r, c, date.fromisoformat(value), self.f[kind])
                else:
                    ws.write(r, c, value, self.f[kind])
        if rows:
            ws.autofilter(top, 0, top + len(rows), len(headers) - 1)
        return top + 1 + len(rows)

    def title(self, ws, text: str) -> None:
        ws.set_row(0, 28)
        ws.write(0, 0, text, self.f["title"])
        ws.write(1, 0, f"{self.cfg.company}, {self.kpis['period']['label']}", self.f["subtitle"])

    # -- sheets -----------------------------------------------------------------

    def channels(self) -> int:
        ws = self.sheet("Channels", [20, 15, 11, 13, 13, 14, 11, 10, 14], header_row=3)
        self.title(ws, "Channels")
        rows = [
            [
                c["channel"],
                _dollars(c["revenue_cents"]),
                c["orders"],
                _dollars(c["aov_cents"]),
                c["revenue_share"],
                _dollars(c["spend_cents"]) if c["spend_cents"] else None,
                c["clicks"] or None,
                c["roas"],
                _dollars(c["cpc_cents"]),
            ]
            for c in self.kpis["channels"]
        ]
        end = self.table(
            ws,
            3,
            [
                "Channel",
                "Revenue",
                "Orders",
                "Avg order value",
                "Share of revenue",
                "Ad spend",
                "Clicks",
                "ROAS",
                "Cost per click",
            ],
            rows,
            ["text", "money", "int", "money", "pct", "money", "int", "times", "money"],
        )
        t = self.kpis["totals"]
        ws.write(end, 0, "Total", self.f["total_text"])
        ws.write(end, 1, _dollars(t["revenue_cents"]), self.f["total_money"])
        ws.write(end, 2, t["orders"], self.f["total_int"])
        ws.write(end, 3, _dollars(t["aov_cents"]), self.f["total_money"])
        ws.write(end, 4, 1 if t["revenue_cents"] else None, self.f["total_pct"])
        ws.write(end, 5, _dollars(t["spend_cents"]), self.f["total_money"])
        ws.write(end, 6, t["clicks"], self.f["total_int"])
        ws.write(end, 7, t["paid_roas"], self.f["total_times"])
        ws.write(end, 8, None, self.f["total_text"])
        ws.write(
            end + 2,
            0,
            "ROAS is channel revenue divided by channel ad spend. The total ROAS counts paid"
            " channels only.",
            self.f["subtitle"],
        )
        return len(rows)

    def daily(self) -> None:
        ws = self.sheet("Daily", [14, 12, 15, 11, 14, 11], header_row=3)
        self.title(ws, "Daily")
        rows = [
            [
                d["date"],
                f"{date.fromisoformat(d['date']):%A}",
                _dollars(d["revenue_cents"]),
                d["orders"],
                _dollars(d["spend_cents"]),
                d["tickets"],
            ]
            for d in self.kpis["daily"]
        ]
        self.table(
            ws,
            3,
            ["Date", "Day", "Revenue", "Orders", "Ad spend", "Tickets"],
            rows,
            ["date", "text", "money", "int", "money", "int"],
        )

    def trend(self) -> int:
        ws = self.sheet("Trend", [14, 15, 10, 13, 12, 14, 10, 10, 14], header_row=3)
        self.title(ws, "Trend by week")
        rows = []
        for week in self.report["trend"]:
            t = week["totals"]
            rows.append(
                [
                    week["period"]["start"],
                    _dollars(t["revenue_cents"]),
                    t["orders"],
                    _dollars(t["aov_cents"]),
                    t["refund_rate"],
                    _dollars(t["spend_cents"]),
                    t["paid_roas"],
                    t["tickets"],
                    t["avg_first_response_min"],
                ]
            )
        self.table(
            ws,
            3,
            [
                "Week starting",
                "Revenue",
                "Orders",
                "Avg order value",
                "Refund rate",
                "Ad spend",
                "ROAS",
                "Tickets",
                "Avg first response (min)",
            ],
            rows,
            ["date", "money", "int", "money", "pct", "money", "times", "int", "minutes"],
        )
        return len(rows)

    def refunds(self) -> None:
        ws = self.sheet("Refunds", [28, 11, 15, 16], header_row=3)
        self.title(ws, "Refunds by reason")
        t = self.kpis["totals"]
        rows = [
            [
                r["reason"],
                r["count"],
                _dollars(r["amount_cents"]),
                r["amount_cents"] / t["refund_cents"] if t["refund_cents"] else None,
            ]
            for r in self.kpis["refund_reasons"]
        ]
        end = self.table(
            ws,
            3,
            ["Reason", "Refunds", "Amount", "Share of refunds"],
            rows,
            ["text", "int", "money", "pct"],
        )
        ws.write(end, 0, "Total", self.f["total_text"])
        ws.write(end, 1, t["refunds"], self.f["total_int"])
        ws.write(end, 2, _dollars(t["refund_cents"]), self.f["total_money"])
        ws.write(end, 3, 1 if t["refund_cents"] else None, self.f["total_pct"])
        ws.write(
            end + 2,
            0,
            f"Refund rate {fmt.pct(t['refund_rate'])}: refunds booked this week divided by this"
            " week's revenue.",
            self.f["subtitle"],
        )

    def support(self) -> None:
        ws = self.sheet("Support", [28, 11, 15, 24], header_row=3)
        self.title(ws, "Support tickets by category")
        rows = [
            [c["category"], c["count"], c["awaiting_reply"], c["avg_first_response_min"]]
            for c in self.kpis["ticket_categories"]
        ]
        end = self.table(
            ws,
            3,
            ["Category", "Tickets", "Awaiting reply", "Avg first response (min)"],
            rows,
            ["text", "int", "int", "minutes"],
        )
        t = self.kpis["totals"]
        ws.write(end, 0, "Total", self.f["total_text"])
        ws.write(end, 1, t["tickets"], self.f["total_int"])
        ws.write(end, 2, t["tickets"] - t["tickets_answered"], self.f["total_int"])
        ws.write(end, 3, t["avg_first_response_min"], self.f["total_int"])
        ws.write(
            end + 2,
            0,
            f"Median first response {fmt.minutes(t['median_first_response_min'])}."
            f" {fmt.pct(t['sla_met_rate'])} of tickets answered within"
            f" {self.cfg.sla_minutes} minutes.",
            self.f["subtitle"],
        )

    def quality(self) -> None:
        ws = self.sheet("Data Quality", [10, 22, 34, 90], header_row=5)
        self.title(ws, "Data Quality")
        findings = self.report["findings"]
        warnings = sum(1 for f in findings if f["level"] == WARN)
        verdict = (
            f"Gate passed with {warnings} warning(s). Read them before relying on the numbers."
            if warnings
            else "Gate passed. No warnings."
        )
        ws.write(3, 0, verdict, self.alert if warnings else self.fine)
        rows = [[f["level"].upper(), f["check"], f["file"], f["message"]] for f in findings]
        if not rows:
            rows = [["PASS", "all_checks", "all files", "Every check passed for every file."]]
        ws.set_row(5, 22)
        ws.write_row(5, 0, ["Level", "Check", "File", "Detail"], self.f["head"])
        levels = {"FAIL": "lvl_fail", "WARN": "lvl_warn", "INFO": "lvl_info", "PASS": "lvl_pass"}
        for r, row in enumerate(rows, start=6):
            ws.write(r, 0, row[0], self.f[levels[row[0]]])
            ws.write_row(r, 1, row[1:], self.f["wrap"])
        top = 6 + len(rows) + 2
        ws.write(top - 1, 0, "Files read for this report", self.f["h2"])
        ws.write_row(top, 0, ["Rows", "Kind", "File", "SHA-256 of the file"], self.f["head"])
        for r, entry in enumerate(self.report["files"], start=top + 1):
            ws.write(r, 0, entry["rows"], self.f["int"])
            ws.write(r, 1, entry["kind"], self.f["text"])
            ws.write(r, 2, entry["file"], self.f["text"])
            ws.write(r, 3, entry["sha256"], self.f["mono"])
        note = top + len(self.report["files"]) + 2
        ws.write(
            note,
            0,
            "Checks run on every file: required columns, unreadable values, duplicate ids,"
            " negative amounts, dates outside the week, days with no data, unknown channels,"
            " row-count swings and files already processed. A failed check stops the run and"
            " no report is written.",
            self.f["subtitle"],
        )

    def definitions(self) -> None:
        ws = self.sheet("Definitions", [24, 62, 34, 52], header_row=3)
        self.title(ws, "How each number is worked out")
        rows = [[name, how, source, edge] for name, how, source, edge in self.definition_rows()]
        ws.set_row(3, 22)
        ws.write_row(3, 0, ["KPI", "Definition", "Source columns", "Edge rules"], self.f["head"])
        for r, row in enumerate(rows, start=4):
            ws.write_row(r, 0, row, self.f["wrap"])

    def definition_rows(self) -> list[tuple[str, str, str, str]]:
        weeks, sla = self.cfg.trailing_weeks, self.cfg.sla_minutes
        paid = ", ".join(self.cfg.paid_channels)
        return [
            (
                "Revenue",
                "Sum of order amounts for orders dated in the week.",
                "orders.amount, orders.order_date",
                "Before refunds. Money is held in whole cents.",
            ),
            (
                "Orders",
                "Count of order rows in the week.",
                "orders.order_id",
                "A repeated order id stops the run; it is never counted twice.",
            ),
            (
                "Average order value",
                "Revenue divided by orders.",
                "orders.amount",
                "Rounded half up to the cent.",
            ),
            (
                "Refund rate",
                "Refund amounts booked in the week divided by the week's revenue.",
                "refunds.amount, refunds.refund_date, orders.amount",
                "By booking date: a refund is not traced back to the week of its order.",
            ),
            (
                "Ad spend",
                "Sum of spend across all channels and days in the week.",
                "ad_spend.spend",
                "A day with no spend row counts as zero and raises a warning.",
            ),
            (
                "Return on ad spend (ROAS)",
                "Channel revenue divided by channel ad spend. The total uses paid channels only.",
                "orders.amount, orders.channel, ad_spend.spend",
                f"Paid channels: {paid}. Channel labels are mapped with the config aliases.",
            ),
            (
                "Support tickets",
                "Count of tickets created in the week.",
                "tickets.created_at",
                "By created date, whatever the ticket's current status.",
            ),
            (
                "Avg first response",
                "Mean minutes to first reply, over tickets that have a reply.",
                "tickets.first_response_minutes",
                f"Unanswered tickets are left out of the mean but count against the {sla}-minute"
                " target.",
            ),
            (
                "vs last week",
                "Change from the week before, as a share of that week's value.",
                "History of earlier runs",
                "Blank when the week before is not on record.",
            ),
            (
                f"vs {weeks}-week average",
                f"Change from the mean of up to {weeks} consecutive weeks before this one.",
                "History of earlier runs",
                "Stops at the first missing week; never averages over a gap.",
            ),
        ]

    def summary(self, ws, channel_rows: int, trend_rows: int) -> None:
        kpis, totals, compared = self.kpis, self.kpis["totals"], self.kpis["comparisons"]
        ws.set_row(0, 30)
        ws.write(0, 0, f"{self.cfg.company}: weekly report", self.f["title"])
        files = self.report["files"]
        ws.write(
            1,
            0,
            f"Week of {kpis['period']['label']}. Data through {kpis['period']['end']}."
            f" Built from {len(files)} files, {sum(f['rows'] for f in files):,} rows:"
            " names and hashes are on the Data Quality sheet.",
            self.f["subtitle"],
        )
        for i, (metric, label, kind, rise_is_good) in enumerate(TILES):
            top, left = 3 + 5 * (i // 4), 3 * (i % 4)
            right = left + 2
            value = _tile_value(kind, totals[metric])
            c = compared[metric]
            ws.merge_range(top, left, top, right, label, self.tile["label"])
            ws.set_row(top + 1, 30)
            if value is None:
                ws.merge_range(top + 1, left, top + 1, right, "n/a", self.tile["text"])
            else:
                ws.merge_range(top + 1, left, top + 1, right, value, self.tile[kind])
            wow = (
                "No earlier week to compare"
                if c["wow_pct"] is None
                else (f"{fmt.delta(c['wow_pct'])} vs last week")
            )
            ws.merge_range(
                top + 2,
                left,
                top + 2,
                right,
                wow,
                self.tile[delta_tone(c["wow_pct"], rise_is_good)],
            )
            trailing = (
                ""
                if c["vs_trailing_pct"] is None
                else (f"{fmt.delta(c['vs_trailing_pct'])} vs {c['trailing_weeks']}-week average")
            )
            ws.merge_range(top + 3, left, top + 3, right, trailing, self.tile["foot"])

        row = 13
        ws.write(row, 0, "Needs attention", self.f["h2"])
        if kpis["alerts"]:
            for alert in kpis["alerts"]:
                row += 1
                ws.write(row, 0, alert["message"], self.alert)
        else:
            row += 1
            ws.write(row, 0, "All KPIs are inside their thresholds.", self.fine)
        warnings = sum(1 for f in self.report["findings"] if f["level"] == WARN)
        row += 1
        if warnings:
            ws.write(
                row,
                0,
                f"{warnings} data-quality warning(s): see the Data Quality sheet.",
                self.alert,
            )
        else:
            ws.write(row, 0, "Data quality: every check passed.", self.fine)

        chart_top = row + 2

        def chart(
            kind: str,
            title: str,
            sheet: str,
            first: int,
            count: int,
            value_col: int,
            number_format: str,
            cell: tuple[int, int],
        ) -> None:
            ch = self.wb.add_chart({"type": kind})
            ch.add_series(
                {
                    "categories": [sheet, first, 0, first + count - 1, 0],
                    "values": [sheet, first, value_col, first + count - 1, value_col],
                    "line": {"color": BLUE, "width": 2.25},
                    "fill": {"color": BLUE},
                    "marker": {
                        "type": "circle",
                        "size": 5,
                        "fill": {"color": BLUE},
                        "border": {"color": "#FFFFFF"},
                    },
                    "gap": 60,
                }
                if kind == "line"
                else {
                    "categories": [sheet, first, 0, first + count - 1, 0],
                    "values": [sheet, first, value_col, first + count - 1, value_col],
                    "fill": {"color": BLUE},
                    "border": {"none": True},
                    "gap": 60,
                }
            )
            ch.set_title(
                {
                    "name": title,
                    "name_font": {"size": 12, "bold": True, "color": INK},
                    "overlay": False,
                }
            )
            ch.set_legend({"none": True})
            axis_font = {"size": 9, "color": MUTED}
            value_axis = {
                "num_format": number_format,
                "num_font": axis_font,
                "line": {"none": True},
                "major_gridlines": {"visible": True, "line": {"color": RULE, "width": 0.5}},
            }
            category_axis = {"num_font": axis_font, "line": {"color": RULE}, "num_format": "d mmm"}
            if kind == "bar":
                category_axis["reverse"] = True
            ch.set_x_axis(value_axis if kind == "bar" else category_axis)
            ch.set_y_axis(category_axis if kind == "bar" else value_axis)
            ch.set_chartarea({"border": {"color": RULE}})
            ch.set_size({"width": 468, "height": 270})
            ws.insert_chart(cell[0], cell[1], ch, {"x_offset": 2, "y_offset": 2})

        if trend_rows > 1:
            chart("line", "Revenue by week", "Trend", 4, trend_rows, 1, MONEY0, (chart_top, 0))
        else:
            ws.write(
                chart_top,
                0,
                "The weekly trend chart appears from the second week on.",
                self.f["note"],
            )
        chart(
            "column", "Revenue by channel", "Channels", 4, channel_rows, 1, MONEY0, (chart_top, 6)
        )
        chart("column", "Revenue by day", "Daily", 4, 7, 2, MONEY0, (chart_top + 14, 0))
        chart(
            "bar",
            "Return on ad spend by channel",
            "Channels",
            4,
            channel_rows,
            7,
            '0.0"x"',
            (chart_top + 14, 6),
        )
        ws.set_h_pagebreaks([chart_top + 14])

    def build(self) -> bytes:
        # Summary is created first so it is the sheet the workbook opens on.
        summary = self.sheet("Summary", [11.5] * 12)
        channel_rows = self.channels()
        self.daily()
        trend_rows = self.trend()
        self.refunds()
        self.support()
        self.quality()
        self.definitions()
        self.summary(summary, channel_rows, trend_rows)
        summary.activate()
        self.wb.close()
        return _repack(self.buffer.getvalue())


def _repack(data: bytes) -> bytes:
    """Rewrite the workbook zip without compression and with fixed metadata.

    Compressed bytes differ between Python builds (zlib versus zlib-ng), which would make
    the same report hash differently on two machines. Stored entries do not.
    """
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(data)) as source,
        zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as target,
    ):
        for name in source.namelist():
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 0
            info.external_attr = 0
            target.writestr(info, source.read(name))
    return out.getvalue()


def render_xlsx(report: dict, cfg: Config) -> bytes:
    return _Book(report, cfg).build()
