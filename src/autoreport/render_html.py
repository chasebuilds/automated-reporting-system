"""The HTML dashboard: one self-contained file, inline CSS and SVG, no external requests."""

from __future__ import annotations

import math
from datetime import date
from html import escape

from autoreport import fmt
from autoreport.config import Config
from autoreport.findings import WARN
from autoreport.render_xlsx import TILES, delta_tone

CSS = """
:root{color-scheme:light;--ink:#1d2330;--muted:#5a6272;--faint:#8a90a0;--glass:rgba(255,255,255,.56);
--card:rgba(255,255,255,.62);--edge:rgba(255,255,255,.75);--rule:rgba(29,35,48,.12);
--series:#2a78d6;--series-soft:rgba(42,120,214,.14);--track:rgba(29,35,48,.07);
--good:#17754a;--bad:#b93a2c;--warn:#96610c;--good-bg:rgba(23,117,74,.12);--bad-bg:rgba(185,58,44,.12);
--warn-bg:rgba(183,121,31,.16);--flat-bg:rgba(29,35,48,.07);--solid:#1d2330;--on-solid:#fff;
--room:radial-gradient(60rem 36rem at 8% -6%,#ffd9b8 0,transparent 60%),
radial-gradient(48rem 34rem at 96% 4%,#f6b7a1 0,transparent 58%),
radial-gradient(54rem 40rem at 70% 104%,#c9d8f2 0,transparent 60%),
radial-gradient(40rem 30rem at 0 100%,#f3e3c2 0,transparent 60%),linear-gradient(160deg,#f6ead9,#efe2d2)}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--ink:#f1efea;--muted:#c2c0b6;
--faint:#8f8d85;--glass:rgba(28,26,25,.58);--card:rgba(44,41,39,.6);--edge:rgba(255,255,255,.13);
--rule:rgba(255,255,255,.13);--series:#3987e5;--series-soft:rgba(57,135,229,.2);
--track:rgba(255,255,255,.09);--good:#55c890;--bad:#f0857a;--warn:#e6b455;
--good-bg:rgba(85,200,144,.15);--bad-bg:rgba(240,133,122,.16);--warn-bg:rgba(230,180,85,.16);
--flat-bg:rgba(255,255,255,.09);--solid:#f1efea;--on-solid:#1d1b1a;
--room:radial-gradient(60rem 36rem at 8% -6%,#5a3a26 0,transparent 60%),
radial-gradient(48rem 34rem at 96% 4%,#5b2f2a 0,transparent 58%),
radial-gradient(54rem 40rem at 70% 104%,#22324f 0,transparent 60%),linear-gradient(160deg,#1b1817,#141211)}}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:5.5rem}
body{margin:0;min-height:100vh;color:var(--ink);background:var(--room) fixed;background-color:#efe2d2;
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
-webkit-font-smoothing:antialiased}
@media (prefers-color-scheme:dark){body{background-color:#141211}}
.num,td.n,th.n,.tile b{font-variant-numeric:tabular-nums}
.glass{background:var(--glass);border:1px solid var(--edge);border-radius:24px;
-webkit-backdrop-filter:blur(26px) saturate(150%);backdrop-filter:blur(26px) saturate(150%);
box-shadow:inset 0 1px 0 var(--edge),0 18px 44px -22px rgba(40,24,10,.45)}
.wrap{max-width:1120px;margin:0 auto;padding:16px 16px 56px}
.bar{position:sticky;top:12px;z-index:5;display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;
padding:10px 12px 10px 20px;border-radius:999px;margin-bottom:20px}
.brand{font-weight:700;letter-spacing:-.01em}.brand span{color:var(--muted);font-weight:500}
nav{display:flex;gap:4px;margin-left:auto;overflow-x:auto;max-width:100%}
nav a{color:var(--ink);text-decoration:none;font-size:14px;font-weight:600;padding:7px 14px;
border-radius:999px;white-space:nowrap}
nav a:hover,nav a:focus-visible{background:var(--solid);color:var(--on-solid);outline:none}
section{padding:24px;margin-bottom:20px}
h1{font-size:clamp(24px,4.6vw,36px);line-height:1.15;letter-spacing:-.025em;margin:2px 0 6px;
text-wrap:balance}
h2{font-size:20px;letter-spacing:-.015em;margin:0 0 4px}
h3{font-size:14px;font-weight:650;margin:0 0 2px}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--muted)}
.lede,.sub{color:var(--muted);margin:0 0 16px}.sub a{color:inherit}.sub{font-size:13px;margin:0 0 12px}
.pills{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px}
.pill{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:600;padding:6px 12px;
border-radius:999px}
.pill.good{background:var(--good-bg);color:var(--good)}.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.bad{background:var(--bad-bg);color:var(--bad)}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}
.tile,.card{background:var(--card);border:1px solid var(--edge);border-radius:18px;padding:16px;
min-width:0}
.tile .k{font-size:13px;color:var(--muted);font-weight:600;display:flex;justify-content:space-between;
gap:8px}
.tile b{display:block;font-size:clamp(22px,2.6vw,28px);line-height:1.2;letter-spacing:-.02em;
margin:4px 0 8px;font-weight:700}
.flag{font-size:11px;font-weight:700;color:var(--warn);background:var(--warn-bg);border-radius:999px;
padding:1px 8px;white-space:nowrap}
.chip{display:inline-block;font-size:12.5px;font-weight:650;padding:2px 9px;border-radius:999px}
.chip.good{background:var(--good-bg);color:var(--good)}.chip.bad{background:var(--bad-bg);color:var(--bad)}
.chip.flat{background:var(--flat-bg);color:var(--muted)}
.tile small{display:block;color:var(--muted);font-size:12.5px;margin-top:6px}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:12px}
svg{display:block;width:100%;height:auto;overflow:visible}
svg text{fill:var(--muted);font-size:13px;font-family:inherit}
svg .val{fill:var(--ink);font-weight:650}
.gridline{stroke:var(--rule);stroke-width:1}.line{fill:none;stroke:var(--series);stroke-width:2.5;
stroke-linejoin:round;stroke-linecap:round}.area{fill:var(--series-soft)}
.dot{fill:var(--series);stroke:var(--card);stroke-width:2}.col{fill:var(--series)}
.hit{fill:transparent;cursor:default}.hit:hover+.col,.hit:hover+.dot{filter:brightness(1.15)}
.bars{display:grid;gap:10px;margin-top:10px}
.brow{display:grid;grid-template-columns:minmax(84px,26%) 1fr auto;align-items:center;gap:10px;
font-size:13.5px}
.brow .t{position:relative;height:14px;background:var(--track);border-radius:4px}
.brow .f{position:absolute;inset:0 auto 0 0;background:var(--series);border-radius:0 4px 4px 0;
min-width:2px}
.brow .m{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--ink);border-radius:1px}
.brow .v{font-weight:650;min-width:4.5em;text-align:right}
.brow .l{color:var(--muted);overflow-wrap:anywhere}
.legend{font-size:12.5px;color:var(--muted);margin-top:10px;display:flex;align-items:center;gap:6px}
.legend i{display:inline-block;width:2px;height:14px;background:var(--ink);border-radius:1px}
.scroll{overflow-x:auto;border-radius:14px;border:1px solid var(--edge);background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:440px}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--rule);vertical-align:top}
th{font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);font-weight:700;
white-space:nowrap}
td.n,th.n{text-align:right;white-space:nowrap}tr:last-child td{border-bottom:0}
tr.total td{font-weight:700;border-top:2px solid var(--rule)}
code{font:12px ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted);overflow-wrap:anywhere}
.lvl{font-size:11.5px;font-weight:800;letter-spacing:.05em;padding:2px 8px;border-radius:6px}
.lvl.warn{background:var(--warn-bg);color:var(--warn)}.lvl.info{background:var(--flat-bg);color:var(--muted)}
.lvl.pass{background:var(--good-bg);color:var(--good)}
ul.alerts{margin:0 0 16px;padding:0;list-style:none;display:grid;gap:6px}
ul.alerts li{background:var(--warn-bg);color:var(--warn);font-weight:600;font-size:14px;
padding:9px 14px;border-radius:12px}
footer{color:var(--muted);font-size:12.5px;text-align:center;padding:4px 16px}
#tip{position:fixed;z-index:9;pointer-events:none;background:var(--solid);color:var(--on-solid);
font-size:12.5px;font-weight:600;padding:6px 10px;border-radius:9px;opacity:0;transition:opacity .12s;
max-width:240px;white-space:pre-line;transform:translate(-50%,-100%)}
@media (max-width:860px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
.grid2{grid-template-columns:1fr}section{padding:18px 14px;border-radius:20px}
.bar{border-radius:22px;padding:12px 12px 8px 16px}nav{margin-left:0}}
@media (max-width:560px){svg text{font-size:19px}}
@media (max-width:380px){.tile{padding:12px}.tile b{font-size:20px}}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}#tip{transition:none}}
@media print{body{background:#fff;color:#000}.bar{position:static}nav,#tip{display:none}
.glass,.tile,.card,.scroll{background:#fff;box-shadow:none;-webkit-backdrop-filter:none;
backdrop-filter:none;border-color:#ccc}section{break-inside:avoid}}
"""

