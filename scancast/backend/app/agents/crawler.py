from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from typing import Any, Generator

from app.models import AgentStep, ResearchPlan, ResearchRequest, RunLog, Source
from app.providers.registry import run_provider_target
from app.utils import dedupe_sources_key


def crawl_sources(request: ResearchRequest, plan: ResearchPlan) -> tuple[list[Source], list[RunLog], AgentStep]:
    stream = iter_crawl_sources(request, plan)
    while True:
        try:
            next(stream)
        except StopIteration as done:
            return done.value


def iter_crawl_sources(request: ResearchRequest, plan: ResearchPlan) -> Generator[dict[str, Any], None, tuple[list[Source], list[RunLog], AgentStep]]:
    started = time.perf_counter()
    sources: list[Source] = []
    logs: list[RunLog] = []
    seen_platform_counts: dict[str, int] = defaultdict(int)

    primary_targets = [target for target in plan.targets if target.role != "fallback"]
    fallback_targets = [target for target in plan.targets if target.role == "fallback"]
    yield from _run_target_group(request, primary_targets, sources, logs, seen_platform_counts)

    runnable_fallbacks = []
    for target in fallback_targets:
        fallback_threshold = min(target.limit, max(3, target.limit // 2))
        if target.role == "fallback" and seen_platform_counts[target.platform] >= fallback_threshold:
            log = RunLog(provider=target.provider, platform=target.platform, ok=True, count=0, note="skipped because primary provider returned enough sources", query=target.query)
            logs.append(log)
            yield {
                "type": "provider_finished",
                "target": target,
                "log": log,
                "sources": [],
                "message": log.note,
            }
            continue
        runnable_fallbacks.append(target)

    yield from _run_target_group(request, runnable_fallbacks, sources, logs, seen_platform_counts)

    step = AgentStep(
        name="SocialCrawlerAgent",
        role="Runs OpenCLI and MediaCrawler adapters concurrently, then deduplicates source items.",
        status="ok" if sources else "failed",
        message=f"Collected {len(sources)} unique sources from {len(logs)} provider runs.",
        elapsedSec=round(time.perf_counter() - started, 3),
        metrics={
            "sources": len(sources),
            "comments": sum(len(s.comments) for s in sources),
            "providerRuns": len(logs),
            "maxParallelPlatforms": request.maxParallelPlatforms,
            "maxParallelVideos": request.maxParallelVideos,
        },
    )
    yield {"type": "agent_step", "step": step, "sources": sources, "logs": logs}
    return sources, logs, step


def _run_target_group(
    request: ResearchRequest,
    targets: list[Any],
    sources: list[Source],
    logs: list[RunLog],
    seen_platform_counts: dict[str, int],
) -> Generator[dict[str, Any], None, None]:
    if not targets:
        return
    max_workers = max(1, min(request.maxParallelPlatforms, len(targets)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_target = {}
        for target in targets:
            yield {
                "type": "provider_started",
                "target": target,
                "message": f"Searching {target.platform} with {target.provider}",
            }
            future_to_target[executor.submit(run_provider_target, request, target)] = target

        for future in as_completed(future_to_target):
            target = future_to_target[future]
            try:
                batch, log = future.result()
            except Exception as exc:  # noqa: BLE001
                batch = []
                log = RunLog(provider=target.provider, platform=target.platform, ok=False, count=0, note=str(exc)[:240])

            log.query = target.query
            logs.append(log)
            new_sources: list[Source] = []
            for source in batch:
                if _add_source_if_new(source, sources):
                    seen_platform_counts[source.platform] += 1
                    new_sources.append(source)

            yield {
                "type": "provider_finished",
                "target": target,
                "log": log,
                "sources": new_sources,
                "message": f"{target.provider} returned {len(new_sources)} new sources for {target.platform}",
            }

def _add_source_if_new(source: Source, sources: list[Source]) -> bool:
    key = dedupe_sources_key(source.platform, source.url, source.title)
    existing_keys = {dedupe_sources_key(item.platform, item.url, item.title) for item in sources}
    if key in existing_keys:
        return False
    source.id = len(sources) + 1
    sources.append(source)
    return True
