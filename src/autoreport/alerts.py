"""Optional heartbeat ping, off unless `alerts.heartbeat_url` is set in the config.

A scheduled job that stops running sends nothing, so nobody notices. A heartbeat service
(Healthchecks.io and similar) expects a ping after every good run and alerts when one does
not arrive. Only the URL from the config is requested and no report data is sent with it.
"""

from __future__ import annotations

from urllib.request import Request, urlopen

TIMEOUT_SECONDS = 10


def ping(url: str, ok: bool) -> str:
    """Ping the heartbeat URL, or URL/fail when the gate refused. Returns a log line.

    A ping that cannot be delivered never changes the run's result or exit code.
    """
    target = url if ok else url.rstrip("/") + "/fail"
    request = Request(target, headers={"User-Agent": "automated-reporting-system"})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - http(s) only
            return f"heartbeat {'success' if ok else 'failure'} ping sent (HTTP {response.status})"
    except Exception as exc:  # noqa: BLE001 - alerting must not break the run
        return f"heartbeat ping not delivered ({type(exc).__name__}: {exc})"
