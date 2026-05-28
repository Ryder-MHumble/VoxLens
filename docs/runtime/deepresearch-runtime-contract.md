# DeepResearch Runtime Contract

This document is the source of truth for the VoxLens runtime API, run lifecycle, stream events and report contract. Frontend code should render backend-owned state instead of deriving research facts locally.

## Primary API Flow

The default frontend flow is asynchronous and persisted:

1. `POST /api/runs` creates a `RunRecord`, stores `record.json`, initializes `events.jsonl`, and queues the run.
2. `GET /api/runs/{runId}/events` replays stored SSE events first, then follows live events until `final_report` or `error`.
3. `GET /api/runs/{runId}` reopens run metadata and includes the report when it exists.
4. `GET /api/runs/{runId}/report` returns the persisted `ResearchReport` when available.

Compatibility endpoints remain available, but they are not the primary frontend path:

- `POST /api/research`: synchronous `ResearchReport` response for smoke tests and non-stream callers.
- `POST /api/research/stream`: direct POST-based SSE stream for legacy clients.
- `GET /api/demo-report`: demo data only when the user has no query.

`ResearchRequest` supports `maxParallelPlatforms` and `maxParallelVideos`. The current frontend sends conservative defaults for normal runs and raises limits for deep re-runs.

## Run Storage

Run files are stored under `runtime/runs/research/{runId}/`:

- `record.json`: run status, progress, request, timestamps and final report pointer.
- `events.jsonl`: append-only stream events with an added `sequence` field.
- `report.json`: final persisted `ResearchReport` after `final_report`.

The in-process queue is an alpha implementation. It is safe for local/single-node runs, but it is not a distributed job system.

## Stream Events

Both `/api/runs/{runId}/events` and `/api/research/stream` use SSE. The run endpoint adds persisted replay and event `sequence`; event names and payload fields should stay backward-compatible.

Current event order:

1. `run_started`: returns `runId`, `query`, `need`, `lang`, initial `stages` and a message.
2. `stage`: updates stage status, progress and message.
3. `plan`: returns `ResearchPlan` and the `QueryPlannerAgent` step.
4. `provider_started`: announces the active platform/provider target.
5. `sources`: returns an incremental `sources[]` batch and `RunLog` for the finished provider.
6. `agent_step`: returns crawler, evidence guard or synthesis trace.
7. `evidence`: returns ranked sources after evidence scoring.
8. `outline`: returns `outline`, `takeaways`, `insights`, `coverage`, `quality` and warnings.
9. `report_patch`: returns the report shell with empty sections so the UI can enter report layout.
10. `section_started`: starts a report section with an empty body.
11. `section_delta`: appends text to the current section body.
12. `section_complete`: replaces the streamed section with the complete section object.
13. `final_report`: returns the final complete `ResearchReport`.
14. `error`: returns a terminal failure message while preserving replayable prior events.

Do not rename events, remove fields, or reorder the core lifecycle without a frontend migration.

## Frontend-Owned vs Backend-Owned State

Frontend responsibilities:

- Create a run for a query.
- Subscribe to run events.
- Render progress, source cards, outline, citations, section deltas and errors.
- Reopen an existing run when the URL contains `run=...`.

Backend-owned state:

- `report.ui.stages[]`, `event.progress`, `event.message` for progress.
- `report.sources[]` and source IDs for source cards and citation highlighting.
- `report.outline[]` for the table of contents.
- `report.takeaways[]`, `report.insights[]`, `report.coverage` and `report.sections[]` for report content.
- `citations`, `sourceIds`, `quote.sourceId` and `table.evidence` for source linkage.

The frontend may create a temporary draft report while waiting, but the final report shape and research claims come from the backend.

## Fallback and Evidence Rules

- If all live providers fail, the backend returns an evidence-limited report or a failed run; it must not replace the user's query with canned demo facts.
- `minLiveSources` adds a `FallbackGuardAgent` trace when collected sources are below the requested floor. Current report status still comes from collected sources, warnings and quality evaluation; callers should read `confidence`, `quality.warnings`, `warnings[]` and `agentTrace` instead of assuming `minLiveSources` always forces `status=partial`.
- `/api/demo-report` is the only endpoint that intentionally returns sample data.

## Extension Points

- Replace the in-process queue with an external queue only after the alpha thresholds in `docs/alpha-exit-criteria.md` require it.
- Add production provider adapters behind the existing provider registry without changing the `ResearchReport` schema.
- Add LLM/VLM synthesis behind `report_builder` while preserving source IDs and citation semantics.
