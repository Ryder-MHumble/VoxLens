# VoxLens Alpha Runtime

VoxLens runtime is organized as an integrated monorepo. The product README at the repository root explains the business positioning and demo flow; this file focuses on local alpha operation.

## Runtime Shape

- `apps/api/app/main.py`: FastAPI entrypoint.
- `apps/api/app/services/run_queue.py`: in-process async queue and run event fan-out.
- `apps/api/app/services/run_store.py`: persisted run records, events and reports under `runtime/runs/research/`.
- `apps/api/app/services/llm_synthesis.py`: OpenRouter synthesis layer. Reads `OPENROUTER_API_KEY` and uses `OPENROUTER_MODEL=z-ai/glm-5.1` by default.
- `apps/api/app/services/quality.py`: coverage, citation accuracy, evidence strength and conclusion-risk evaluation.
- `apps/api/app/providers/registry.py`: provider boundary. `local` keeps OpenCLI, VoxLens crawler runtime and yt-dlp in one product runtime; `online` can point to a production provider service.
- `packages/crawler/`: integrated VoxLens crawler runtime for Chinese-platform collection; upstream attribution and revision are recorded in `packages/crawler/UPSTREAM_REVISION` and `THIRD_PARTY_NOTICES.md`.
- `apps/web/`: TanStack/Vite frontend that creates a run, streams run events, and can reopen an existing run by URL.

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
cd "C:\Users\hp\Documents\VoxLens\apps\api"
uv sync
uv run uvicorn app.main:app --reload --port 8765
```

Frontend:

```powershell
cd "C:\Users\hp\Documents\VoxLens\apps\web"
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

- `providerMode=local`: default alpha mode. Uses OpenCLI, VoxLens crawler runtime and yt-dlp fallback where available.
- `providerMode=online`: calls `VOXLENS_ONLINE_PROVIDER_URL` using the normalized provider contract.
- `providerMode=hybrid`: tries the online provider when configured, then falls back to local.

Baidu/Tieba is intentionally excluded from the default alpha platform set.

## Validate

```powershell
cd "C:\Users\hp\Documents\VoxLens\apps\api"
uv run python -m compileall -q -f app

cd "C:\Users\hp\Documents\VoxLens\apps\web"
pnpm build
```
