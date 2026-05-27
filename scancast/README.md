# VoxLens Alpha Runtime

VoxLens backend/frontend lives in this directory. The product README at the repository root explains the business positioning and demo flow; this file focuses on local alpha operation.

## Runtime Shape

- `backend/app/main.py`: FastAPI entrypoint.
- `backend/app/services/run_queue.py`: in-process async queue and run event fan-out.
- `backend/app/services/run_store.py`: persisted run records, events and reports under `scancast/runs/research/`.
- `backend/app/services/llm_synthesis.py`: OpenRouter synthesis layer. Reads `OPENROUTER_API_KEY` and uses `OPENROUTER_MODEL=z-ai/glm-5.1` by default.
- `backend/app/services/quality.py`: coverage, citation accuracy, evidence strength and conclusion-risk evaluation.
- `backend/app/providers/registry.py`: provider boundary. `local` keeps OpenCLI/MediaCrawler for dev; `online` can point to a production provider service.
- `../external/MediaCrawler/`: vendored NanmiCoder/MediaCrawler component used by local Chinese-platform crawlers; upstream revision is recorded in `../external/MediaCrawler.UPSTREAM_REVISION`.
- `frontend/`: TanStack/Vite frontend that creates a run, streams run events, and can reopen an existing run by URL.

## Environment

Copy the example file and fill secrets locally:

```powershell
copy .env.example .env
```

Important variables:

```text
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=z-ai/glm-5.1
VOXLENS_ENABLE_LLM=true
VOXLENS_ONLINE_PROVIDER_URL=
VOXLENS_BILIBILI_COOKIE=
VOXLENS_DOUYIN_COOKIE=
VOXLENS_XHS_COOKIE=
VOXLENS_ZHIHU_COOKIE=
VOXLENS_KUAISHOU_COOKIE=
VOXLENS_WEIBO_COOKIE=
```

Do not commit `.env` or any API key.

## Run Locally

Install all local dependencies from the repository root first:

```bash
./scripts/bootstrap.sh
```

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1
```

Backend:

```powershell
cd "C:\Users\hp\Documents\VoxLens\scancast"
uv sync
uv run uvicorn app.main:app --app-dir backend --reload --port 8765
```

Frontend:

```powershell
cd "C:\Users\hp\Documents\VoxLens\scancast\frontend"
pnpm install
pnpm dev
```

## API Flow

Create an async run:

```http
POST /api/runs
```

Stream or replay events:

```http
GET /api/runs/{runId}/events
```

Reopen run metadata/report:

```http
GET /api/runs/{runId}
GET /api/runs/{runId}/report
```

Legacy endpoints remain for compatibility:

```http
POST /api/research
POST /api/research/stream
```

## Provider Modes

- `providerMode=local`: default alpha mode. Uses OpenCLI, MediaCrawler and yt-dlp fallback where available.
- `providerMode=online`: calls `VOXLENS_ONLINE_PROVIDER_URL` using the normalized provider contract.
- `providerMode=hybrid`: tries the online provider when configured, then falls back to local.

Baidu/Tieba is intentionally excluded from the default alpha platform set.

## Validate

```powershell
cd "C:\Users\hp\Documents\VoxLens\scancast"
uv run python -m compileall -f backend

cd "C:\Users\hp\Documents\VoxLens\scancast\frontend"
pnpm build
```
