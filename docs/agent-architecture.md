# Agent Architecture

## Objective

The agent layer enforces an evidence-first flow without changing the public `ResearchReport` response. Its central rule is that every stage receives a snapshot contract from the preceding stage; optional LLM work is budgeted and can be blocked without preventing a deterministic report.

## Shared Execution

`apps/api/app/agents/coordinator.py` exposes two entry points:

- `run_agentic_research()` for the synchronous `/api/research` endpoint.
- `complete_research_pipeline()` for the shared post-acquisition flow used by synchronous, streaming, and queued runs.

The streaming path retains `iter_crawl_sources()` so it can emit provider progress, then converts the collected values into the same `AcquisitionBatch` used by the synchronous path.

## Artifact Contract

The stage contracts live in `apps/api/app/agents/artifacts.py`:

```text
PlanSpec
  -> AcquisitionBatch
  -> EvidenceBatch
  -> ResearchReport
  -> ClaimSet
  -> VerifiedReport
```

- Dataclass envelopes are frozen.
- New evidence-domain Pydantic models are frozen.
- Source and run-log values are defensively copied at boundaries.
- `PlanSpec.platform_queries` and `EvidenceBatch.source_scores` use read-only mappings.
- `Source` itself remains mutable for compatibility with providers and report decoration, so stage code must never pass crawler-owned instances forward without copying them.

## Budget and Stop Policy

`ResearchBudget` is the shared mutable ledger. It tracks:

- maximum unique sources;
- ASR minutes allowance;
- LLM call attempts;
- LLM token allowance;
- maximum elapsed time;
- minimum source and platform thresholds for synthesis.

`StopPolicy` decides whether acquisition should continue, whether evidence is unusable, and whether a platform is retryable. Supplemental acquisition is bounded to one plan generated from coverage gaps.

## Coverage Gate

`CoverageGate` evaluates:

- platforms actually represented;
- planned entities found in searchable source text;
- evidence modalities present (`text`, `speech`, `comment`, `ocr`, and declared channels);
- explicit counterevidence signals;
- search intents that remain unsupported by available modalities.

`should_block_synthesis()` applies only to LLM synthesis. A blocked run still returns a deterministic report with an explicit warning. This avoids turning incomplete evidence into a confident generative narrative while preserving a usable audit artifact.

## Evidence Structuring

`prepare_evidence_batch()` adapts the legacy ranked `Source` list into:

- one aggregate `EvidenceUnit` per source;
- one seven-dimensional `EvidenceQualityAssessment` per source;
- a source-to-quality-label mapping.

The adapter prefers full transcript text, then transcript text/preview, summary, title, and sampled comments. The raw `Artifact` hash includes internal transcript fields even though those fields remain excluded from public `Source` serialization.

## LLM Orchestrator

`LLMOrchestrator` owns optional report synthesis:

1. Verify that call and token budgets can fit the declared `LLMCallSpec`.
2. Invoke the configured provider and retry within limits.
3. Account for reported token usage, or conservatively charge the declared maximum when usage is unavailable.
4. Fall back to the deterministic report when no provider is configured, coverage blocks synthesis, retries fail, or budget is exhausted.

The report builder still supports direct LLM synthesis for isolated tests and compatibility, but production research paths pass a precomputed `LlmSynthesisResult` supplied by the orchestrator.

## Grounding Verifier

Grounding happens after report synthesis:

1. `build_claim_set_from_report()` converts final takeaways and insights into `Claim` models.
2. Numeric source citations are mapped to evidence units.
3. Candidate `ClaimEvidence` links start as `insufficient`; a citation alone is not treated as proof.
4. `ClaimGroundingVerifier` applies linked evidence, lexical overlap, and polarity rules.
5. Insufficient or contradictory results are exposed through the existing warning and agent-trace fields.

The deterministic verifier is intentionally conservative and heuristic. It is not a substitute for human entailment review in high-stakes research.

## ASR Boundary

`apps/api/app/services/asr_pipeline.py` defines permission, extraction, VAD, ASR, cache, artifact, and timestamped evidence interfaces. Normal research runs currently call only `plan_asr_candidates()`; they do not execute media download, ffmpeg, or ASR automatically. This is an explicit skeleton boundary, not an active multimodal claim.

## Failure Behavior

- No live providers: return a planning/demo fallback without factual claims.
- No/weak evidence: return an evidence-limited report and add `FallbackGuardAgent`.
- Coverage gap: optionally retry once, then block LLM synthesis if still severe.
- LLM unavailable/failing: return deterministic report.
- Grounding failure: return report with warnings; do not silently delete cited material.

## Verification

```bash
PYTHONPATH=apps/api python3 scripts/verify_agent_architecture.py
```

The six offline checks cover contract immutability and serialization compatibility, budget/stop policy, coverage, grounding, orchestrator behavior, and the complete shared flow.
