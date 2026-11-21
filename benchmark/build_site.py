"""Assemble the live demo site from samples/.

    python -m benchmark.build_samples
    python -m benchmark.build_site --out _site

The page is the sample week's own dashboard, with a strip at the top linking the Excel
workbook, the KPI JSON, the raw input files and the refused-week notice. Everything in it
comes from the seeded synthetic generator; no real data goes into the site.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from html import escape
from pathlib import Path

from benchmark.run import ROOT

REPO_URL = "https://github.com/chasebuilds/automated-reporting-system"

STRIP_STYLE = (
    "<style>.demo-strip{font:14px/1.5 system-ui,sans-serif;padding:10px 16px;"
    "background:rgba(127,127,127,.14);border-bottom:1px solid rgba(127,127,127,.3)}"
    ".demo-strip a{color:inherit;font-weight:600;margin-right:14px;white-space:nowrap}"
    ".demo-strip b{margin-right:10px}</style>"
)


class SiteError(Exception):
    pass


def newest_week(samples: Path) -> Path:
    weeks = sorted(p for p in (samples / "output").iterdir() if p.is_dir())
    if not weeks:
        raise SiteError(f"no report found under {samples / 'output'}; run build_samples first")
    return weeks[-1]


def strip_html(links: list[tuple[str, str]]) -> str:
    anchors = "".join(f'<a href="{escape(href)}">{escape(text)}</a>' for text, href in links)
    return (
        f'{STRIP_STYLE}<div class="demo-strip" role="note"><b>Live demo, synthetic data.</b>'
        f"{anchors}</div>"
    )


def build_site(samples: Path, out: Path) -> Path:
    week_dir = newest_week(samples)
    week = week_dir.name
    dashboard = week_dir / f"dashboard_{week}.html"
    if not dashboard.exists():
        raise SiteError(f"{dashboard} is missing")

    if out.exists():
        shutil.rmtree(out)
    (out / "inputs").mkdir(parents=True)

    links = []
    for name, text in (
        (f"weekly_report_{week}.xlsx", "Download the Excel report"),
        (f"kpis_{week}.json", "KPI JSON"),
    ):
        shutil.copy(week_dir / name, out / name)
        links.append((text, name))
    for src in sorted((samples / "inbox").iterdir()):
        shutil.copy(src, out / "inputs" / src.name)
    links.append(("Raw input files", "inputs/"))
    notice = samples / f"no_report_example_{week}.eml"
    if notice.exists():
        shutil.copy(notice, out / notice.name)
        links.append(("Refused-week notice", notice.name))
    links.append(("Source code", REPO_URL))

    html = dashboard.read_text(encoding="utf-8")
    if "<body>" not in html:
        raise SiteError(f"{dashboard} has no <body> tag")
    html = html.replace("<body>", "<body>\n" + strip_html(links), 1)
    (out / "index.html").write_text(html, encoding="utf-8", newline="\n")
    (out / "inputs" / "index.html").write_text(_listing(out / "inputs"), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out / "index.html"


def _listing(folder: Path) -> str:
    items = "".join(
        f'<li><a href="{escape(p.name)}">{escape(p.name)}</a></li>'
        for p in sorted(folder.iterdir())
        if p.name != "index.html"
    )
    return (
        '<!doctype html><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1"><title>Input files</title>'
        '<body style="font:16px/1.6 system-ui,sans-serif;margin:24px">'
        "<h1>One week of raw exports (synthetic)</h1>"
        f'<ul>{items}</ul><p><a href="../">Back to the dashboard</a></p></body>'
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--samples", type=Path, default=ROOT / "samples")
    parser.add_argument("--out", type=Path, default=ROOT / "_site")
    args = parser.parse_args(argv)
    try:
        index = build_site(args.samples, args.out)
    except SiteError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {index}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
