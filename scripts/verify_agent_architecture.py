#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.agents.artifacts import AcquisitionBatch, PlanSpec  # noqa: E402
from app.agents.budget import ResearchBudget, StopPolicy  # noqa: E402
from app.agents.coordinator import (  # noqa: E402
    complete_research_pipeline,
    create_acquisition_batch,
    create_plan_spec,
    prepare_evidence_batch,
)
from app.agents.coverage_gate import CoverageGate  # noqa: E402
from app.agents.grounding_verifier import ClaimGroundingVerifier  # noqa: E402
from app.agents.llm_orchestrator import LLMCallSpec, LLMOrchestrator  # noqa: E402
from app.agents.planner import build_research_plan  # noqa: E402
from app.models import Claim, ClaimEvidence, EvidenceUnit, ResearchReport, ResearchRequest, RunLog, Source  # noqa: E402


def verify_artifact_immutability() -> None:
    """Verify frozen fields, read-only mappings, and source snapshot isolation."""

    plan = _plan_spec()
    try:
        plan.query = "mutated"  # type: ignore[misc]
        raise AssertionError("PlanSpec accepted field mutation")
    except FrozenInstanceError:
        pass
    try:
        plan.platform_queries["weibo"] = "mutated"  # type: ignore[index]
        raise AssertionError("PlanSpec mapping accepted mutation")
    except TypeError:
        pass

    source = _source(1, "bilibili", "Phone A battery is stable", "Battery tests are stable.")
    batch = create_acquisition_batch([source], [_log("bilibili", 1)])
    source.title = "mutated after freeze"
    assert batch.sources[0].title == "Phone A battery is stable"
    serialized_source = batch.sources[0].model_dump()
    assert {"id", "platform", "sourceType", "title", "summary", "metrics", "comments"}.issubset(serialized_source)
    assert {"fullTranscript", "transcriptText", "transcriptSegments"}.isdisjoint(serialized_source)
    assert set(ResearchReport.model_fields) == {
        "runId", "productName", "slogan", "title", "query", "need", "lang", "status", "confidence",
        "generatedAt", "totalVideos", "totalComments", "platforms", "outline", "takeaways", "insights",
        "coverage", "quality", "sections", "sources", "warnings", "methodology", "ui", "runLogs", "plan",
        "agentTrace", "isDemoFallback",
    }
    try:
        batch.sources = ()  # type: ignore[misc]
        raise AssertionError("AcquisitionBatch accepted field mutation")
    except FrozenInstanceError:
        pass


def verify_budget_and_stop_policy() -> None:
    """Verify search continuation, exhaustion, and platform retry decisions."""

    policy = StopPolicy()
    thin_batch = create_acquisition_batch(
        [_source(1, "bilibili", "Phone A review", "stable battery")],
        [_log("bilibili", 1)],
    )
    budget = ResearchBudget(min_sources_for_synthesis=3, min_platforms_for_synthesis=2)
    assert policy.should_continue_search(thin_batch, budget)

    enough_sources = [
        _source(1, "bilibili", "Phone A review", "stable battery", "Strong"),
        _source(2, "youtube", "Phone A long-term review", "stable battery", "Moderate"),
        _source(3, "youtube", "Phone A camera test", "clear video", "Strong"),
    ]
    enough_batch = create_acquisition_batch(
        enough_sources,
        [_log("bilibili", 1), _log("youtube", 2)],
    )
    assert not policy.should_continue_search(enough_batch, budget)
    assert not policy.should_retry_platform("youtube", list(enough_batch.collection_logs))
    assert policy.should_retry_platform("weibo", list(enough_batch.collection_logs))

    exhausted = ResearchBudget(max_sources=1, min_sources_for_synthesis=3)
    assert not policy.should_continue_search(thin_batch, exhausted)


def verify_coverage_gate() -> None:
    """Verify the gate blocks severe gaps and releases covered acquisition."""

    gate = CoverageGate()
    plan = _plan_spec()
    budget = ResearchBudget(min_sources_for_synthesis=2, min_platforms_for_synthesis=2)
    blocked_batch = create_acquisition_batch(
        [_source(1, "bilibili", "Phone A review", "Battery is stable")],
        [_log("bilibili", 1)],
    )
    blocked_report = gate.evaluate(blocked_batch, plan)
    assert gate.should_block_synthesis(blocked_report, budget)
    assert "platform:youtube" in gate.identify_gaps(blocked_report, plan)

    covered_batch = _covered_batch()
    covered_report = gate.evaluate(covered_batch, plan)
    assert not gate.should_block_synthesis(covered_report, budget)
    assert covered_report.counterevidence_found
    assert covered_report.is_sufficient


def verify_grounding_rules() -> None:
    """Verify deterministic support, contradiction, and insufficient results."""

    units = [
        EvidenceUnit(
            id="evidence-support",
            text="Phone A battery life is stable in long-term testing.",
            modality="text",
            source_id=1,
            artifact_id="artifact-1",
        ),
        EvidenceUnit(
            id="evidence-contradict",
            text="Phone A battery life is not stable under heavy use.",
            modality="text",
            source_id=2,
            artifact_id="artifact-2",
        ),
    ]
    claims = [
        Claim(id="support", claim_text="Phone A battery life is stable", claim_type="finding"),
        Claim(id="contradict", claim_text="Phone A battery life is stable", claim_type="finding"),
        Claim(id="insufficient", claim_text="Phone A has satellite connectivity", claim_type="finding"),
    ]
    links = [
        ClaimEvidence(
            claim_id="support",
            evidence_unit_id="evidence-support",
            relation="support",
            relevance_score=1.0,
        ),
        ClaimEvidence(
            claim_id="contradict",
            evidence_unit_id="evidence-contradict",
            relation="contradict",
            relevance_score=1.0,
        ),
    ]
    results = ClaimGroundingVerifier().verify_claims(claims, units, links)
    assert [result.relation for result in results] == ["support", "contradict", "insufficient"]
    assert results[-1].needs_human_review


