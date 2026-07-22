from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Iterator
from uuid import uuid4

from fastapi.encoders import jsonable_encoder

from app.agents.coordinator import complete_research_pipeline, create_acquisition_batch, create_research_budget
from app.agents.crawler import iter_crawl_sources
from app.agents.planner import build_research_plan
from app.harness import FileHarnessStore
from app.models import AgentStep, ResearchReport, ResearchRequest, ResearchStage
from app.services.report_builder import build_report


def stream_research(
    request: ResearchRequest,
    run_id: str | None = None,
    harness_store: FileHarnessStore | None = None,
) -> Iterator[str]:
    run_id = run_id or f"run-{uuid4().hex[:12]}"
    query = (request.query or request.need).strip()
    trace: list[AgentStep] = []

    stages = _initial_stages(request.lang)
    yield _event("run_started", {
        "runId": run_id,
        "query": query,
        "need": request.need,
        "lang": request.lang,
        "stages": stages,
        "message": "DeepResearch run started.",
    })

    try:
        yield _stage("plan", "running", 12, "正在拆解问题与生成搜索计划", stages)
        plan, planner_step = build_research_plan(request)
        trace.append(planner_step)
        yield _event("plan", {
            "runId": run_id,
            "plan": plan,
            "step": planner_step,
            "progress": 20,
            "message": planner_step.message,
        })
        yield _stage("plan", "completed", 100, planner_step.message, stages)

        if not request.useLiveProviders:
            report = build_report(
                need=request.need,
                query=query,
                lang=request.lang,
                sources=[],
                run_logs=[],
                is_demo=True,
                generated_at=datetime.now(),
                run_id=run_id,
                research_mode=request.researchMode,
                enable_llm_synthesis=False,
            )
            report.plan = plan
            report.agentTrace = trace
            yield from _stream_report(report, stages)
            return

        yield _stage("search", "running", 25, "正在搜索平台来源并抽样评论/字幕", stages)
        crawler = iter_crawl_sources(request, plan)
        while True:
            try:
                progress = next(crawler)
            except StopIteration as done:
                sources, logs, crawler_step = done.value
                trace.append(crawler_step)
                break

            if progress["type"] == "provider_started":
                yield _event("provider_started", {
                    "runId": run_id,
                    "target": progress["target"],
                    "progress": 30,
                    "message": progress["message"],
                })
            elif progress["type"] == "provider_finished":
                new_sources = progress.get("sources", [])
                yield _event("sources", {
                    "runId": run_id,
                    "target": progress["target"],
                    "log": progress["log"],
                    "sources": new_sources,
                    "progress": min(62, 35 + len(new_sources) * 4),
                    "message": progress["message"],
                })
            elif progress["type"] == "agent_step":
                yield _event("agent_step", {
                    "runId": run_id,
                    "step": progress["step"],
                    "progress": 64,
                    "message": progress["step"].message,
                })

        search_status = "completed" if sources else "failed"
        yield _stage("search", search_status, 100 if sources else 70, f"Collected {len(sources)} sources.", stages)

        yield _stage("evidence", "running", 68, "正在整理证据、计算来源质量和引用优先级", stages)
        budget = create_research_budget(request)
        acquisition_batch = create_acquisition_batch(sources[:budget.max_sources], logs)
        budget.set_sources_collected(len(acquisition_batch.sources))
        pipeline = asyncio.run(complete_research_pipeline(
            request=request,
            plan=plan,
            acquisition_batch=acquisition_batch,
            budget=budget,
            run_id=run_id,
            harness_store=harness_store,
        ))
        if len(pipeline.acquisition_batch.sources) != len(sources):
            yield _event("sources", {
                "runId": run_id,
                "target": "coverage_retry",
                "sources": pipeline.acquisition_batch.sources,
                "progress": 66,
                "message": f"Coverage retry produced {len(pipeline.acquisition_batch.sources)} unique sources in total.",
            })
            yield _stage(
                "search",
                "completed" if pipeline.acquisition_batch.sources else "failed",
                100 if pipeline.acquisition_batch.sources else 70,
                f"Collected {len(pipeline.acquisition_batch.sources)} unique sources after coverage retry.",
                stages,
            )
        trace.extend(pipeline.steps)
        evidence_step = next(
            step for step in pipeline.steps if step.name == "EvidenceStructuringAgent"
        )
        ranked_sources = pipeline.verified_report.report.sources
        for step in pipeline.steps:
            if step.name in {"EvidenceStructuringAgent", "ReportSynthesisAgent", "ClaimGroundingVerifierAgent"}:
                continue
            yield _event("agent_step", {
                "runId": run_id,
                "step": step,
                "progress": 72 if step.name != "ReportSynthesisAgent" else 84,
                "message": step.message,
            })
        yield _event("evidence", {
            "runId": run_id,
            "step": evidence_step,
            "sources": ranked_sources,
            "progress": 78,
            "message": evidence_step.message,
        })
        evidence_status = "completed" if ranked_sources else "failed"
        yield _stage("evidence", evidence_status, 100 if ranked_sources else 60, evidence_step.message, stages)

        yield _stage("synthesis", "running", 84, "正在生成目录、结论和分段报告", stages)
        for step in pipeline.steps:
            if step.name not in {"ReportSynthesisAgent", "ClaimGroundingVerifierAgent"}:
                continue
            yield _event("agent_step", {
                "runId": run_id,
                "step": step,
                "progress": 84,
                "message": step.message,
            })
        report = pipeline.verified_report.report
        report.plan = plan
        report.agentTrace = trace
        yield from _stream_report(report, stages)
    except Exception as exc:  # noqa: BLE001
        yield _stage("synthesis", "failed", 100, str(exc)[:240], stages)
        yield _event("error", {
            "runId": run_id,
            "message": str(exc),
            "progress": 100,
        })


