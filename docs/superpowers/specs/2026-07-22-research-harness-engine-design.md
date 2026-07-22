# Research Harness Engine Design

## Objective

Extract a small, reusable research harness from the existing VoxLens pipeline without changing the public `ResearchReport` contract or introducing a database, queue service, graph store, or new dependency.

The first version must make research stages observable, checkpointed, replayable, and able to persist the evidence-domain objects that currently disappear after report generation.

## Scope

The first implementation covers:

- a typed operator contract;
- deterministic dependency ordering;
- stage lifecycle and event recording;
- file-backed checkpoints and resume for resumable operators;
- persisted Artifact, EvidenceUnit, Claim, ClaimEvidence, and verification snapshots;
- integration with queued runs through the existing `RunManager`;
- exact propagation of failed, partial, and completed report states.

It does not implement media download, ASR execution, OCR, parallel workers, distributed scheduling, graph databases, cross-run search, or a new public API.

## Design Principles

1. The evidence model is logical. Storage remains files under one run directory.
2. Deterministic work stays in operators; LLM calls remain optional dependencies of operators.
3. A checkpoint is immutable evidence of one completed operator attempt, not a mutable shared blackboard.
4. Replay never executes an operator. A missing, stale, or invalid resumable checkpoint fails closed without calling crawlers, providers, or LLMs.
5. Current synchronous and streaming API schemas remain unchanged.
6. Existing staged crawler and frontend changes are out of scope and must not be modified.

## File Layout

Each queued run retains the existing files and adds a compact harness surface:

```text
runtime/runs/research/{run_id}/
  record.json
  events.jsonl
  report.json
  harness.json
  harness-events.jsonl
  checkpoints/
    {operator_name}.json
  snapshot.json
  snapshots/
    {generation}/
      artifacts.jsonl
      evidence.jsonl
      claims.jsonl
      claim-evidence.jsonl
      verifications.jsonl
```

JSON documents are written through a temporary sibling followed by `os.replace`. A pipeline snapshot is written into a temporary generation directory, renamed only after every JSONL file is durable, and exposed by atomically replacing `snapshot.json`. Multi-file readers resolve the pointer once through `read_pipeline_snapshot()`, so one read never combines files from different generations. Every harness document includes `schemaVersion: 1`.

## Core Interfaces

`HarnessOperator` defines one independently testable stage:

```python
@dataclass(frozen=True)
class HarnessOperator:
    name: str
    run: Callable[[HarnessContext], Any]
    version: str = "1"
    dependencies: tuple[str, ...] = ()
    dump: Callable[[Any], Any] = identity
    load: Callable[[Any], Any] | None = None
    resumable: bool = False
```

`ResearchHarness` validates the operator graph, executes ready operators in deterministic declaration order, records lifecycle transitions, and returns a mapping of stage outputs. The first executor is sequential. The interface must not prevent a future concurrent executor.

An operator loader is a pure deserializer. It must not perform network, provider, filesystem mutation, or LLM work; replay guarantees apply to `operator.run`, while loader purity remains part of the operator contract.

`FileHarnessStore` owns all filesystem operations. The engine never constructs paths directly.

## Operator Lifecycle

Operator states are:

```text
queued -> running -> completed
                  -> skipped
                  -> blocked
                  -> failed
completed -> resumed
```

- `completed` writes a checkpoint before the manifest is updated.
- `resumed` loads a completed checkpoint only when `resumable=True`, a loader is present, and the operator version plus input hash still match.
- `failed` records the exception type and bounded message, then stops dependent execution.
- `blocked` represents a policy decision, not an exception caused by broken code.
- `skipped` represents an intentional no-op with an explicit reason.

## Pipeline Integration

The current Coordinator remains the owner of research behavior. The first integration wraps the shared post-acquisition call as a harness-managed operator for queued runs and persists its complete domain result.

This keeps the change surgical while establishing the execution and persistence contracts. Later iterations may split coverage, evidence preparation, synthesis, and grounding into separate operators without changing the harness API.

`RunManager` creates one `FileHarnessStore` rooted at the same path as `RunStore` and passes it into `stream_research()`. Direct legacy endpoints continue to work without a store.

## Persisted Domain Snapshot

After `complete_research_pipeline()` succeeds, the queued-run adapter writes:

- `AcquisitionBatch.raw_artifacts` to `artifacts.jsonl`;
- `EvidenceBatch.evidence_units` to `evidence.jsonl`;
- `ClaimSet.claims` to `claims.jsonl`;
- `ClaimSet.claim_evidence_links` to `claim-evidence.jsonl`;
- grounding results to `verifications.jsonl`.

All five files belong to one immutable generation. The public report remains unchanged. Reopening a report does not require loading these files, but research tooling can inspect the active generation independently through `snapshot.json`.

## Error and Recovery Semantics

- A backend restart continues to cancel the active public run in this first version; the harness checkpoint remains available for audit and future resume work.
- A corrupt checkpoint fails closed with an explicit harness error. It is never silently ignored or overwritten.
- Every checkpoint stores the operator version, deterministic input hash, output hash, committed timestamp, and payload.
- Unknown dependencies and dependency cycles fail before any operator executes.
- Operator names are restricted to ASCII letters, numbers, underscore, and hyphen.
- A failed `ResearchReport` must produce a failed `RunRecord`, not a completed record.

## Verification

Tests must prove:

- dependency ordering and exactly-once execution in a fresh run;
- checkpoint creation and resume without invoking the operator;
- failure and blocked lifecycle recording;
- cycle and unknown-dependency rejection;
- atomic manifest/checkpoint replacement;
- evidence-domain snapshot round trips;
- queued-run store injection;
- unchanged `ResearchReport` fields and existing SSE event names;
- correct `failed`, `partial`, and `completed` run-status propagation.