def verify_llm_orchestrator() -> None:
    """Verify retry limits, shared call budget, token tracking, and fallback."""

    attempts = 0

    async def failing_provider(spec: LLMCallSpec, inputs: dict[str, object]) -> object:
        nonlocal attempts
        attempts += 1
        raise TimeoutError(f"mock timeout for {spec.name}: {bool(inputs)}")

    budget = ResearchBudget(max_llm_calls=2, max_llm_tokens=100)
    orchestrator = LLMOrchestrator(budget, failing_provider)
    result = asyncio.run(orchestrator.execute(
        LLMCallSpec(name="semantic_extraction", max_tokens=40, max_retries=2, timeout_seconds=1),
        {"query": "Phone A"},
        lambda _: "deterministic-fallback",
    ))
    assert result == "deterministic-fallback"
    assert attempts == 2
    assert orchestrator.remaining_budget()["llm_calls"] == 0

    second = asyncio.run(orchestrator.execute(
        LLMCallSpec(name="synthesis", max_tokens=40),
        {},
        lambda: "budget-fallback",
    ))
    assert second == "budget-fallback"
    assert attempts == 2

    async def successful_provider(spec: LLMCallSpec, inputs: dict[str, object]) -> object:
        return {"name": spec.name, "inputs": inputs, "usage": {"total_tokens": 25}}

    success_budget = ResearchBudget(max_llm_calls=2, max_llm_tokens=100)
    success_orchestrator = LLMOrchestrator(success_budget, successful_provider)
    success = asyncio.run(success_orchestrator.execute(
        LLMCallSpec(name="synthesis", max_tokens=40),
        {"claims": 2},
        lambda: {},
    ))
    assert success["usage"]["total_tokens"] == 25
    assert success_orchestrator.remaining_budget() == {"llm_calls": 1, "llm_tokens": 75}


def verify_complete_flow() -> None:
    """Verify the shared post-acquisition flow with mock data and no provider execution."""

    request = ResearchRequest(
        need="Compare Phone A battery experience and risks",
        query="Phone A battery review comparison",
        platforms=["bilibili", "youtube"],
        useLiveProviders=True,
        lang="en",
    )
    legacy_plan, _ = build_research_plan(request)
    acquisition = _covered_batch()
    budget = ResearchBudget()
    with patch.dict("os.environ", {"VOXLENS_ENABLE_LLM": "false"}, clear=False):
        pipeline = asyncio.run(complete_research_pipeline(
            request=request,
            plan=legacy_plan,
            acquisition_batch=acquisition,
            budget=budget,
            run_id="mock-run",
        ))
    verified = pipeline.verified_report
    assert verified.report.runId == "mock-run"
    assert verified.coverage_gate_passed
    assert verified.verification_results
    assert pipeline.claim_set.claims
    assert {claim.claim_text for claim in pipeline.claim_set.claims}.issubset({
        item.text for item in verified.report.takeaways
    } | {item.summary for item in verified.report.insights})
    step_names = {step.name for step in pipeline.steps}
    assert {"CoverageGateAgent", "EvidenceStructuringAgent", "ReportSynthesisAgent", "ClaimGroundingVerifierAgent"}.issubset(step_names)


def _covered_batch() -> AcquisitionBatch:
    """Return a two-platform batch with positive and counterevidence sources."""

    return create_acquisition_batch(
        [
            _source(
                1,
                "bilibili",
                "Phone A battery review",
                "Phone A battery life is stable in daily use.",
                "Strong",
            ),
            _source(
                2,
                "youtube",
                "Phone A long-term comparison",
                "Phone A battery has a downside and is not stable under heavy use.",
                "Moderate",
            ),
        ],
        [_log("bilibili", 1), _log("youtube", 1)],
    )


def _plan_spec() -> PlanSpec:
    """Return a compact immutable plan used by unit-style checks."""

    return PlanSpec(
        query="Phone A battery review",
        entities=("Phone A",),
        comparison_targets=(),
        time_range="",
        evidence_intents=("review",),
        platform_queries={
            "bilibili": "Phone A battery review",
            "youtube": "Phone A battery long term review",
        },
    )


def _source(
    source_id: int,
    platform: str,
    title: str,
    summary: str,
    quality_label: str = "Weak",
) -> Source:
    """Build one Source mock with the existing API model."""

    return Source(
        id=source_id,
        platform=platform,
        title=title,
        summary=summary,
        url=f"https://example.test/{platform}/{source_id}",
        provider="mock",
        metrics={"evidence_quality_label": quality_label},
        quality={"label": quality_label},
        collectedAt="2026-07-17T12:00:00",
    )


def _log(platform: str, count: int) -> RunLog:
    """Build one successful collection log mock."""

    return RunLog(provider="mock", platform=platform, ok=True, count=count, query="mock query")


def main() -> None:
    """Run all architecture checks without network, crawler, browser, or media access."""

    checks = [
        verify_artifact_immutability,
        verify_budget_and_stop_policy,
        verify_coverage_gate,
        verify_grounding_rules,
        verify_llm_orchestrator,
        verify_complete_flow,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    print("All VoxLens agent architecture checks passed.")


if __name__ == "__main__":
    main()
