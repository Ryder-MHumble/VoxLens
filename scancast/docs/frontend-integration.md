# Frontend Integration

The frontend is a TanStack Start / Vite app in `frontend/`.

## Runtime Behavior

- `/` accepts a research question and routes to `/results?q=...`.
- `/results` creates a draft report immediately, then calls `POST /api/research/stream`.
- The result page renders progress, source batches, outline, takeaways and section deltas as they arrive.
- Normal searches already enable MediaCrawler for Chinese social platforms; clicking **Deep re-run / 娣卞害閲嶈窇** increases per-platform limits and comment depth.
- If the stream fails, the frontend falls back to `POST /api/research`.

## Backend-Owned Data

The frontend should not infer research facts. It renders:

- `report.ui.stages` for progress.
- `report.sources` for the right source rail.
- `report.outline` for the left table of contents.
- `report.takeaways` and `report.sections` for the main report.
- `citations`, `sourceIds`, `quote.sourceId` and `table.evidence` for source highlighting.

## Commands

```powershell
cd "C:\Users\hp\Documents\VoxLens\scancast"
uv run uvicorn app.main:app --app-dir backend --reload --port 8765

cd "C:\Users\hp\Documents\VoxLens\scancast\frontend"
pnpm dev
```

The Vite proxy maps `/api` to `http://127.0.0.1:8765`.

## Validation Checklist

- `uv run python -m compileall -f backend`
- `pnpm build`
- `GET http://127.0.0.1:8765/api/health`
- `GET http://127.0.0.1:8080/results?q=iPhone%2016%20review`