JS = """
(function(){var t=document.getElementById('tip');if(!t)return;
function show(e){var el=e.target.closest('[data-tip]');if(!el){t.style.opacity=0;return}
t.textContent=el.getAttribute('data-tip');t.style.opacity=1;
var x=Math.min(Math.max(e.clientX,90),window.innerWidth-90);
t.style.left=x+'px';t.style.top=Math.max(e.clientY-12,40)+'px'}
document.addEventListener('pointermove',show);document.addEventListener('pointerdown',show);
document.addEventListener('pointerleave',function(){t.style.opacity=0})})();
"""


def _nice_step(span: float, target: int = 4) -> float:
    raw = span / target if span > 0 else 1
    magnitude: float = 10 ** math.floor(math.log10(raw))
    for multiple in (1, 2, 2.5, 5, 10):
        if raw <= multiple * magnitude:
            return multiple * magnitude
    return 10 * magnitude


def _axis(low: float, high: float, from_zero: bool) -> list[float]:
    if from_zero:
        low = 0
    if high <= low:
        high = low + 1
    step = _nice_step(high - low)
    start = math.floor(low / step) * step
    ticks = [start]
    while ticks[-1] < high - 1e-9:
        ticks.append(ticks[-1] + step)
    return ticks


def _compact(dollars: float, symbol: str) -> str:
    if abs(dollars) >= 1000:
        return f"{symbol}{dollars / 1000:g}k"
    return f"{symbol}{dollars:g}"


