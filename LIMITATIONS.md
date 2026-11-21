# Limitations

What this does not handle, as plainly as possible.

## What the gate cannot catch

- **Small silent losses, unless a control total is supplied.** If an export quietly drops a few percent of its rows, the week looks normal. From the exports alone the gate passes it: the benchmark plants exactly this (3% of orders removed at random) and reports it as missed. No rule that looks only at the export can tell a 3% loss from a slightly quiet week without raising false alarms. The sound fix is reconciliation: put a `control_totals_<week>.csv` in the inbox with the row counts and amount totals the source system itself reports, and the gate stops any week that does not balance. With that file the benchmark catches all 18 faults. Whether a client's systems can produce those totals has to be found out per client.
- **Plausible wrong values.** An amount of 54.00 typed as 45.00 passes unless a control total covers that column. Only values far outside the usual range are flagged (25 times the typical value by default).
- **Wrong but valid channel.** An order tagged `Email` that was really `Organic` passes. Unknown channel names are flagged; wrong known ones are not.
- **The first week.** With no earlier week on record, the row-count check has nothing to compare against and is skipped. The report says so on the Data Quality sheet.
- **Row-count checks on small files.** Files that average under 100 rows a week are not checked for swings, because small counts move a lot by chance. In the samples that means refunds and ad spend.

## Input shape

- Four file kinds with fixed column names: orders, refunds, ad spend, tickets. Other data needs a schema added in `src/autoreport/ingest.py`. Header case, spaces and hyphens are ignored; anything else must match.
- Files are matched by name: `<kind>_<week start date>.csv` or `.xlsx`. A file named any other way is ignored, and the gate then reports that kind as missing.
- Weekly periods only, seven days from the date in the file name. No monthly or daily reports.
- XLSX input reads the first sheet only, with the header in row 1. No `.xls`, no password-protected files, no merged header rows.
- Dates: `YYYY-MM-DD` and `YYYY-MM-DD HH:MM[:SS]` always. Slash dates are read in one order only, set by `input.date_order` in the config (`mdy` by default, or `dmy`). A slash date in the other order is rejected as unreadable when its day is above 12, and otherwise lands outside the week and is refused by the date check; it is never silently accepted, but the message will say the date is out of period, not that the order is wrong. One setting covers all files.
- No time zones. A timestamp is taken at face value and assigned to its calendar day.
- One currency, two decimal places. No currency conversion.

## Calculations

- Refund rate is refunds booked in the week divided by revenue in the week. Refunds are not traced back to the week the order was placed.
- Return on ad spend uses the channel on the order as given. There is no attribution model.
- Week-over-week and trailing-average comparisons need consecutive earlier weeks in the history. If a week was skipped, the comparison stops at the gap instead of averaging across it.
- A restated week (its file changed and it was run again) updates that week. Later weeks that were compared against the old numbers are not rebuilt until they are run again.

## Output and delivery

- Email is a dry run. The report message and the no-report notice are saved as `.eml` files and nothing is sent. Sending is left to a mail tool the client already uses.
- The Excel workbook holds values, not formulas. Change an input and rerun; do not edit numbers in the workbook.
- The workbook was checked by reading it back with `openpyxl` (8 sheets, 4 charts, number formats, frozen panes, print titles). It has not been opened in Microsoft Excel, Google Sheets or LibreOffice as part of this build, so chart appearance in each app is unverified.
- The dashboard is English only and has no drill-down. Hover notes need JavaScript; everything else works without it.
- Byte-identical output was checked on Python 3.12, 3.13 and 3.14 with the versions in `requirements.lock`. A different `xlsxwriter` version may write different (still correct) bytes. To make this possible the workbook is stored uncompressed, so it is about 78 KB, several times its compressed size.

## Alerts and unattended running

- The heartbeat ping is off by default and was tested only against a stand-in, never a real monitoring service. It sends no report data, only a request to the URL in the config.
- Nothing on the PC can report that the PC was off. Alerting on a missed run needs an outside heartbeat service; without one, a run that never starts is silent.
- Control totals cover row counts and one amount column per file (orders, refunds, ad spend). There is no control on ticket response times or per-channel splits.
- The input archive grows by about one week of files per week and is never pruned.
- Not done in this version: a per-file date format, a business timezone setting, a machine-readable data dictionary, and reading totals straight from a source system API.

## Scale

- Tested at about 1,500 input rows a week. Files are read fully into memory, so millions of rows would need a different reader.
- One company, one inbox. A lock file stops two runs overlapping on the same state folder; a run that is killed outright leaves the lock behind and it must be deleted by hand (`RUNBOOK.md`).
