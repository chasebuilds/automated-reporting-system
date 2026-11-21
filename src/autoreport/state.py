"""Run state: which files were processed (ledger) and each week's KPIs (history).

Both are keyed by period, so running a week again replaces its entry and nothing is counted
twice. Neither file holds a timestamp, which keeps reruns byte-identical.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path


class RunLockedError(RuntimeError):
    pass


def atomic_write(path: Path, data: bytes) -> None:
    """Write beside the target, then swap it in, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(data)
    os.replace(temp, path)


def write_json(path: Path, data: object) -> None:
    atomic_write(path, dump_json(data))


@contextmanager
def run_lock(directory: Path) -> Iterator[None]:
    """Hold state/run.lock for the length of a run so two runs cannot overlap."""
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "run.lock"
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RunLockedError(
            f"another run holds {lock} (process {lock.read_text('utf-8').strip() or 'unknown'})."
            " If no run is active, a crashed run left it behind: delete the file and run again."
        ) from None
    try:
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        yield
    finally:
        lock.unlink(missing_ok=True)


def dump_json(data: object) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


class State:
    def __init__(self, directory: Path):
        self.directory = directory
        self.ledger: dict[str, dict[str, dict]] = _read(directory / "ledger.json")
        self.history: dict[str, dict] = _read(directory / "history.json")

    def save(self) -> None:
        write_json(self.directory / "ledger.json", self.ledger)
        write_json(self.directory / "history.json", self.history)

    def prior_weeks(self, period: date, count: int) -> list[dict]:
        """History for the consecutive weeks just before `period`, oldest first.

        Stops at the first missing week: an average over a broken run of weeks would be
        labelled as a trailing average but would not be one.
        """
        weeks: list[dict] = []
        for back in range(1, count + 1):
            entry = self.history.get((period - timedelta(weeks=back)).isoformat())
            if entry is None:
                break
            weeks.append(entry)
        return weeks[::-1]

    def trend(self, period: date, limit: int = 12) -> list[dict]:
        """History entries up to but not including `period`, oldest first."""
        keys = sorted(k for k in self.history if k < period.isoformat())[-(limit - 1) :]
        return [self.history[k] for k in keys]

    def find_content(self, sha256: str, period: date, kind: str) -> tuple[str, str, str] | None:
        """Where this exact file content was processed before, if under another period or kind."""
        for other_period, kinds in sorted(self.ledger.items()):
            for other_kind, entry in sorted(kinds.items()):
                same_slot = (other_period, other_kind) == (period.isoformat(), kind)
                if entry["sha256"] == sha256 and not same_slot:
                    return other_period, other_kind, entry["file"]
        return None

    def previous_sha(self, period: date, kind: str) -> str | None:
        return self.ledger.get(period.isoformat(), {}).get(kind, {}).get("sha256")
