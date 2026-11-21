from pathlib import Path

import pytest
from benchmark.build_site import SiteError, build_site, main

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_site_is_the_dashboard_with_download_links(tmp_path):
    index = build_site(SAMPLES, tmp_path / "site")
    html = index.read_text(encoding="utf-8")
    assert html.count("demo-strip") >= 2
    assert 'href="weekly_report_2026-09-21.xlsx"' in html
    assert "21 Sep to 27 Sep 2026" in html
    site = index.parent
    for name in (
        "weekly_report_2026-09-21.xlsx",
        "kpis_2026-09-21.json",
        "no_report_example_2026-09-21.eml",
        "inputs/orders_2026-09-21.csv",
        "inputs/index.html",
        ".nojekyll",
    ):
        assert (site / name).exists(), name
    assert (site / "weekly_report_2026-09-21.xlsx").read_bytes() == (
        SAMPLES / "output/2026-09-21/weekly_report_2026-09-21.xlsx"
    ).read_bytes()


def test_rebuild_replaces_old_site(tmp_path):
    out = tmp_path / "site"
    out.mkdir()
    (out / "stale.txt").write_text("old")
    build_site(SAMPLES, out)
    assert not (out / "stale.txt").exists()


def test_missing_report_is_an_error(tmp_path):
    (tmp_path / "output").mkdir()
    with pytest.raises(SiteError):
        build_site(tmp_path, tmp_path / "site")
    assert main(["--samples", str(tmp_path), "--out", str(tmp_path / "site")]) == 1