def _stream_report(report: ResearchReport, stages: list[ResearchStage]) -> Iterator[str]:
    empty_sections = []
    report_patch = report.model_copy(deep=True)
    report_patch.sections = empty_sections
    if report_patch.ui:
        report_patch.ui.stages = stages
        report_patch.ui.activeStage = "synthesis"
        report_patch.ui.progress = 88

    yield _event("outline", {
        "runId": report.runId,
        "outline": report.outline,
        "takeaways": report.takeaways,
        "insights": report.insights,
        "coverage": report.coverage,
        "quality": report.quality,
        "warnings": report.warnings,
        "progress": 86,
        "message": "Outline and takeaways are ready.",
    })
    yield _event("report_patch", {
        "runId": report.runId,
        "report": report_patch,
        "progress": 88,
        "message": "Report shell is ready; streaming sections next.",
    })

    for idx, section in enumerate(report.sections, start=1):
        yield _event("section_started", {
            "runId": report.runId,
            "sectionId": section.id,
            "section": section.model_copy(update={"body": "", "bullets": [], "table": [], "quote": None}),
            "progress": min(96, 88 + idx),
            "message": f"Streaming section {idx}/{len(report.sections)}",
        })
        for chunk in _chunks(section.body, 72):
            yield _event("section_delta", {
                "runId": report.runId,
                "sectionId": section.id,
                "delta": chunk,
                "progress": min(97, 88 + idx),
            })
            time.sleep(0.015)
        yield _event("section_complete", {
            "runId": report.runId,
            "section": section,
            "progress": min(98, 88 + idx),
            "message": f"Completed section {idx}/{len(report.sections)}",
        })

    if report.ui:
        report.ui.stages = stages
        report.ui.activeStage = "synthesis"
        report.ui.progress = 100
    for stage in stages:
        if stage.status in {"queued", "running"}:
            stage.status = "completed"
        stage.progress = 100
    yield _stage("synthesis", "completed" if report.status != "failed" else "failed", 100, "报告生成完成", stages)
    yield _event("final_report", {
        "runId": report.runId,
        "report": report,
        "progress": 100,
        "message": "DeepResearch report completed.",
    })


def _initial_stages(lang: str) -> list[ResearchStage]:
    zh = lang == "zh"
    labels = [
        ("plan", "规划问题" if zh else "Plan query"),
        ("search", "搜索来源" if zh else "Search sources"),
        ("evidence", "整理证据" if zh else "Structure evidence"),
        ("synthesis", "生成报告" if zh else "Synthesize report"),
    ]
    return [ResearchStage(id=stage_id, label=label) for stage_id, label in labels]


def _stage(stage_id: str, status: str, progress: int, message: str, stages: list[ResearchStage]) -> str:
    for stage in stages:
        if stage.id != stage_id:
            continue
        stage.status = status  # type: ignore[assignment]
        stage.progress = progress
        stage.message = message
        now = datetime.now().isoformat(timespec="seconds")
        if status == "running" and not stage.startedAt:
            stage.startedAt = now
        if status in {"completed", "partial", "failed", "skipped"}:
            stage.completedAt = now
        break
    return _event("stage", {
        "stageId": stage_id,
        "status": status,
        "progress": _overall_progress(stages),
        "stageProgress": progress,
        "message": message,
        "stages": stages,
    })


def _overall_progress(stages: list[ResearchStage]) -> int:
    if not stages:
        return 0
    return min(100, round(sum(stage.progress for stage in stages) / len(stages)))


def _event(event: str, data: dict[str, Any]) -> str:
    payload = {"type": event, **data}
    return f"event: {event}\ndata: {json.dumps(jsonable_encoder(payload), ensure_ascii=False)}\n\n"


def _chunks(text: str, size: int) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    for part in re_split_keep_punctuation(text):
        if len(current) + len(part) > size and current:
            chunks.append(current)
            current = part
        else:
            current += part
    if current:
        chunks.append(current)
    return chunks


def re_split_keep_punctuation(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    for idx, char in enumerate(text):
        if char in "。！？.!?;；":
            parts.append(text[start : idx + 1])
            start = idx + 1
    if start < len(text):
        parts.append(text[start:])
    return [part for part in parts if part]
