# Runtime Documentation Index

Use this folder as the runtime source of truth:

- `deepresearch-runtime-contract.md`: canonical API, run lifecycle, event stream and report ownership contract.
- `frontend-integration.md`: how the current frontend consumes the runtime contract without owning research facts.
- `backend-agent-architecture.md`: backend agent pipeline and provider boundaries.
- `ops-runbook.md`: safe local operation, crawler risk controls and incident response.
- `brand.md`: product-facing brand payload and visual language.

Rules for future changes:

- Define endpoint, event and report-schema changes in `deepresearch-runtime-contract.md` first.
- Keep `docs/runtime.md` as an operator guide, not a second contract definition.
- Do not change frontend interactions, event names, event order or citation/source ID semantics without an explicit migration note and verification evidence.
