# VoxLens Architecture

## Decision

VoxLens is organized as an integrated product monorepo instead of a thin app shell around visible outside projects.

```text
apps/api/                 FastAPI research runtime
apps/web/                 Web product experience
packages/crawler/         Integrated crawler runtime
packages/research_cli/    Local research CLI
runtime/runs/             Local runtime output, ignored by Git
docs/runtime/             Runtime and integration documentation
```

## Rationale

- Product contributors should see one VoxLens system, not a legacy app shell plus an outside dependency folder.
- Runtime code needs stable product-level paths for crawler output, run persistence, and capability detection.
- Platform/provider metadata should have one backend source of truth (`apps/api/app/platform_catalog.py`) instead of repeated lists across reports, capabilities and crawler adapters.
- The crawler package should feel like a first-class VoxLens runtime component instead of a visible outside project.
- Legal attribution and risk notices must stay explicit even though standalone upstream docs are removed.

## Trade-offs

- Keeping the crawler source in `packages/crawler/` makes the repository larger, but avoids a fragile clone/bootstrap step.
- Removing standalone crawler docs, WebUI assets and unrelated platform paths reduces external-project leakage, but copyright headers and license notices remain for compliance.
- Runtime outputs are centralized in `runtime/runs/`, which simplifies cleanup and deployment but requires path updates in scripts and docs.

## Operational Rules

- Store local API secrets in `apps/api/.env`; never commit `.env` files.
- Write persisted run records to `runtime/runs/research/`.
- Write crawler collection output to `runtime/runs/crawler/`.
- Install everything from the repository root with `scripts/bootstrap.sh` or `scripts/bootstrap.ps1`.
- Run `scripts/validate_runtime.sh` or `scripts/validate_runtime.ps1` before merging runtime changes.
- Keep crawler-related risk warnings in the README, root `LICENSE`, `THIRD_PARTY_NOTICES.md` and `packages/crawler/LICENSE`.
