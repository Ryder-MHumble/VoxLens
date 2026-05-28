# Frontend Integration

The frontend is a TanStack Start / Vite app in `apps/web/`. This document describes how it consumes the backend contract; the canonical API and event definitions live in `docs/runtime/deepresearch-runtime-contract.md`.

## Runtime Behavior

- `/` accepts a research question and routes to `/results?q=...`.
- `/results` creates a draft report immediately, then calls `POST /api/runs`.
- The backend returns a `runId`; the page writes it to the URL and subscribes to `GET /api/runs/{runId}/events`.
- When a URL already includes `run=...`, the page first calls `GET /api/runs/{runId}` to reopen persisted state, then follows the event stream.
- The result page renders progress, source batches, outline, takeaways and section deltas as events arrive.
- Normal searches enable the VoxLens crawler runtime for Chinese social platforms; **Deep re-run / 深度重跑** increases per-platform limits and comment depth.
- If run creation or event streaming fails, the frontend falls back to the synchronous `POST /api/research` endpoint.

The legacy `POST /api/research/stream` helper remains in the API client for compatibility, but it is not the primary result-page path.

## Backend-Owned Data

The frontend should not infer research facts. It renders:

- `report.ui.stages` for progress.
- `report.sources` for the right source rail.
- `report.outline` for the left table of contents.
- `report.takeaways`, `report.insights`, `report.coverage` and `report.sections` for the main report.
- `citations`, `sourceIds`, `quote.sourceId` and `table.evidence` for source highlighting.

## Commands

From the repository root:

```bash
./scripts/bootstrap.sh
```

Backend:

```bash
cd apps/api
uv run uvicorn app.main:app --reload --port 8765
```

Frontend:

```bash
cd apps/web
pnpm dev
```

The Vite proxy maps `/api` to `http://127.0.0.1:8765`.

## Validation Checklist

From the repository root:

```bash
./scripts/validate_runtime.sh
```

Optional frontend build check:

```bash
cd apps/web
pnpm build
```
