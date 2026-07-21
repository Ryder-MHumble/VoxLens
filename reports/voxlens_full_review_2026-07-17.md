# VoxLens Studio Full Project Review — 2026-07-17

## Scope

Reviewed the modified/new backend agent, evidence, ASR, citation, report, stream, verification, brand, frontend metadata, README, and architecture files. The crawler package was not modified and no platform collection, browser/CDP, media download, or ASR execution was run.

## Executive Summary

The evidence-domain models and individual agent modules were structurally sound, but the runtime contained several high-severity false connections: the streaming path bypassed the new architecture, the coverage gate did not actually block synthesis, grounding verified a synthetic claim set rather than delivered report claims, and report LLM calls bypassed the orchestrator. These connections are now unified through one post-acquisition pipeline.

The public `ResearchReport` field set and legacy `Source` serialization keys remain unchanged. Product positioning is now consistent around **VoxLens Studio** and **“从视频里拿证据，不是拿答案。 / Evidence, not answers.”**

## Findings by Severity

### High — Fixed

1. **Streaming runtime bypassed the new agent architecture.**
   - Before: `research_stream.py` ran `prepare_evidence()` and `build_report()` directly.
   - Impact: no shared budget, supplemental coverage retry, coverage gate, orchestrator, or final grounding on streaming/queued runs.
   - Fix: both paths now call `complete_research_pipeline()` after acquisition.

2. **Grounding verified the wrong claims.**
   - Before: deterministic claims copied evidence-unit text, were verified, and then a separate report was generated.
   - Impact: verification could pass while the delivered report contained different conclusions.
   - Fix: claims are now adapted from final report takeaways/insights and verified before delivery.

3. **CoverageGate was advisory rather than a gate.**
   - Before: `blocked=True` only changed trace/warnings; report LLM synthesis could still run.
   - Impact: severe platform/entity/evidence gaps could still produce generative conclusions.
   - Fix: unresolved severe gaps block LLM synthesis and force deterministic evidence-limited reporting.

4. **LLMOrchestrator was not connected to report synthesis.**
   - Before: the orchestrator wrapped only an unused `ClaimSet` fallback; `build_report()` invoked LLM synthesis directly.
   - Impact: production LLM calls bypassed shared retry and budget policy.
   - Fix: production report synthesis receives a precomputed `LlmSynthesisResult` from `LLMOrchestrator`; direct builder behavior remains only for isolated compatibility/tests.

5. **Raw Artifact hashes omitted full transcripts.**
   - Before: `Source.model_dump()` excluded internal transcript fields, so the artifact payload/hash did not represent all captured evidence.
   - Impact: provenance and integrity checks could not cover the strongest text evidence.
   - Fix: artifact payloads explicitly preserve and hash full transcript text and segments while API serialization remains unchanged.

### Medium — Fixed

6. **Evidence intent and evidence modality were conflated.**
   - Before: planner values such as `review`/`complaint` were compared directly with modalities such as `text`/`speech`.
   - Impact: gap reporting produced false `evidence_type` misses.
   - Fix: contracts now distinguish `evidence_intents` from `evidence_modalities_found` and map intents to satisfying modalities.

7. **Immutability claims were only partially enforced.**
   - Before: frozen envelopes contained mutable evidence-domain Pydantic models.
   - Fix: new Artifact/EvidenceUnit/Claim/ClaimEvidence/quality models are frozen; collection fields used by Claims/Artifacts are tuples; legacy Source remains mutable but is defensively copied at boundaries.

8. **Product positioning was inconsistent.**
   - Before: README, API brand payload, report slogan, and web metadata used different promises including “multimodal DeepResearch” and “Research beyond text.”
   - Fix: product name, positioning, slogan, report defaults, frontend metadata, and README copy now use the same evidence-first workspace narrative.

9. **Dead pre-report synthesis code remained after the architecture rewrite.**
   - Before: `synthesize_claim_set()` produced a ClaimSet not used to build the report.
   - Fix: removed and replaced with `build_claim_set_from_report()`.

### Low / Remaining Limitations

10. **ASR is adapter-ready, not an active normal-run stage.**
    - Normal runs plan candidates only. `ASRPipeline.run()` is verified offline but requires an execution adapter/provider.
    - Action: documented explicitly; no media execution was added in this scope.

11. **Citation parser is not exposed in the public report.**
    - Structured timestamp/comment citations remain library-ready because changing report citation shape would break compatibility.

12. **Normal-run evidence granularity remains one aggregate unit per source.**
    - This is adequate for transitional grounding but weaker than timestamp/comment-level review.

13. **Grounding remains heuristic.**
    - Lexical overlap and polarity can produce false positives/negatives. High-stakes entailment still requires human review or a stronger verifier.

14. **Streaming supplemental retries are less granular than initial provider progress.**
    - The stream emits the supplemental agent step and merged source batch, but not per-provider progress inside the bounded retry.

## Actual Architecture Status

| Component | Status |
| --- | --- |
| Immutable stage envelopes | Implemented with defensive Source snapshots |
| Artifact provenance/hash | Implemented, including internal transcript content |
| Shared sync/stream post-acquisition flow | Implemented |
| Budget and stop policy | Implemented |
| Coverage retry and LLM block | Implemented |
| Seven-dimensional quality assessment | Implemented |
| Report LLM orchestrator | Implemented |
| Final-report claim grounding | Implemented |
| ASR execution in normal runs | Skeleton only |
| Structured timestamp/comment citations in API | Not exposed for compatibility |

## Compatibility Review

- `ResearchReport` field set is unchanged.
- Legacy `Source` JSON keys are preserved.
- `fullTranscript`, `transcriptText`, and `transcriptSegments` remain excluded from API serialization.
- Existing numeric source citations remain unchanged.
- Stream event names and final report event shape remain unchanged.

## Validation Results

Executed offline on 2026-07-17 without crawler, browser/CDP, media, or network access:

```bash
python3 -m compileall -q apps/api/app scripts
PYTHONPATH=apps/api python3 scripts/verify_evidence_model.py
PYTHONPATH=apps/api python3 scripts/verify_agent_architecture.py
```

- Python compile: passed.
- Evidence model verification: passed, 5 checks.
- Agent architecture verification: passed, 6 checks.
- API unit tests: passed, 25 tests.
- Offline synchronous/streaming equivalence smoke: passed; both reports contain the shared coverage, evidence, report synthesis, and grounding trace steps and preserve the same report field set.
- `git diff --check`: passed.
- Frontend build: not executed because `apps/web/node_modules` is absent; no dependency installation was attempted.