def _n(value: float) -> str:
    return f"{value:.1f}"


def line_chart(points: list[tuple[str, float, str]], symbol: str) -> str:
    """points: (x label, dollars, tooltip). Weekly revenue, last point labelled."""
    width, height, left, right, top, bottom = 640, 270, 58, 78, 18, 34
    ticks = _axis(min(p[1] for p in points), max(p[1] for p in points), from_zero=False)
    low, high = ticks[0], ticks[-1]
    plot_w, plot_h = width - left - right, height - top - bottom

    def x(i: int) -> float:
        return left + plot_w * i / (len(points) - 1)

    def y(v: float) -> float:
        return top + plot_h * (1 - (v - low) / (high - low))

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Revenue by week">']
    for tick in ticks:
        out.append(
            f'<line class="gridline" x1="{left}" x2="{width - right}" y1="{_n(y(tick))}"'
            f' y2="{_n(y(tick))}"/><text x="{left - 8}" y="{_n(y(tick) + 4.5)}"'
            f' text-anchor="end">{escape(_compact(tick, symbol))}</text>'
        )
    coords = [(x(i), y(p[1])) for i, p in enumerate(points)]
    path = " ".join(
        f"{'M' if i == 0 else 'L'}{_n(cx)} {_n(cy)}" for i, (cx, cy) in enumerate(coords)
    )
    base = top + plot_h
    out.append(
        f'<path class="area" d="{path} L{_n(coords[-1][0])} {base} L{_n(coords[0][0])} {base} Z"/>'
        f'<path class="line" d="{path}"/>'
    )
    every = max(1, math.ceil(len(points) / 6))
    for i, ((cx, cy), (label, _value, tip)) in enumerate(zip(coords, points, strict=True)):
        last = i == len(points) - 1
        if (len(points) - 1 - i) % every == 0:
            out.append(
                f'<text x="{_n(cx)}" y="{height - 10}" text-anchor="middle">{escape(label)}</text>'
            )
        out.append(
            f'<circle class="hit" cx="{_n(cx)}" cy="{_n(cy)}" r="16" data-tip="{escape(tip)}"/>'
            f'<circle class="dot" cx="{_n(cx)}" cy="{_n(cy)}" r="{5 if last else 4}"/>'
        )
    cx, cy = coords[-1]
    out.append(
        f'<text class="val" x="{_n(cx + 10)}" y="{_n(cy + 4.5)}">'
        f"{escape(_compact(round(points[-1][1] / 100) / 10 * 1000, symbol))}</text></svg>"
    )
    return "".join(out)


