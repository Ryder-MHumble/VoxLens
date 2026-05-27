from __future__ import annotations

import time
from datetime import datetime
from uuid import uuid4

from app.agents.crawler import crawl_sources
from app.agents.evidence import prepare_evidence
from app.agents.planner import build_research_plan
from app.models import AgentStep, ResearchReport, ResearchRequest
from app.services.report_builder import build_report


def run_agentic_research(request: ResearchRequest) -> ResearchReport:
    trace: list[AgentStep] = []
    query = request.query or request.need
    run_id = f"run-{uuid4().hex[:12]}"

    plan, planner_step = build_research_plan(request)
    trace.append(planner_step)

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
        )
        trace.append(AgentStep(
            name="SocialCrawlerAgent",
            role="Live provider execution",
            status="skipped",
            message="Live providers disabled; returned a query-specific planning report without factual claims.",
        ))
        report.agentTrace = trace
        report.isDemoFallback = True
        report.plan = plan
        return report

    sources, logs, crawler_step = crawl_sources(request, plan)
    trace.append(crawler_step)

    ranked_sources, evidence_step = prepare_evidence(sources)
    trace.append(evidence_step)

    min_sources = request.minLiveSources or 1
    if len(ranked_sources) < min_sources:
        trace.append(AgentStep(
            name="FallbackGuardAgent",
            role="Prevents canned demo data from replacing the user's query; marks the report as evidence-limited instead.",
            status="partial",
            message=f"Only {len(ranked_sources)} live sources collected; requested at least {min_sources}. Building an evidence-limited report with real run logs.",
            metrics={"liveSources": len(ranked_sources), "minSources": min_sources},
        ))

    started = time.perf_counter()
    report = build_report(
        need=request.need,
        query=query,
        lang=request.lang,
        sources=ranked_sources,
        run_logs=logs,
        generated_at=datetime.now(),
        run_id=run_id,
    )
    trace.append(AgentStep(
        name="ReportSynthesisAgent",
        role="Builds the structured, citation-ready DeepResearch report JSON.",
        status="ok",
        message="Generated report sections, takeaways, comparison table and source citations.",
        elapsedSec=round(time.perf_counter() - started, 3),
        metrics={"sections": len(report.sections), "takeaways": len(report.takeaways)},
    ))
    report.plan = plan
    report.agentTrace = trace
    return report
