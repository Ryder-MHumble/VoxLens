from __future__ import annotations

import re
import time

from app.models import AgentStep, CrawlTarget, ResearchPlan, ResearchRequest


def build_research_plan(request: ResearchRequest) -> tuple[ResearchPlan, AgentStep]:
    started = time.perf_counter()
    query = (request.query or request.need).strip()
    expanded = _expand_query(query, request.lang)
    targets: list[CrawlTarget] = []

    for platform in request.platforms:
        primary = _primary_provider(platform, request.useCrawlerRuntime)
        targets.append(CrawlTarget(
            platform=platform,
            provider=primary,
            query=_platform_query(platform, expanded),
            limit=request.limitPerPlatform,
            commentsLimit=request.commentsPerVideo,
            detailLimit=request.detailVideosPerPlatform,
            videoParallelism=request.maxParallelVideos,
            authMode=request.authMode,
            role="primary",
        ))
        if platform == "bilibili" and request.useCrawlerRuntime:
            targets.append(CrawlTarget(
                platform=platform,
                provider="opencli" if primary == "crawler" else "crawler",
                query=_platform_query(platform, expanded),
                limit=request.limitPerPlatform,
                commentsLimit=request.commentsPerVideo,
                detailLimit=request.detailVideosPerPlatform,
                videoParallelism=request.maxParallelVideos,
                authMode=request.authMode,
                role="fallback",
            ))

    plan = ResearchPlan(
        canonicalQuery=query,
        expandedQueries=expanded,
        platforms=request.platforms,
        targets=targets,
        retrievalDepth="deep" if request.limitPerPlatform >= 10 or request.commentsPerVideo >= 10 else "standard",
        notes=[
            "The alpha searches Bilibili, Douyin, YouTube, Xiaohongshu, Zhihu, Kuaishou and Weibo by default; Baidu/Tieba is intentionally excluded.",
            "VoxLens crawler runtime is primary for Chinese social platforms and uses cookie env vars or existing-browser/CDP login state.",
            "OpenCLI is kept as a local development fallback for YouTube and Bilibili metadata enrichment.",
            "providerMode separates local/dev providers from production online provider adapters.",
            "The frontend consumes progress events for planning, provider runs, source batches, evidence scoring and report streaming.",
        ],
    )
    step = AgentStep(
        name="QueryPlannerAgent",
        role="Turns a user need into platform-specific crawl targets.",
        status="ok",
        message=f"Planned {len(targets)} crawl targets for {len(request.platforms)} platforms.",
        elapsedSec=round(time.perf_counter() - started, 3),
        metrics={"expandedQueries": len(expanded), "targets": len(targets)},
    )
    return plan, step


def _primary_provider(platform: str, use_crawler_runtime: bool) -> str:
    if use_crawler_runtime and platform in {"bilibili", "douyin", "xiaohongshu", "zhihu", "kuaishou", "weibo"}:
        return "crawler"
    return "opencli"


def _platform_query(platform: str, expanded: list[str]) -> str:
    if platform == "youtube" and expanded:
        return expanded[-1]
    return expanded[0]


def _expand_query(query: str, lang: str) -> list[str]:
    clean = re.sub(r"\s+", " ", query).strip()
    values = [clean]
    if lang == "zh":
        values.extend([
            f"{clean} 真实体验 评论",
            f"{clean} 评测 对比 优缺点",
        ])
        if not re.search(r"[A-Za-z]", clean):
            values.append(f"{clean} review comparison long term")
    else:
        values.extend([
            f"{clean} review comparison",
            f"{clean} long term experience comments",
        ])
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped[:4]
