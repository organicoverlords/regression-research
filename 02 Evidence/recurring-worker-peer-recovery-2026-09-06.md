# Recurring worker peer-recovery verification — 2026-09-06

## Scope
Durable evidence for the first observed end-to-end sibling recovery in the canonical five-worker recurring fleet. This record is historical evidence only; current ChatGPT Automations state remains authoritative for enabled/disabled membership.

## Observed sequence
- Maple scheduler invocation: `2026-09-06T14:43:49.569791Z` (`17:43:49+03:00`).
- Maple was disabled at scheduler `updated_at: 2026-09-06T14:44:52.079317Z`, about 63 seconds after that invocation.
- Maple's current durable report did not advance to a fresh generation for that invocation; its latest report remained the run ending at `2026-09-06T17:02:29.3253506+03:00`.
- Pine began a fresh run at `2026-09-06T17:56:09.4643898+03:00` and recorded the full peer-recovery signature in its own durable report.
- Pine's report records: `Peer recovery: re-enabled canonical sibling Maple ... exact action is_enabled=true; result SUCCESS at 2026-09-06T14:56:18.652056Z`.
- A subsequent authoritative scheduler read showed Maple `is_enabled: true` with `updated_at: 2026-09-06T14:56:39.329255Z`.
- The user independently reported that all five canonical workers appeared enabled in the ChatGPT UI; the subsequent scheduler read agreed.

## Finding
The distributed peer-recovery design is now proven end-to-end for one natural failure event:

`scheduled invocation -> no corresponding fresh report generation -> ~63 s disable -> sibling detects exact scheduler/report gap -> sibling requests re-enable -> action is recorded -> scheduler later reflects enabled state`

The earlier apparent mismatch immediately after Pine's action was a propagation/read timing issue, not proof that the re-enable failed. A scheduler read taken roughly twenty seconds later reflected the successful recovery.

## Current contract and recurrence prevention
`04 Operating Contracts/fresh-worker-generation-launch.md` owns the recurring-worker boundary. Every recurring worker performs one bounded fleet-health check after its own report begin and before product mutation, may re-enable only a disabled canonical sibling matching the full pre-report startup-failure signature, and must record one explicit `Peer recovery:` result in its own durable report. Workers may not administer themselves or alter sibling schedules/prompts/titles/timezones/staggers.

## Evidence pointers
- Pine current report: `worker-reports/current/6a9adc0dbf6481919c607312a5041d1d.md`
- Maple current report: `worker-reports/current/6a9adc04e6a881918433be70752b1426.md`
- Canonical recurring-worker contract: `04 Operating Contracts/fresh-worker-generation-launch.md`
- Shared convergence issue: `organicoverlords/regression-research#125`

## Remaining uncertainty
One successful recovery proves the mechanism can work; it does not prove every future disable will match this failure signature or that every scheduler update will propagate with the same latency. Future workers must continue to require the complete scheduler/report signature and must not infer failure or recovery from report staleness, scheduler enabled state, or a worker's claimed action alone.
