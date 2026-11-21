# Benchmark

Written by `python -m benchmark.run` from a real run. Nothing here is typed by hand.

- Generator seed: `20260803`. 12 clean weeks of orders, refunds, ad spend and support tickets for an invented shop, with the true KPIs worked out separately in `benchmark/generate.py`.
- 18 corrupted copies of one week, one planted fault each (`benchmark/faults.py`). Each is run twice: with the four exports only, and with a control totals file (row counts and amount totals as the source system states them).
- Run on Python 3.14.3, Windows 11.

## Result

| Measure | Result |
|---|---|
| KPI values matching truth exactly | 876 of 876 |
| Planted faults caught, exports only | 17 of 18 |
| Planted faults caught, with a control totals file | 18 of 18 |
| False alarms on the 12 clean weeks (control totals checked) | 0 |
| Median run time per week | 50 ms (min 41, max 60) for about 1,436 input rows |
| Outputs byte-identical on a second run | 4 of 4 files |

## KPIs against truth, week by week

Each week, every total, every per-channel figure and every week-over-week and trailing-average figure is compared with the truth. A value counts only if it is equal, not close.

| Week of | Revenue, report | Revenue, truth | Orders, report | Orders, truth | Refund rate, report | Refund rate, truth | Values equal | Gate alarms | Run time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-08-03 | $57,848.90 | $57,848.90 | 1,113 | 1,113 | 3.18% | 3.18% | 73 of 73 | 0 | 48 ms |
| 2026-08-10 | $56,970.32 | $56,970.32 | 1,119 | 1,119 | 2.22% | 2.22% | 73 of 73 | 0 | 41 ms |
| 2026-08-17 | $59,847.26 | $59,847.26 | 1,133 | 1,133 | 3.02% | 3.02% | 73 of 73 | 0 | 46 ms |
| 2026-08-24 | $60,025.78 | $60,025.78 | 1,159 | 1,159 | 3.37% | 3.37% | 73 of 73 | 0 | 43 ms |
| 2026-08-31 | $61,683.18 | $61,683.18 | 1,194 | 1,194 | 3.01% | 3.01% | 73 of 73 | 0 | 43 ms |
| 2026-09-07 | $63,899.63 | $63,899.63 | 1,210 | 1,210 | 3.83% | 3.83% | 73 of 73 | 0 | 52 ms |
| 2026-09-14 | $64,164.45 | $64,164.45 | 1,248 | 1,248 | 3.42% | 3.42% | 73 of 73 | 0 | 56 ms |
| 2026-09-21 | $63,611.14 | $63,611.14 | 1,238 | 1,238 | 7.02% | 7.02% | 73 of 73 | 0 | 60 ms |
| 2026-09-28 | $67,166.37 | $67,166.37 | 1,260 | 1,260 | 3.42% | 3.42% | 73 of 73 | 0 | 58 ms |
| 2026-10-05 | $67,103.69 | $67,103.69 | 1,282 | 1,282 | 2.61% | 2.61% | 73 of 73 | 0 | 53 ms |
| 2026-10-12 | $66,159.98 | $66,159.98 | 1,272 | 1,272 | 2.39% | 2.39% | 73 of 73 | 0 | 57 ms |
| 2026-10-19 | $67,798.89 | $67,798.89 | 1,298 | 1,298 | 3.18% | 3.18% | 73 of 73 | 0 | 45 ms |

## Planted faults

Exports only: a fault counts as caught when the gate answers at the expected level with the expected check. A fail must stop the run, write no report and leave a no-report notice in the outbox. A warn must still produce the report, with the warning on its Data Quality sheet.

With control totals: the gate may be stricter than the expected level, because a week that does not balance with the source system is stopped. A fault counts as caught when the run stops, or when it warns at the expected level.

