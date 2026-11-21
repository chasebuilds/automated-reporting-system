from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from benchmark.generate import CONFIG_TOML, generate, truth_for, write_week

from autoreport.config import load_config
from autoreport.pipeline import run_period

HISTORY_WEEKS = 5


@pytest.fixture(scope="session")
def weeks():
    return generate(weeks=HISTORY_WEEKS + 1)


@pytest.fixture(scope="session")
def truth(weeks):
    return truth_for(weeks)


def make_workspace(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    config = folder / "report.toml"
    config.write_text(CONFIG_TOML, encoding="utf-8")
    return config


@pytest.fixture(scope="session")
def seeded(tmp_path_factory, weeks):
    """A workspace where the first five weeks have already run cleanly."""
    folder = tmp_path_factory.mktemp("seeded")
    cfg = load_config(make_workspace(folder))
    results = []
    for week in weeks[:HISTORY_WEEKS]:
        write_week(week, folder / "inbox")
        results.append(run_period(cfg, week.start))
    return folder, results


@pytest.fixture
def ws(tmp_path, seeded, weeks):
    """Fresh copy of the seeded state plus the next clean week. Returns (config, week)."""
    config = make_workspace(tmp_path)
    shutil.copytree(seeded[0] / "state", tmp_path / "state")
    write_week(weeks[HISTORY_WEEKS], tmp_path / "inbox", control=False)
    return config, weeks[HISTORY_WEEKS]