def column_chart(points: list[tuple[str, float, str]], symbol: str, label: str) -> str:
    """points: (x label, dollars, tooltip). Zero based, tallest bar labelled."""
    width, height, left, right, top, bottom = 640, 270, 58, 12, 26, 34
    ticks = _axis(0, max(p[1] for p in points), from_zero=True)
    high = ticks[-1]
    plot_w, plot_h = width - left - right, height - top - bottom
    slot = plot_w / len(points)
    bar = min(slot - 2, 44)
    base = top + plot_h
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">']
    for tick in ticks:
        ty = top + plot_h * (1 - tick / high)
        out.append(
            f'<line class="gridline" x1="{left}" x2="{width - right}" y1="{_n(ty)}" y2="{_n(ty)}"/>'
            f'<text x="{left - 8}" y="{_n(ty + 4.5)}" text-anchor="end">'
            f"{escape(_compact(tick, symbol))}</text>"
        )
    tallest = max(range(len(points)), key=lambda i: points[i][1])
    for i, (name, value, tip) in enumerate(points):
        bx = left + slot * i + (slot - bar) / 2
        h = plot_h * value / high
        by = base - h
        r = min(4, h)
        out.append(
            f'<rect class="hit" x="{_n(left + slot * i)}" y="{top}" width="{_n(slot)}"'
            f' height="{plot_h}" data-tip="{escape(tip)}"/>'
            f'<path class="col" d="M{_n(bx)} {base} V{_n(by + r)} Q{_n(bx)} {_n(by)} {_n(bx + r)}'
            f" {_n(by)} H{_n(bx + bar - r)} Q{_n(bx + bar)} {_n(by)} {_n(bx + bar)} {_n(by + r)}"
            f' V{base} Z"/>'
            f'<text x="{_n(bx + bar / 2)}" y="{height - 10}" text-anchor="middle">'
            f"{escape(name)}</text>"
        )
        if i == tallest:
            out.append(
                f'<text class="val" x="{_n(bx + bar / 2)}" y="{_n(by - 7)}" text-anchor="middle">'
                f"{escape(_compact(round(value / 100) / 10 * 1000, symbol))}</text>"
            )
    out.append("</svg>")
    return "".join(out)


