# Alpha Exit Criteria

VoxLens should leave internal alpha only when reliability, evidence quality and operating safety are measurable. These criteria are intentionally product- and maintenance-focused; they do not require new frontend interactions.

## Milestone Metrics

| Area | Metric | Target | Source | Owner |
| --- | --- | --- | --- | --- |
| Run reliability | Runs reach `final_report` or a clear `error` | >= 90% across a 20-run sample | `runtime/runs/research/*/record.json` | API owner |
| Reopen reliability | Persisted run can reopen by `runId` | 100% for completed sample runs | `GET /api/runs/{runId}` | API owner |
| Evidence coverage | Reports with at least 3 citable sources | >= 80% for supported-platform queries | `report.json` | Research owner |
| Citation integrity | Citation IDs resolve to source cards | 100% in manual spot checks | UI + `report.sources[]` | Web owner |
| Time to first source | First `sources` event arrives | <= 90 seconds for local alpha runs | `events.jsonl` timestamps/logs | Runtime owner |
| Risk handling | Runs with platform challenges stop and are documented | 100% of incidents | issue/PR notes | Repo governor |

## Required Project Controls

- Runtime contract changes are documented in `docs/runtime/deepresearch-runtime-contract.md`.
- `scripts/validate_runtime.sh` or `scripts/validate_runtime.ps1` passes before merging runtime changes.
- PRs state whether they affect API events, report schema, crawler behavior, frontend interaction, or license/risk notices.
- Crawler/auth changes include stop conditions and verification notes.

## Expansion Gate

Do not add new platforms, new event names, or new frontend interaction paths until:

- Existing default platforms pass the reliability sample.
- The shared platform catalog is updated with provider, auth and capability metadata.
- The operation runbook has platform-specific risk notes if the platform has unique constraints.

## Architecture Upgrade Triggers

Consider replacing the in-process queue and file storage only when one of these becomes true:

- More than one API process must handle the same run queue.
- Concurrent local runs regularly exceed low single digits.
- Operators need cancellation, retry, priority, or scheduled jobs.
- `runtime/runs/research/` becomes a shared production data store instead of local alpha output.
