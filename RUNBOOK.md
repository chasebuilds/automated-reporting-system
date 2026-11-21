# Runbook

How to run, check and repair the weekly report without the person who built it.

## What it is

One command reads the week's exports from `inbox/`, checks them, and writes the report to `output/<week>/` and an email file to `outbox/`. Settings are in `report.toml`. Everything it remembers is in `state/`.

## Every week

1. Put the week's files in `inbox/`, named by the Monday the week starts:
   `orders_2026-09-21.csv`, `refunds_2026-09-21.csv`, `ad_spend_2026-09-21.xlsx`, `tickets_2026-09-21.csv`, and, if the source system provides one, `control_totals_2026-09-21.csv`.
2. Run `autoreport run --config report.toml` (or let the scheduler do it; see `docs/scheduling.md`).
3. Exit code 0: open `output/<week>/`. Read the Data Quality sheet if the Summary says there are warnings.
4. Exit code 1: no report was written. The reason is on the screen, in `state/logs/<week>.log`, and in `outbox/no_report_<week>.eml`. Fix the file it names and run again.

## Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | Report written (possibly with warnings) | Nothing, or read the warnings |
| 1 | The gate refused the data. For `compare`: at least one line differs | Fix the named file and rerun |
| 2 | Bad command or config, no files to run, or another run is in progress | Read the one-line error |

## Input contract

| File | Required columns | Notes |
|---|---|---|
| orders | `order_id`, `order_date`, `channel`, `items`, `amount` | One row per order. Ids are read as text and must be unique |
| refunds | `refund_id`, `order_id`, `refund_date`, `amount`, `reason` | One row per refund, dated when it was booked |
| ad_spend | `date`, `channel`, `spend`, `clicks` | One row per channel per day |
| tickets | `ticket_id`, `created_at`, `category`, `first_response_minutes` | Leave the minutes blank for a ticket with no reply yet |
| control_totals (optional) | `file`, `metric`, `value` | `file` is one of the four above; `metric` is `rows` or `amount` |

Rules for all files: CSV (UTF-8) or XLSX (first sheet, header in row 1). Header case, spaces and hyphens do not matter. Dates are `YYYY-MM-DD`, with or without a time; slash dates are read in the one order set by `input.date_order` in the config. Amounts may carry `$` and thousands commas. Every row must be dated inside the week.

## When the gate refuses a week

| Check in the message | Usual cause | Fix |
|---|---|---|
| `missing_file` | Export not delivered, or named differently | Add the file, or rename it to `<kind>_<week start>.csv` |
| `duplicate_file` | Browser saved a second copy, `name (1).csv` | Delete the extra copy |
| `unreadable_file` | Download cut off, or the file is open in Excel | Export again; close Excel |
| `missing_column` | The source system renamed or dropped a column | Restore the column name in the export. If the change is permanent, this is a change request |
| `bad_value` | Text in a number or date column (`N/A`, a blank, a day-first date) | Correct the cells at the rows named, in the source system if possible |
| `duplicate_id` | Rows pasted twice, or two exports joined | Remove the repeated rows |
| `negative_value` | Refunds mixed into the orders export, or a sign error | Move or correct the rows |
| `date_out_of_period` | The wrong week's file | Replace it with the right week |
| `date_gap` (2 or more days) | Export filtered to part of the week | Export the full week |
| `row_count_swing` (60% or more) | Cut-off or doubled export | Export again. If the swing is real (a sale, an outage), raise `quality.row_swing_fail` for that run and note why |
| `control_total` | The files do not add up to what the source system reports | Export again. If the control figure is the wrong one, correct the control file |
| `already_processed` | An old file renamed as this week's | Replace it with the right week |
| `empty_file` (orders) | Export ran with a filter that matched nothing | Export again |

Warnings (`date_gap` for a single day, `row_count_swing` under 60%, `unknown_channel`, `outlier_value`, `restated_file`, `empty_file` for other kinds) do not stop the report. They are printed on its Data Quality sheet. An `unknown_channel` warning usually means a new label needs adding under `[channels.aliases]` in the config.

Never edit a number in the workbook to make a report look right. Fix the input and rerun; the workbook is rebuilt from the files every time.

## Common tasks

- **Check a week without writing anything:** `autoreport check --config report.toml --period 2026-09-21`
- **Rerun a week after a corrected file arrives:** run it again with `--period`. The week is replaced, not added. The report notes the file was restated.
- **Backfill several weeks:** put all their files in `inbox/` and run `autoreport run --config report.toml --all`. Weeks run oldest first and stop at the first refusal.
- **See what has been processed:** `autoreport status --config report.toml`
- **Compare with the hand-made report:** `autoreport compare --config report.toml --period 2026-09-21 --manual manual.csv`, where the file has the columns `metric,value`. Known metric names: `revenue`, `orders`, `average_order_value`, `refunds`, `refund_amount`, `refund_rate`, `net_revenue`, `ad_spend`, `paid_roas`, `tickets`, `avg_first_response_min`. A difference is not automatically the tool's error; find out which side is right and write it down.
- **Change a threshold, a recipient or a channel name:** edit `report.toml`. No code change is needed.

## Where things live

| Path | What | Safe to delete? |
|---|---|---|
| `inbox/` | The exports as delivered | Yes, after the week is archived |
| `output/<week>/` | Workbook, dashboard, JSON | Yes; rerun the week to rebuild |
| `outbox/` | Email files: the report, or a no-report notice | Yes |
| `state/history.json` | Each week's KPIs, used for week-over-week and trailing averages | No |
| `state/ledger.json` | Hash of every file processed | No |
| `state/archive/<week>/` | A copy of each accepted input | Keep for as long as reports may be questioned |
| `state/logs/` | One log per week | Yes |
| `state/run.lock` | Present only while a run is in progress | Only if no run is active (see below) |

## Recovery

- **"another run holds state/run.lock":** a run is in progress, or one crashed. Check that no `autoreport` process is running, then delete `state/run.lock` and run again.
- **A run crashed part way:** just run it again. Files are swapped in whole and state is saved last, so there is nothing to clean up. A leftover `*.tmp` file can be deleted.
- **`state/` was lost:** restore it from backup. Without a backup, put the past weeks' files back in `inbox/` (they are in `state/archive/` if that survived) and run `--all` to rebuild history.
- **Moving to another PC:** copy the whole folder including `state/`, make a new virtual environment, `pip install -r requirements.lock`, `pip install -e . --no-deps`, run `autoreport status` to confirm the history came across, then recreate the scheduled task.

## Alerts

- **The report was refused:** exit code 1 and `outbox/no_report_<week>.eml`.
- **The run did not happen at all** (PC off, scheduler disabled): nothing on this PC can report that. Set `alerts.heartbeat_url` in the config to a heartbeat monitor and it will alert when the weekly ping is missing. See `docs/scheduling.md`.

## Back up

`report.toml` and the whole `state/` folder. Everything else can be rebuilt from them.