def bar_rows(rows: list[tuple[str, float | None, str, str]], marker: float | None = None) -> str:
    """rows: (label, value, shown value, tooltip). Horizontal bars that reflow on a phone."""
    top = max([v for _, v, _, _ in rows if v is not None] + [marker or 0] + [1e-9]) * 1.04
    out = ['<div class="bars">']
    for label, value, shown, tip in rows:
        fill = (
            ""
            if value is None
            else f'<span class="f" style="width:{value / top * 100:.2f}%"></span>'
        )
        mark = (
            ""
            if marker is None
            else f'<span class="m" style="left:{marker / top * 100:.2f}%"></span>'
        )
        out.append(
            f'<div class="brow" data-tip="{escape(tip)}"><span class="l">{escape(label)}</span>'
            f'<span class="t">{fill}{mark}</span><span class="v num">{escape(shown)}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def _table(headers: list[tuple[str, bool]], rows: list[list[str]], total: list[str] | None) -> str:
    head = "".join(f"<th{' class=n' if num else ''}>{escape(h)}</th>" for h, num in headers)
    body = []
    for cells, cls in [(r, "") for r in rows] + ([(total, ' class="total"')] if total else []):
        tds = "".join(
            f"<td{' class=n' if num else ''}>{cell}</td>"
            for cell, (_, num) in zip(cells, headers, strict=True)
        )
        body.append(f"<tr{cls}>{tds}</tr>")
    return (
        f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def _tile_value(kind: str, value, sym: str) -> str:
    return {
        "money": lambda: fmt.money(value, sym),
        "money0": lambda: fmt.money(value, sym, decimals=False),
        "int": lambda: fmt.count(value),
        "pct": lambda: fmt.pct(value),
        "times": lambda: fmt.times(value),
        "minutes": lambda: fmt.minutes(value),
    }[kind]()


def render_html(report: dict, cfg: Config) -> str:
    kpis = report["kpis"]
    totals, compared, sym = kpis["totals"], kpis["comparisons"], cfg.currency
    e = escape
    flagged = {a["metric"] for a in kpis["alerts"]}
    warnings = [f for f in report["findings"] if f["level"] == WARN]

    tiles = []
    for metric, label, kind, rise_is_good in TILES:
        c = compared[metric]
        tone = delta_tone(c["wow_pct"], rise_is_good)
        if c["wow_pct"] is None:
            chip = '<span class="chip flat">No earlier week</span>'
        else:
            arrow = "▲" if c["wow_pct"] > 0 else "▼" if c["wow_pct"] < 0 else "●"
            chip = f'<span class="chip {tone}">{arrow} {e(fmt.delta(c["wow_pct"]))} vs last week</span>'
        trailing = (
            ""
            if c["vs_trailing_pct"] is None
            else f"<small>{e(fmt.delta(c['vs_trailing_pct']))} vs {c['trailing_weeks']}-week"
            " average</small>"
        )
        flag = '<span class="flag">Check</span>' if metric in flagged else ""
        tiles.append(
            f'<div class="tile"><div class="k"><span>{e(label)}</span>{flag}</div>'
            f"<b>{e(_tile_value(kind, totals[metric], sym))}</b>{chip}{trailing}</div>"
        )

    trend = report["trend"]
    if len(trend) > 1:
        points = []
        for week in trend:
            start = date.fromisoformat(week["period"]["start"])
            revenue = week["totals"]["revenue_cents"]
            points.append(
                (
                    f"{start.day} {start:%b}",
                    revenue / 100,
                    f"Week of {week['period']['label']}\n{fmt.money(revenue, sym)}",
                )
            )
        trend_svg = line_chart(points, sym)
        trend_sub = f"Last {len(trend)} weeks, by week start date"
    else:
        trend_svg = ""
        trend_sub = "This is the first week on record. The trend line appears from week two."

    daily_points = []
    for d in kpis["daily"]:
        day = date.fromisoformat(d["date"])
        daily_points.append(
            (
                f"{day:%a}",
                d["revenue_cents"] / 100,
                f"{day:%A} {day.day} {day:%b}\n{fmt.money(d['revenue_cents'], sym)}"
                f" from {d['orders']:,} orders",
            )
        )

    channel_bars = bar_rows(
        [
            (
                c["channel"],
                c["revenue_cents"],
                fmt.money(c["revenue_cents"], sym, decimals=False),
                f"{c['channel']}\n{fmt.money(c['revenue_cents'], sym)} from {c['orders']:,} orders"
                f"\n{fmt.pct(c['revenue_share'])} of revenue",
            )
            for c in kpis["channels"]
        ]
    )
    paid = [c for c in kpis["channels"] if c["spend_cents"]]
    roas_bars = bar_rows(
        [
            (
                c["channel"],
                c["roas"],
                fmt.times(c["roas"]),
                f"{c['channel']}\n{fmt.money(c['revenue_cents'], sym)} revenue on"
                f" {fmt.money(c['spend_cents'], sym)} spend",
            )
            for c in paid
        ],
        marker=cfg.paid_roas_min,
    )
    channel_table = _table(
        [
            ("Channel", False),
            ("Revenue", True),
            ("Orders", True),
            ("Avg order", True),
            ("Share", True),
            ("Ad spend", True),
            ("ROAS", True),
        ],
        [
            [
                e(c["channel"]),
                fmt.money(c["revenue_cents"], sym),
                fmt.count(c["orders"]),
                fmt.money(c["aov_cents"], sym),
                fmt.pct(c["revenue_share"]),
                fmt.money(c["spend_cents"], sym) if c["spend_cents"] else "none",
                fmt.times(c["roas"]) if c["spend_cents"] else "n/a",
            ]
            for c in kpis["channels"]
        ],
        [
            "Total",
            fmt.money(totals["revenue_cents"], sym),
            fmt.count(totals["orders"]),
            fmt.money(totals["aov_cents"], sym),
            "100.0%" if totals["revenue_cents"] else "n/a",
            fmt.money(totals["spend_cents"], sym),
            fmt.times(totals["paid_roas"]),
        ],
    )

    refund_table = _table(
        [("Reason", False), ("Refunds", True), ("Amount", True)],
        [
            [e(r["reason"]), fmt.count(r["count"]), fmt.money(r["amount_cents"], sym)]
            for r in kpis["refund_reasons"]
        ],
        ["Total", fmt.count(totals["refunds"]), fmt.money(totals["refund_cents"], sym)],
    )
    ticket_bars = bar_rows(
        [
            (
                c["category"],
                c["count"],
                fmt.count(c["count"]),
                f"{c['category']}\n{c['count']:,} tickets, {c['awaiting_reply']:,} awaiting reply"
                f"\nAvg first response {fmt.minutes(c['avg_first_response_min'])}",
            )
            for c in kpis["ticket_categories"]
        ]
    )

    if report["findings"]:
        quality_rows = [
            [
                f'<span class="lvl {e(f["level"])}">{e(f["level"].upper())}</span>',
                e(f["check"].replace("_", " ")),
                e(f["file"]),
                e(f["message"]),
            ]
            for f in report["findings"]
        ]
    else:
        quality_rows = [
            [
                '<span class="lvl pass">PASS</span>',
                "all checks",
                "all files",
                "Every check passed for every file.",
            ]
        ]
    quality_table = _table(
        [("Level", False), ("Check", False), ("File", False), ("Detail", False)], quality_rows, None
    )
    files_table = _table(
        [("File", False), ("Rows", True), ("SHA-256", False)],
        [
            [e(f["file"]), fmt.count(f["rows"]), f"<code>{e(f['sha256'][:16])}</code>"]
            for f in report["files"]
        ],
        None,
    )

    if warnings:
        quality_pill = (
            f'<span class="pill warn">▲ {len(warnings)} data warning'
            f"{'' if len(warnings) == 1 else 's'}, see Data quality</span>"
        )
    else:
        quality_pill = '<span class="pill good">✓ All data checks passed</span>'
    kpi_pill = (
        f'<span class="pill warn">▲ {len(kpis["alerts"])} KPI outside its threshold</span>'
        if kpis["alerts"]
        else '<span class="pill good">✓ KPIs inside thresholds</span>'
    )
    alerts = (
        '<ul class="alerts">'
        + "".join(f"<li>{e(a['message'])}</li>" for a in kpis["alerts"])
        + "</ul>"
        if kpis["alerts"]
        else ""
    )
    title = f"{cfg.company} weekly report, {kpis['period']['label']}"
    rows_read = sum(f["rows"] for f in report["files"])
    trend_card = (
        f'<div class="card"><h3>Revenue by week</h3><p class="sub">{e(trend_sub)}</p>'
        f"{trend_svg}</div>"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="bar glass">
<div class="brand">{e(cfg.company)} <span>Weekly report</span></div>
<nav aria-label="Sections"><a href="#overview">Overview</a><a href="#channels">Channels</a>
<a href="#support">Refunds and support</a><a href="#quality">Data quality</a></nav>
</header>
<main>
<section id="overview" class="glass">
<div class="eyebrow">Week of</div>
<h1>{e(kpis["period"]["label"])}</h1>
<p class="sub">Data through {e(kpis["period"]["end"])}, built from {len(report["files"])} files
 ({rows_read:,} rows). <a href="#quality">File names and hashes</a></p>
<div class="pills">{quality_pill}{kpi_pill}</div>
{alerts}
<div class="tiles">{"".join(tiles)}</div>
<div class="grid2">
{trend_card}
<div class="card"><h3>Revenue by day</h3><p class="sub">This week, Monday to Sunday</p>
{column_chart(daily_points, sym, "Revenue by day")}</div>
</div>
</section>
<section id="channels" class="glass">
<h2>Channels</h2>
<p class="lede">Where the orders came from, and what the paid channels returned.</p>
<div class="grid2">
<div class="card"><h3>Revenue by channel</h3>{channel_bars}</div>
<div class="card"><h3>Return on ad spend</h3>{roas_bars}
<div class="legend"><i></i> Floor set in the config: {e(fmt.times(cfg.paid_roas_min))}</div></div>
</div>
{channel_table}
</section>
<section id="support" class="glass">
<h2>Refunds and support</h2>
<p class="lede">{e(fmt.money(totals["refund_cents"], sym))} refunded across
 {totals["refunds"]:,} refunds ({e(fmt.pct(totals["refund_rate"]))} of revenue).
 {totals["tickets"]:,} tickets, median first response
 {e(fmt.minutes(totals["median_first_response_min"]))},
 {e(fmt.pct(totals["sla_met_rate"]))} answered within {cfg.sla_minutes} minutes.</p>
<div class="grid2">
<div><h3>Refunds by reason</h3><p class="sub">Largest amount first</p>{refund_table}</div>
<div class="card"><h3>Tickets by category</h3>{ticket_bars}</div>
</div>
</section>
<section id="quality" class="glass">
<h2>Data quality</h2>
<p class="lede">Every file is checked before any number is calculated. A failed check stops the
 run and no report is written, so this page only exists because the gate passed.</p>
{quality_table}
<h3 style="margin-top:20px">Files read</h3>
<p class="sub">{rows_read:,} rows from {len(report["files"])} files. The hash identifies the exact
 file each number came from.</p>
{files_table}
</section>
</main>
<footer>Built from the inbox by automated-reporting-system. The same input files always produce
 this same report.</footer>
</div>
<div id="tip" role="status"></div>
<script>{JS}</script>
</body>
</html>
"""