| Fault | What was done to the week | Expected | Exports only | Caught | With control totals | Caught |
|---|---|---|---|---|---|---|
| `missing_file` | Refunds export not delivered | fail | fail (missing_file) | yes | fail (missing_file) | yes |
| `missing_column` | Orders export has no amount column | fail | fail (missing_column) | yes | fail (missing_column) | yes |
| `duplicate_orders` | 40 order rows pasted in twice | fail | fail (duplicate_id) | yes | fail (control_total, duplicate_id) | yes |
| `negative_amount` | One order amount is negative | fail | fail (negative_value) | yes | fail (control_total, negative_value) | yes |
| `text_in_amount` | Three order amounts say N/A | fail | fail (bad_value) | yes | fail (bad_value, control_total) | yes |
| `wrong_week` | Last week's orders file sent again under this week's name | fail | fail (already_processed, date_gap, date_out_of_period) | yes | fail (already_processed, control_total, date_gap, date_out_of_period) | yes |
| `delivered_twice` | Orders file present twice, second copy named (1) | fail | fail (duplicate_file) | yes | fail (duplicate_file) | yes |
| `truncated_export` | Orders export lost 65% of its rows | fail | fail (row_count_swing) | yes | fail (control_total, row_count_swing) | yes |
| `weekend_missing` | No orders for Saturday or Sunday | fail | fail (date_gap) | yes | fail (control_total, date_gap) | yes |
| `corrupt_workbook` | Ad spend workbook cut off mid-download | fail | fail (unreadable_file) | yes | fail (unreadable_file) | yes |
| `negative_response` | One ticket has a negative response time | fail | fail (negative_value) | yes | fail (negative_value) | yes |
| `partial_export` | Orders export lost 38% of its rows | warn | warn (row_count_swing) | yes | fail (control_total) | yes |
| `one_day_missing` | No orders for Wednesday | warn | warn (date_gap) | yes | fail (control_total) | yes |
| `unknown_channel` | 30 orders tagged with a channel not in the config | warn | warn (unknown_channel) | yes | warn (unknown_channel) | yes |
| `missing_spend_day` | Ad spend has no rows for Thursday | warn | warn (date_gap) | yes | fail (control_total) | yes |
| `decimal_slip` | One ad spend value is 100 times too large | warn | warn (outlier_value) | yes | fail (control_total) | yes |
| `empty_refunds` | Refunds export has a header and no rows | warn | warn (empty_file) | yes | fail (control_total) | yes |
| `small_silent_loss` | Orders export lost 3% of its rows at random | warn | pass | **no** | fail (control_total) | yes |

### What the gate said, exports only

- `missing_file`: no refunds export for the week of 2026-09-28 (.csv or .xlsx)
- `missing_column`: missing required column 'amount' (columns found: order_id, order_date, channel, items)
- `duplicate_orders`: 40 order_id values appear more than once (40 extra rows; first: FH-109615)
- `negative_amount`: 1 negative value in column 'amount' (first at row 292)
- `text_in_amount`: 3 values in column 'amount' could not be read (first at row 292: 'N/A')
- `wrong_week`: content is identical to orders_2026-09-21.csv, already processed as orders for the week of 2026-09-21
- `delivered_twice`: 2 orders files for the same week (orders_2026-09-28 (1).csv, orders_2026-09-28.csv); keep one
- `truncated_export`: 441 rows is -64% against the average of 1,222 over the last 4 weeks; check for a cut-off export
- `weekend_missing`: no orders at all on Sat 2026-10-03, Sun 2026-10-04
- `corrupt_workbook`: file could not be read (BadZipFile: File is not a zip file)
- `negative_response`: 1 negative value in column 'first_response_minutes' (first at row 12)
- `partial_export`: 781 rows is -36% against the average of 1,222 over the last 4 weeks; check for a cut-off export
- `one_day_missing`: no orders at all on Wed 2026-09-30
- `unknown_channel`: 30 rows use a channel that is not in the config: 'TikTok Shop' (30); reported under 'Unmapped'
- `missing_spend_day`: no spend row for Paid Search Thu 2026-10-01, Paid Social Thu 2026-10-01, Email Thu 2026-10-01; spend for those days counts as zero
- `decimal_slip`: 1 value in column 'spend' above 25x the typical value (largest 44,723.00 at row 6, typical 507.72); check for a slipped decimal point
- `empty_refunds`: file has a header but no rows; refunds are reported as zero

### Missed

- Exports only: `small_silent_loss` (orders export lost 3% of its rows at random), expected warn, gate said pass.
- With control totals: none.

A loss this small sits inside normal week-to-week movement, so no rule that looks only at the export can flag it without also raising false alarms on clean weeks. With a control totals file it is caught: column 'amount' adds up to 65,239.94, source system says 67,166.37 (difference -1,926.43). Without one it passes. See `LIMITATIONS.md`.

## Byte stability

The last week was run twice and each output compared byte for byte.

| File | Identical on rerun |
|---|---|
| `dashboard_2026-10-19.html` | yes |
| `kpis_2026-10-19.json` | yes |
| `weekly_report_2026-10-19.eml` | yes |
| `weekly_report_2026-10-19.xlsx` | yes |
