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
- The crawler package must remain easy to update from upstream while still feeling like a first-class VoxLens runtime component.
- Legal attribution must stay explicit even though the component is structurally integrated.

## Trade-offs

- Keeping the crawler source in `packages/crawler/` makes the repository larger, but avoids a fragile clone/bootstrap step.
- Preserving upstream README and license files inside the package keeps compliance clear, but some internal package files still mention the upstream project name.
- Runtime outputs are centralized in `runtime/runs/`, which simplifies cleanup and deployment but requires path updates in scripts and docs.

## Operational Rules

- Store local API secrets in `apps/api/.env`; never commit `.env` files.
- Write persisted run records to `runtime/runs/research/`.
- Write crawler collection output to `runtime/runs/crawler/`.
- Install everything from the repository root with `scripts/bootstrap.sh` or `scripts/bootstrap.ps1`.
- Track crawler upstream changes in `packages/crawler/UPSTREAM_REVISION` and `THIRD_PARTY_NOTICES.md`.
