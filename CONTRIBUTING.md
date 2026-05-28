# Contributing to VoxLens

VoxLens is an alpha monorepo with a FastAPI backend, TanStack/Vite frontend, research CLI and integrated crawler runtime. The project priority is to preserve existing research capability and frontend interaction while improving maintainability.

## Change Principles

- Keep changes surgical; every changed line should map to the requested outcome.
- Do not rename stream events, remove response fields, or change source/citation IDs without an explicit migration.
- Do not change frontend interaction behavior unless the issue explicitly asks for it.
- Keep crawler risk notices and license notices intact when moving or deleting files.
- Prefer shared metadata and documented contracts over duplicated platform/provider lists.

## Local Setup

```bash
./scripts/bootstrap.sh
```

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1
```

The frontend package manager is `pnpm`. Do not introduce a second frontend install path unless the project deliberately changes package managers.

## Validation

Run the runtime smoke gate before opening or merging PRs that touch backend, CLI, crawler, scripts or runtime docs:

```bash
./scripts/validate_runtime.sh
```

Windows PowerShell:

```powershell
.\scripts\validate_runtime.ps1
```

Optional frontend build check for UI or API-client changes:

```bash
cd apps/web
pnpm build
```

## Documentation Ownership

- Runtime API and event contract: `docs/runtime/deepresearch-runtime-contract.md`
- Local operation guide: `docs/runtime.md`
- Frontend consumption notes: `docs/runtime/frontend-integration.md`
- Crawler/auth risk handling: `docs/runtime/ops-runbook.md`
- Alpha readiness: `docs/alpha-exit-criteria.md`

## Review Checklist

Every PR should state:

- Change surface: `apps/api`, `apps/web`, `packages/crawler`, `packages/research_cli`, docs or scripts.
- Risk level and rollback plan.
- Verification commands and results.
- Whether API events, report schema, crawler behavior, frontend interaction, or license/risk notices changed.
