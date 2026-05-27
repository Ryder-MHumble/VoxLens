"""Search orchestration."""

from __future__ import annotations

from pathlib import Path

from social_deep_research.models import ProviderRun
from social_deep_research.providers import mediacrawler_provider, opencli_provider


def run_search(
    query: str,
    platforms: list[str],
    limit: int,
    provider_mode: str,
    fallback_mediacrawler: bool,
    media_crawler_dir: Path | None = None,
    save_root: Path | None = None,
    timeout: int = 90,
) -> list[ProviderRun]:
    runs: list[ProviderRun] = []
    for platform in platforms:
        platform = platform.strip().lower()
        if not platform:
            continue

        if provider_mode == "mediacrawler":
            runs.append(mediacrawler_provider.search(platform, query, limit, media_crawler_dir=media_crawler_dir, save_root=save_root, timeout=max(timeout, 180)))
            continue

        if provider_mode == "opencli":
            runs.append(opencli_provider.search(platform, query, limit, timeout=timeout))
            continue

        # Hybrid: use lighter OpenCLI where available, fall back to MediaCrawler when requested.
        if opencli_provider.supports(platform):
            run = opencli_provider.search(platform, query, limit, timeout=timeout)
            runs.append(run)
            if run.items or not fallback_mediacrawler or not mediacrawler_provider.supports(platform):
                continue
            runs.append(mediacrawler_provider.search(platform, query, limit, media_crawler_dir=media_crawler_dir, save_root=save_root, timeout=max(timeout, 180)))
        elif mediacrawler_provider.supports(platform):
            runs.append(mediacrawler_provider.search(platform, query, limit, media_crawler_dir=media_crawler_dir, save_root=save_root, timeout=max(timeout, 180)))
        else:
            runs.append(ProviderRun(provider="none", platform=platform, query=query, ok=False, note="unsupported platform"))
    return runs
