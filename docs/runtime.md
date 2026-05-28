# VoxLens Alpha Runtime

VoxLens runtime is organized as an integrated monorepo. The product README explains positioning and demo flow; this file is the local operator guide. The canonical API/event contract lives in `docs/runtime/deepresearch-runtime-contract.md`.

## Runtime Shape

- `apps/api/app/main.py`: FastAPI entrypoint.
- `apps/api/app/platform_catalog.py`: shared platform metadata, crawler mapping and cookie env aliases.
- `apps/api/app/services/run_queue.py`: in-process async queue and run event fan-out.
- `apps/api/app/services/run_store.py`: persisted run records, events and reports under `runtime/runs/research/`.
- `apps/api/app/services/llm_synthesis.py`: OpenRouter synthesis layer. Reads `OPENROUTER_API_KEY` and uses `OPENROUTER_MODEL=z-ai/glm-5.1` by default.
- `apps/api/app/services/quality.py`: coverage, citation accuracy, evidence strength and conclusion-risk evaluation.
- `apps/api/app/providers/registry.py`: provider boundary. `local` keeps OpenCLI, VoxLens crawler runtime and yt-dlp in one product runtime; `online` can point to a production provider service.
- `packages/crawler/`: integrated VoxLens crawler runtime for Chinese-platform collection; standalone crawler docs and unrelated platform paths are removed, while license and third-party notices remain in `packages/crawler/LICENSE` and `THIRD_PARTY_NOTICES.md`.
- `apps/web/`: TanStack/Vite frontend that creates a run, streams run events, and can reopen an existing run by URL.

## Environment

Copy the example file and fill secrets locally:

```bash
cp .env.example .env
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

Do not commit `.env`, cookies or API keys.

## Run Locally

Install all local dependencies from the repository root first. The frontend package manager is `pnpm`.

```bash
./scripts/bootstrap.sh
```

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1
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

## API Flow

Primary asynchronous flow:

```http
POST /api/runs
GET /api/runs/{runId}/events
GET /api/runs/{runId}
GET /api/runs/{runId}/report
```

Compatibility endpoints:

```http
POST /api/research
POST /api/research/stream
```

`/api/demo-report` is only for empty-query demos.

## Risk Boundary

Local collection uses crawler-style access and browser automation. Keep runs low-frequency, use test accounts where possible, and do not bypass platform controls. Misuse can trigger rate limits, verification challenges, IP blocking, account suspension or account bans, especially on Xiaohongshu/RedNote, Douyin, Bilibili, Kuaishou, Weibo and Zhihu.

Operational rules and stop conditions are in `docs/runtime/ops-runbook.md`.

## Provider Modes

- `providerMode=local`: default alpha mode. Uses OpenCLI, VoxLens crawler runtime and yt-dlp fallback where available.
- `providerMode=online`: calls `VOXLENS_ONLINE_PROVIDER_URL` using the normalized provider contract.
- `providerMode=hybrid`: tries the online provider when configured, then falls back to local.

Baidu/Tieba has been removed from the crawler runtime because it is outside the current VoxLens social-video alpha scope.

## Capacity Assumptions

The current queue and run store are alpha-local infrastructure:

- One local API process owns the queue.
- Runs are persisted on the local filesystem.
- Event replay is durable for local restarts after the event has been written.
- Cancellation, retry, distributed workers and scheduled collection are intentionally out of scope.

Use `docs/alpha-exit-criteria.md` to decide when to upgrade the queue or storage model.

## Validate

Runtime smoke gate:

```bash
./scripts/validate_runtime.sh
```

Windows PowerShell:

```powershell
.\scripts\validate_runtime.ps1
```

Optional frontend build check:

```bash
cd apps/web
pnpm build
```
