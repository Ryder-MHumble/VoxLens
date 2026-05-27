"""OpenCLI-backed search provider."""

from __future__ import annotations

from typing import Any

from voxlens_research.models import ProviderRun, SearchItem
from voxlens_research.utils import extract_first_json, run_command


OPENCLI_PLATFORM = {
    "bilibili": "bilibili",
    "youtube": "youtube",
    "xiaohongshu": "xiaohongshu",
}


def supports(platform: str) -> bool:
    return platform in OPENCLI_PLATFORM


def search(platform: str, query: str, limit: int, timeout: int = 90) -> ProviderRun:
    site = OPENCLI_PLATFORM.get(platform)
    if not site:
        return ProviderRun(provider="opencli", platform=platform, query=query, ok=False, note="opencli has no search command for this platform")

    command = ["opencli", site, "search", query, "--limit", str(limit), "-f", "json"]
    run = ProviderRun(provider="opencli", platform=platform, query=query, command=command)
    try:
        code, stdout, stderr, elapsed = run_command(command, timeout=timeout)
        run.elapsed_sec = elapsed
        run.stderr = stderr.strip()
        run.ok = code == 0
        if code != 0:
            run.note = (stderr or stdout).strip()[:800]
            return run
        payload = extract_first_json(stdout)
        if not isinstance(payload, list):
            run.note = "opencli returned non-list JSON"
            return run
        run.items = [_normalize(platform, item) for item in payload[:limit] if isinstance(item, dict)]
        if not run.items:
            run.note = "no results returned; login/cookie/search quality may be the cause"
        return run
    except Exception as exc:  # noqa: BLE001 - provider failures should not stop the report
        run.ok = False
        run.note = str(exc)
        return run


def _normalize(platform: str, item: dict[str, Any]) -> SearchItem:
    title = str(item.get("title") or item.get("name") or "Untitled")
    url = str(item.get("url") or item.get("link") or "")
    author = str(item.get("author") or item.get("channel") or "")
    metrics: dict[str, Any] = {}

    if platform == "youtube":
        metrics = {"views": item.get("views")}
        return SearchItem(
            platform=platform,
            title=title,
            url=url,
            provider="opencli",
            author=author,
            published=str(item.get("published") or ""),
            duration=str(item.get("duration") or ""),
            metrics=metrics,
            raw=item,
        )

    if platform == "bilibili":
        metrics = {"score": item.get("score")}
    elif platform == "xiaohongshu":
        metrics = {"likes": item.get("likes")}

    return SearchItem(
        platform=platform,
        title=title,
        url=url,
        provider="opencli",
        author=author,
        published=str(item.get("published_at") or item.get("published") or ""),
        metrics=metrics,
        raw=item,
    )
