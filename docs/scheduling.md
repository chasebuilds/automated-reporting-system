# Running it on a schedule

The command is the same everywhere:

```text
autoreport run --config report.toml
```

It reports the newest week in the inbox. Exit code 0 means the report was written, 1 means the gate refused it (the reason is on stderr and in `state/logs/<week>.log`), 2 means a bad command or config. A scheduler should treat anything but 0 as "tell a person".

Pick a time after the last export normally lands. The examples use Monday 07:00.

These are examples to copy. Nothing in this repo registers a scheduled job for you.

## Windows Task Scheduler

Save as `run_report.cmd` next to `report.toml`. Edit the two paths.

```bat
@echo off
cd /d C:\reports\weekly
C:\reports\weekly\.venv\Scripts\autoreport.exe run --config report.toml >> state\scheduler.log 2>&1
exit /b %ERRORLEVEL%
```

Register it (run once, in a normal Command Prompt):

```bat
schtasks /Create /TN "Weekly report" /TR "C:\reports\weekly\run_report.cmd" /SC WEEKLY /D MON /ST 07:00
```

Check the last result (0 is success):

```bat
schtasks /Query /TN "Weekly report" /V /FO LIST
```

Remove it:

```bat
schtasks /Delete /TN "Weekly report" /F
```

To stop a second copy starting while one is still running, open the task in Task Scheduler, Settings tab, and leave "If the task is already running" on "Do not start a new instance". The tool also holds its own lock file, so an overlapping run exits with code 2 instead of writing over the first.

Notes: the `cd /d` line matters, because scheduled tasks start in `C:\Windows\System32`. The task runs only while that user is logged on unless you tick "Run whether user is logged on or not" in the Task Scheduler window.

## cron (macOS, Linux)

Open the table with `crontab -e` and add one line:

```cron
0 7 * * 1 cd /srv/reports/weekly && .venv/bin/autoreport run --config report.toml >> state/scheduler.log 2>&1 || echo "Weekly report was refused, see state/logs" | mail -s "Weekly report failed" ops@example.com
```

The part after `||` runs only on a non-zero exit. Swap it for whatever alert you already use, or drop it and watch the log.

## GitHub Actions

For teams that keep the exports in a repository. Save as `.github/workflows/weekly-report.yml`.

```yaml
name: weekly-report
on:
  schedule:
    - cron: "0 7 * * 1" # Mondays 07:00 UTC
  workflow_dispatch:

concurrency: weekly-report # never two runs at once

jobs:
  report:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install automated-reporting-system/
      - name: Build the report (the job fails if the gate refuses the data)
        run: autoreport run --config report.toml
      - uses: actions/upload-artifact@v4
        if: success()
        with:
          name: weekly-report
          path: |
            output/
            outbox/
      - name: Keep the ledger and history for next week
        if: success()
        run: |
          git config user.name "report-bot"
          git config user.email "report-bot@users.noreply.github.com"
          git add state/ledger.json state/history.json
          git commit -m "Weekly report state" || echo "no change"
          git push
```

A refused run shows as a failed job, and GitHub emails the repository's watchers. The state files must be committed back (last step), or next week has no history to compare against.

Two things to know before relying on GitHub Actions for a client's report:

- Scheduled workflows can start late when GitHub is busy. Do not promise a time to the minute.
- In a public repository, GitHub switches scheduled workflows off after 60 days without repository activity. The state commit in the last step counts as activity, but a few refused weeks in a row would not. This is the main reason to set up the heartbeat below.

## Alert when the run does not happen

A failed run is loud: exit code 1 and a notice in the outbox. A run that never starts (PC off, task disabled, workflow paused) is silent. The standard fix is a heartbeat monitor: a service that expects a ping every week and alerts you when it is missing.

1. Create a check in a heartbeat service (Healthchecks.io is one; any that accepts a plain GET works). Set its period to 7 days and a grace time of a few hours.
2. Put the check's URL in the config:

   ```toml
   [alerts]
   heartbeat_url = "https://hc-ping.com/your-check-id"
   ```

3. After each good `autoreport run` the tool requests that URL. After a refused run it requests the same URL with `/fail` added. `check` runs and `--inbox` runs never ping.

The setting is empty by default, and then the tool makes no network request of any kind. The ping carries no report data. If the ping cannot be delivered, the run's result and exit code do not change.

## When the report is refused

The tool writes `outbox/no_report_<week>.eml`: a short message to the report's recipients saying there is no report this week and listing the reasons. Like the report email, it is saved, not sent. Send it with the same step you use for the report, so nobody is left wondering whether the job broke. A later good run of the same week removes the notice.

## Sending the email for real

By design this tool only writes `outbox/weekly_report_<week>.eml`. To send it, hand that file to a mail tool you already trust, as a separate step after a zero exit code. For example, with msmtp on Linux:

```text
msmtp -t < outbox/weekly_report_2026-09-21.eml
```

Keeping the send step outside the tool means a test run can never email a client by accident.

## Getting files into the inbox

The tool does not fetch exports. Common ways to fill `inbox/` before the scheduled time: a scheduled export from the shop or help desk to a synced folder, an email rule that saves attachments, or a person dropping the files in. If a file is late, the run fails with "no orders export for the week of ...", which is the behaviour you want.
