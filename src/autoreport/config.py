"""Load the TOML config into one typed object. Paths resolve relative to the config file."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    company: str = "Example Company"
    currency: str = "$"
    inbox: Path = Path("inbox")
    output: Path = Path("output")
    outbox: Path = Path("outbox")
    state: Path = Path("state")
    period: str = "latest"
    trailing_weeks: int = 4
    channels: tuple[str, ...] = ("Paid Search", "Paid Social", "Email", "Organic")
    paid_channels: tuple[str, ...] = ("Paid Search", "Paid Social", "Email")
    aliases: dict[str, str] = field(default_factory=dict)
    refund_rate_max: float = 0.06
    paid_roas_min: float = 3.0
    first_response_minutes_max: float = 120.0
    sla_minutes: int = 240
    row_swing_warn: float = 0.30
    row_swing_fail: float = 0.60
    row_swing_min_rows: int = 100
    date_gap_warn_days: int = 1
    date_gap_fail_days: int = 2
    outlier_multiple: float = 25.0
    control_tolerance_cents: int = 0
    require_control_totals: bool = False
    date_order: str = "mdy"
    archive_inputs: bool = True
    heartbeat_url: str = ""
    mail_from: str = "reports@example.com"
    mail_to: tuple[str, ...] = ("owner@example.com",)

    def canonical_channel(self, raw: str) -> str | None:
        """Map a channel label from an export to a configured name, or None if unknown."""
        key = " ".join(raw.split()).casefold()
        for name in self.channels:
            if name.casefold() == key:
                return name
        return self.aliases.get(key)


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name}: not valid TOML ({exc})") from exc

    base = path.resolve().parent
    company = raw.get("company", {})
    paths = raw.get("paths", {})
    period = raw.get("period", {})
    channels = raw.get("channels", {})
    kpi = raw.get("thresholds", {})
    quality = raw.get("quality", {})
    delivery = raw.get("delivery", {})
    source = raw.get("input", {})
    alerts = raw.get("alerts", {})
    d = Config()

    names = tuple(channels.get("names", d.channels))
    paid = tuple(channels.get("paid", [c for c in d.paid_channels if c in names]))
    if unknown := [c for c in paid if c not in names]:
        raise ConfigError(f"{path.name}: paid channels not listed in channels.names: {unknown}")
    aliases = {}
    for alias, target in channels.get("aliases", {}).items():
        if target not in names:
            raise ConfigError(f"{path.name}: alias '{alias}' points at unknown channel '{target}'")
        aliases[" ".join(alias.split()).casefold()] = target

    cfg = Config(
        company=company.get("name", d.company),
        currency=company.get("currency_symbol", d.currency),
        inbox=base / paths.get("inbox", "inbox"),
        output=base / paths.get("output", "output"),
        outbox=base / paths.get("outbox", "outbox"),
        state=base / paths.get("state", "state"),
        period=str(period.get("default", d.period)),
        trailing_weeks=int(period.get("trailing_weeks", d.trailing_weeks)),
        channels=names,
        paid_channels=paid,
        aliases=aliases,
        refund_rate_max=float(kpi.get("refund_rate_max", d.refund_rate_max)),
        paid_roas_min=float(kpi.get("paid_roas_min", d.paid_roas_min)),
        first_response_minutes_max=float(
            kpi.get("first_response_minutes_max", d.first_response_minutes_max)
        ),
        sla_minutes=int(kpi.get("sla_minutes", d.sla_minutes)),
        row_swing_warn=float(quality.get("row_swing_warn", d.row_swing_warn)),
        row_swing_fail=float(quality.get("row_swing_fail", d.row_swing_fail)),
        row_swing_min_rows=int(quality.get("row_swing_min_rows", d.row_swing_min_rows)),
        date_gap_warn_days=int(quality.get("date_gap_warn_days", d.date_gap_warn_days)),
        date_gap_fail_days=int(quality.get("date_gap_fail_days", d.date_gap_fail_days)),
        outlier_multiple=float(quality.get("outlier_multiple", d.outlier_multiple)),
        control_tolerance_cents=round(
            float(quality.get("control_tolerance", d.control_tolerance_cents / 100)) * 100
        ),
        require_control_totals=bool(
            quality.get("require_control_totals", d.require_control_totals)
        ),
        date_order=str(source.get("date_order", d.date_order)).lower(),
        archive_inputs=bool(source.get("archive", d.archive_inputs)),
        heartbeat_url=str(alerts.get("heartbeat_url", d.heartbeat_url)),
        mail_from=delivery.get("from", d.mail_from),
        mail_to=tuple(delivery.get("to", d.mail_to)),
    )
    if cfg.trailing_weeks < 1:
        raise ConfigError(f"{path.name}: period.trailing_weeks must be 1 or more")
    if not 0 < cfg.row_swing_warn <= cfg.row_swing_fail:
        raise ConfigError(f"{path.name}: need 0 < quality.row_swing_warn <= row_swing_fail")
    if not 1 <= cfg.date_gap_warn_days <= cfg.date_gap_fail_days:
        raise ConfigError(f"{path.name}: need 1 <= date_gap_warn_days <= date_gap_fail_days")
    if cfg.date_order not in ("mdy", "dmy"):
        raise ConfigError(f"{path.name}: input.date_order must be 'mdy' or 'dmy'")
    if cfg.heartbeat_url and not cfg.heartbeat_url.startswith(("https://", "http://")):
        raise ConfigError(f"{path.name}: alerts.heartbeat_url must be an http(s) URL")
    if cfg.control_tolerance_cents < 0:
        raise ConfigError(f"{path.name}: quality.control_tolerance cannot be negative")
    if cfg.outlier_multiple <= 1:
        raise ConfigError(f"{path.name}: quality.outlier_multiple must be above 1")
    return cfg
