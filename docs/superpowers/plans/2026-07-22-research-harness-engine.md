# Research Harness Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a file-backed, resumable research harness to queued VoxLens runs while preserving the current API and avoiding new infrastructure dependencies.

**Architecture:** A small `app.harness` package provides typed operators, deterministic graph execution, lifecycle records, and filesystem checkpoints. The queued-run adapter executes the existing post-acquisition pipeline through the harness and persists the resulting evidence-domain objects beside the existing run files.

**Tech Stack:** Python 3.11, standard library, Pydantic 2, `unittest`, existing FastAPI runtime.

## Global Constraints

- Do not add a database, queue service, graph store, object store, or third-party dependency.
- Do not change `ResearchReport` fields or public SSE event names.
- Do not modify the 16 staged crawler, browser-runtime, frontend, or crawler test files.
- Keep the first executor sequential and deterministic.
- Store all harness state under the existing per-run directory.
- Write tests before production code and observe each new test fail for the expected reason.
- Do not create commits or alter the user's existing staged set in this shared checkout.

---

### Task 1: File Harness Store

**Files:**
- Create: `apps/api/app/harness/__init__.py`
- Create: `apps/api/app/harness/models.py`
- Create: `apps/api/app/harness/store.py`
- Create: `apps/api/tests/test_research_harness.py`

**Interfaces:**
- Produces: `HarnessManifest`, `OperatorRecord`, `FileHarnessStore`.
- `FileHarnessStore(root: Path)` treats `root` as the existing research-runs directory.

- [x] **Step 1: Write failing store tests**

```python
def test_store_writes_manifest_checkpoint_and_events_atomically(self):
    store = FileHarnessStore(self.root)
    store.initialize("run-1", {"query": "battery review"})
    store.write_checkpoint("run-1", "evidence", {"count": 2})
    store.append_event("run-1", {"type": "operator_completed", "operator": "evidence"})
    self.assertEqual(store.read_checkpoint("run-1", "evidence"), {"count": 2})
    self.assertEqual(list(store.iter_events("run-1"))[-1]["operator"], "evidence")
```

- [x] **Step 2: Verify the tests fail because `app.harness` does not exist**

Run: `PYTHONPATH=apps/api apps/api/.venv/bin/python -m unittest apps.api.tests.test_research_harness -v`

- [x] **Step 3: Implement manifest models and atomic file operations**

Use `os.replace()` through a unique temporary sibling, validate operator names, and include `schemaVersion: 1`, operator version, input hash, output hash, and committed timestamp in persisted checkpoints.

- [x] **Step 4: Run the focused tests and confirm they pass**

Run: `PYTHONPATH=apps/api apps/api/.venv/bin/python -m unittest apps.api.tests.test_research_harness -v`

### Task 2: Deterministic Operator Engine

**Files:**
- Create: `apps/api/app/harness/engine.py`
- Modify: `apps/api/app/harness/models.py`
- Modify: `apps/api/tests/test_research_harness.py`

**Interfaces:**
- Produces: `HarnessOperator`, `HarnessContext`, `ResearchHarness`, `HarnessExecutionError`, `OperatorBlocked`, `OperatorSkipped`.
- `await ResearchHarness(store, run_id).run(operators, initial_values, mode="resume")` returns `dict[str, Any]`.

- [x] **Step 1: Add failing tests for dependency ordering, resume, failure, blocked state, cycles, and unknown dependencies**

```python
async def test_resume_loads_checkpoint_without_invoking_operator(self):
    calls = 0
    operator = HarnessOperator(
        name="plan",
        run=run_once,
        dump=lambda value: value,
        load=lambda payload: payload,
        resumable=True,
    )
    await ResearchHarness(store, "run-1").run([operator])
    outputs = await ResearchHarness(store, "run-1").run([operator], mode="resume")
    self.assertEqual(outputs["plan"], {"query": "battery"})
    self.assertEqual(calls, 1)
```

- [x] **Step 2: Run the tests and observe missing engine symbols**

- [x] **Step 3: Implement graph validation and sequential execution**

Use stable declaration order for ready operators. Resume only when version and input hash match. Fail closed on corrupt checkpoint data. Write the checkpoint before recording the completed transition. Bound stored exception messages to 500 characters.

- [x] **Step 4: Run focused tests until green**

### Task 3: Evidence-Domain Snapshot Persistence

**Files:**
- Modify: `apps/api/app/harness/store.py`
- Modify: `apps/api/tests/test_research_harness.py`

**Interfaces:**
- Produces: `write_pipeline_snapshot(run_id: str, result: PipelineResult) -> None`.
- Produces: `read_jsonl(run_id: str, filename: str) -> list[dict[str, Any]]` for tests and offline tools.
- Produces: `read_pipeline_snapshot(run_id: str) -> dict[str, Any] | None` for generation-consistent multi-file reads.

- [x] **Step 1: Add a failing round-trip test using real Artifact, EvidenceUnit, Claim, ClaimEvidence, and ClaimVerification models**
- [x] **Step 2: Verify the expected missing-method failure**
- [x] **Step 3: Implement atomic JSONL replacement using Pydantic/dataclass serialization**
- [x] **Step 4: Verify all five files contain schema-versioned records and round-trip data**

### Task 4: Queued-Run Harness Integration

**Files:**
- Modify: `apps/api/app/services/research_stream.py`
- Modify: `apps/api/app/services/run_queue.py`
- Modify: `apps/api/app/agents/coordinator.py`
- Modify: `apps/api/tests/test_research_harness.py`
- Modify: `apps/api/tests/test_run_manager_lifecycle.py`

**Interfaces:**
- `stream_research(request, run_id=None, harness_store=None)` remains backward compatible.
- `complete_research_pipeline(..., harness_store=None)` remains backward compatible.
- Queued runs pass a store rooted at `RunStore.root`; direct endpoints pass `None`.

- [x] **Step 1: Add failing tests proving store injection and persisted pipeline snapshots**
- [x] **Step 2: Verify current queued runs create no harness files**
- [x] **Step 3: Wrap the shared post-acquisition execution in a non-resumable `research_pipeline` operator**
- [x] **Step 4: Persist the complete PipelineResult before yielding the final report**
- [x] **Step 5: Run harness, lifecycle, architecture, and evidence tests**

### Task 5: Status Correctness and Documentation

**Files:**
- Modify: `apps/api/app/services/run_store.py`
- Modify: `apps/api/tests/test_run_manager_lifecycle.py`
- Modify: `docs/agent-architecture.md`
- Modify: `docs/runtime/backend-agent-architecture.md`

**Interfaces:**
- A final report with status `failed` writes `RunRecord.status = "failed"`.
- `partial` and `completed` retain their exact meanings.

- [x] **Step 1: Add a failing regression test for failed-report status propagation**
- [x] **Step 2: Confirm it currently records `completed`**
- [x] **Step 3: Implement the explicit report-to-run status mapping**
- [x] **Step 4: Document the file layout, replay boundary, and single-writer constraint**
- [x] **Step 5: Run full backend verification and `git diff --check`**

Run:

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m unittest discover -s apps/api/tests -p 'test_*.py' -v
PYTHONPATH=apps/api apps/api/.venv/bin/python scripts/verify_agent_architecture.py
PYTHONPATH=apps/api apps/api/.venv/bin/python scripts/verify_evidence_model.py
git diff --check
```
