from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from pydantic import TypeAdapter

from app.models import CrawlTarget, ResearchRequest, RunLog, Source
from app.providers.crawler_provider import (
    search_bilibili_crawler,
    search_douyin,
    search_kuaishou,
    search_weibo,
    search_xiaohongshu,
    search_zhihu,
)
from app.providers.opencli_provider import search_bilibili, search_youtube


class LocalDevProvider:
    name = "local"

    def available(self) -> bool:
        return True

    def search(self, request: ResearchRequest, target: CrawlTarget) -> tuple[list[Source], RunLog]:
        if target.platform == "youtube" and target.provider == "opencli":
            return search_youtube(
                target.query,
                target.limit,
                target.detailLimit,
                target.commentsLimit,
                request.includeTranscripts,
                target.videoParallelism,
            )
        if target.platform == "bilibili" and target.provider == "opencli":
            return search_bilibili(
                target.query,
                target.limit,
                target.detailLimit,
                target.commentsLimit,
                request.includeTranscripts,
                target.videoParallelism,
            )
        if target.platform == "bilibili" and target.provider == "crawler":
            return search_bilibili_crawler(
                target.query,
                target.limit,
                target.commentsLimit,
                request.useCrawlerRuntime,
                target.authMode,
                target.videoParallelism,
            )
        if target.platform == "douyin" and target.provider == "crawler":
            return search_douyin(
                target.query,
                target.limit,
                target.commentsLimit,
                request.useCrawlerRuntime,
                target.authMode,
                target.videoParallelism,
            )
        if target.platform == "xiaohongshu" and target.provider == "crawler":
            return search_xiaohongshu(
                target.query,
                target.limit,
                target.commentsLimit,
                request.useCrawlerRuntime,
                target.authMode,
                target.videoParallelism,
            )
        if target.platform == "zhihu" and target.provider == "crawler":
            return search_zhihu(
                target.query,
                target.limit,
                target.commentsLimit,
                request.useCrawlerRuntime,
                target.authMode,
                target.videoParallelism,
            )
        if target.platform == "kuaishou" and target.provider == "crawler":
            return search_kuaishou(
                target.query,
                target.limit,
                target.commentsLimit,
                request.useCrawlerRuntime,
                target.authMode,
                target.videoParallelism,
            )
        if target.platform == "weibo" and target.provider == "crawler":
            return search_weibo(
                target.query,
                target.limit,
                target.commentsLimit,
                request.useCrawlerRuntime,
                target.authMode,
                target.videoParallelism,
            )
        return [], RunLog(provider=target.provider, platform=target.platform, ok=False, count=0, note="unsupported local target")


class OnlineProvider:
    """Production-provider seam.

    The alpha keeps scraping tools local-only. A deployed environment can set
    VOXLENS_ONLINE_PROVIDER_URL to a service that returns normalized Source rows.
    """

    name = "online"

    def __init__(self) -> None:
        self.url = os.getenv("VOXLENS_ONLINE_PROVIDER_URL", "").rstrip("/")
        self.token = os.getenv("VOXLENS_ONLINE_PROVIDER_TOKEN", "")

    def available(self) -> bool:
        return bool(self.url)

    def search(self, request: ResearchRequest, target: CrawlTarget) -> tuple[list[Source], RunLog]:
        if not self.available():
            return [], RunLog(provider="online", platform=target.platform, ok=False, count=0, note="VOXLENS_ONLINE_PROVIDER_URL is not configured")
        payload = json.dumps({
            "request": request.model_dump(mode="json"),
            "target": target.model_dump(mode="json"),
        }).encode("utf-8")
        headers = {"content-type": "application/json"}
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        try:
            req = urllib.request.Request(f"{self.url}/search", data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=180) as response:  # noqa: S310 - user-configured provider endpoint
                body = json.loads(response.read().decode("utf-8"))
            rows = body.get("sources", body.get("items", [])) if isinstance(body, dict) else []
            sources = TypeAdapter(list[Source]).validate_python(rows)
            note = str(body.get("note", ""))[:240] if isinstance(body, dict) else ""
            return sources, RunLog(provider="online", platform=target.platform, ok=True, count=len(sources), note=note)
        except Exception as exc:  # noqa: BLE001
            return [], RunLog(provider="online", platform=target.platform, ok=False, count=0, note=str(exc)[:240])


def run_provider_target(request: ResearchRequest, target: CrawlTarget) -> tuple[list[Source], RunLog]:
    local = LocalDevProvider()
    online = OnlineProvider()
    if request.providerMode == "online":
        return online.search(request, target)
    if request.providerMode == "hybrid" and online.available():
        sources, log = online.search(request, target)
        if sources:
            return sources, log
        local_sources, local_log = local.search(request, target)
        local_log.note = f"online fallback: {log.note}; local: {local_log.note}"[:260]
        return local_sources, local_log
    return local.search(request, target)


def provider_capabilities() -> dict[str, Any]:
    online = OnlineProvider()
    return {
        "modes": ["local", "online", "hybrid"],
        "defaultMode": "local",
        "localDevProviders": ["opencli", "crawler", "yt-dlp"],
        "onlineProvider": {
            "available": online.available(),
            "urlConfigured": bool(online.url),
            "contract": "POST {VOXLENS_ONLINE_PROVIDER_URL}/search with normalized ResearchRequest and CrawlTarget; response { sources: Source[], note?: string }.",
        },
    }
