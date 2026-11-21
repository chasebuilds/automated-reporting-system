# Maintenance terms (template)

A starting point to agree in writing before delivery. Square brackets are to be filled in per project. Nothing here applies until both sides have agreed to it.

## What is covered

For [30] days after delivery, defects are fixed at no charge.

A **defect** is the tool not doing what the written specification says, on input that meets the input contract in `RUNBOOK.md`. Examples: a KPI that does not match its definition on the `Definitions` sheet, a gate check that passes a file it is documented to refuse, a crash on valid input.

Reported defects get a first reply within [2] working days.

## What is a change request, not a defect

Quoted and scheduled separately:

- The source system changed its export: a renamed, removed or added column, a new date or number format, a new file.
- A new metric, chart, sheet, recipient or schedule.
- A new channel that needs its own rules (a new label for an existing channel is a config edit the client can make).
- Different thresholds because the business changed.

## What is outside our control

No promise is made about:

- The source systems continuing to produce the same exports.
- The client's PC, scheduler, network, email account or cloud runner being up at the scheduled time. No uptime figure is offered for equipment we do not run.
- Scheduled runs on a third-party service that delays or pauses them.
- The accuracy of the input data beyond the checks listed in the README. The gate reduces the risk of a wrong report; it cannot remove it. `LIMITATIONS.md` lists what it does not catch.

## What the gate will do

Stop the report, with a message naming the file and the problem, on every condition in the "Fail" column of the README's check table. This is the behaviour to hold us to.

## Monitoring

Not included unless named here as a paid service: [none / describe]. Without it, the client is the one who sees the no-report notice or the missed heartbeat and gets in touch.

## Handover

At delivery the client holds every file, the repository, the config, this document and the runbook. Any account or credential the pipeline uses is created and owned by the client. A handover call walks through one normal run, one refused run and one rerun.

## After the fix window

Support continues only under a separate, scoped agreement: [hours, rate, reaction time].
