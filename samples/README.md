# Samples

One week for an invented shop, Fernhollow Supply Co. All data is synthetic, made by `benchmark/generate.py` with a fixed seed. Rebuild everything here with `python -m benchmark.build_samples`.

## Input: one week's inbox

| File | Rows | What it is |
|---|---:|---|
| [inbox/orders_2026-09-21.csv](inbox/orders_2026-09-21.csv) | 1,238 | One row per order: id, date, channel, items, amount |
| [inbox/refunds_2026-09-21.csv](inbox/refunds_2026-09-21.csv) | 107 | One row per refund: id, order id, date, amount, reason |
| [inbox/ad_spend_2026-09-21.xlsx](inbox/ad_spend_2026-09-21.xlsx) | 21 | Spend and clicks per day per ad platform |
| [inbox/tickets_2026-09-21.csv](inbox/tickets_2026-09-21.csv) | 134 | One row per support ticket, with minutes to first reply |

| [inbox/control_totals_2026-09-21.csv](inbox/control_totals_2026-09-21.csv) | 6 | Optional: row counts and amount totals as the source system states them |

The ad spend export calls its channels `Google Ads` and `Meta Ads`. The config maps them to `Paid Search` and `Paid Social`, the names the orders use.

## Output: what one command wrote

| File | What it is |
|---|---|
| [output/2026-09-21/weekly_report_2026-09-21.xlsx](output/2026-09-21/weekly_report_2026-09-21.xlsx) | The Excel workbook: Summary with KPI tiles and charts, Channels, Daily, Trend, Refunds, Support, Data Quality, Definitions |
| [output/2026-09-21/dashboard_2026-09-21.html](output/2026-09-21/dashboard_2026-09-21.html) | The dashboard. Download it and open it in a browser; it is one file with no outside requests |
| [output/2026-09-21/kpis_2026-09-21.json](output/2026-09-21/kpis_2026-09-21.json) | Every number in the report, plus the gate findings and file hashes |
| [outbox/weekly_report_2026-09-21.eml](outbox/weekly_report_2026-09-21.eml) | The email that would be sent, with the workbook and dashboard attached. Opens in most mail apps. It was not sent |

This week was built to show an alert: a burst of transit damage pushes the refund rate to 7.0%, over the 6.0% limit in the config. The report flags it and still publishes, because a bad week for the business is not bad data.

## Config and state

- [report.toml](report.toml): company name, channels, KPI thresholds, gate thresholds, paths.
- [state/history.json](state/history.json): KPIs for the seven earlier weeks, so this week has something to compare against. Those weeks' input files are not kept here; the generator can rebuild them.
- [state/ledger.json](state/ledger.json): the hash of every file already processed.
- Running the sample also creates `state/archive/` (a copy of each input) and `state/logs/`. Both are left out of the repository.

## Comparing with a hand-made report

[manual_report_2026-09-21.csv](manual_report_2026-09-21.csv) stands in for the report a person used to build by hand. One figure is planted wrong: two digits of the ad spend are swapped.

```text
autoreport compare --config samples/report.toml --period 2026-09-21 --manual samples/manual_report_2026-09-21.csv
```

```text
Week of 2026-09-21: tool against manual_report_2026-09-21.csv
metric                          manual          tool    difference  result
revenue                      63,611.14     63,611.14         +0.00  match
orders                           1,238         1,238            +0  match
average_order_value              51.38         51.38         +0.00  match
refund_amount                 4,467.33      4,467.33         +0.00  match
refund_rate                     0.0702        0.0702       +0.0000  match
ad_spend                      7,873.10      7,837.10        -36.00  DIFFERENT
tickets                            134           134            +0  match

6 of 7 lines match.
Explain each other line before retiring the manual report.
```

## A week the gate refuses

[inbox_bad/](inbox_bad) is the same week with 40 order rows pasted in twice.

```text
autoreport run --config samples/report.toml --inbox samples/inbox_bad
```

It exits with code 1, writes no report, and prints:

```text
No report for the week of 2026-09-21: 3 data problem(s) must be fixed first.
  orders_2026-09-21.csv: column 'amount' adds up to 65,677.91, source system says 63,611.14 (difference +2,066.77)
  orders_2026-09-21.csv: file has 1,278 rows, source system says 1,238 (difference +40)
  orders_2026-09-21.csv: 40 order_id values appear more than once (40 extra rows; first: FH-108377)
```

It also saves a no-report notice to the outbox for the people expecting the report. A copy is kept here as [no_report_example_2026-09-21.eml](no_report_example_2026-09-21.eml).
