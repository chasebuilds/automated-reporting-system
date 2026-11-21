"""One data-quality result. Failures stop the run; warnings are printed in the report."""

from __future__ import annotations

from dataclasses import asdict, dataclass

FAIL = "fail"
WARN = "warn"
INFO = "info"
LEVEL_ORDER = {FAIL: 0, WARN: 1, INFO: 2}


@dataclass(frozen=True)
class Finding:
    level: str
    check: str
    file: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    def line(self) -> str:
        return f"{self.level.upper():4} {self.check}: {self.file}: {self.message}"


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (LEVEL_ORDER[f.level], f.file, f.check, f.message))
