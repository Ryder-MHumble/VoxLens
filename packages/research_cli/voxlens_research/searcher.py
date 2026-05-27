"""Search orchestration."""

from __future__ import annotations

from pathlib import Path

from voxlens_research.models import ProviderRun
from voxlens_research.providers import crawler_provider, opencli_provider


def run_search(
    query: str,
    platforms: list[str],
    limit: int,
    provider_mode: str,
    fallback_crawler: bool,
    crawler_dir: Path | None = None,
    save_root: Path | None = None,
    timeout: int = 90,
) -> list[ProviderRun]:
    runs: list[ProviderRun] = []
    for platform in platforms:
        platform = platform.strip().lower()
        if not platform:
            continue

        if provider_mode == "crawler":
            runs.append(crawler_provider.search(platform, query, limit, crawler_dir=crawler_dir, save_root=save_root, timeout=max(timeout, 180)))
            continue

        if provider_mode == "opencli":
            runs.append(opencli_provider.search(platform, query, limit, timeout=timeout))
            continue

        # Hybrid: use lighter OpenCLI where available, fall back to VoxLens crawler runtime when requested.
        if opencli_provider.supports(platform):
            run = opencli_provider.search(platform, query, limit, timeout=timeout)
            runs.append(run)
            if run.items or not fallback_crawler or not crawler_provider.supports(platform):
                continue
            runs.append(crawler_provider.search(platform, query, limit, crawler_dir=crawler_dir, save_root=save_root, timeout=max(timeout, 180)))
        elif crawler_provider.supports(platform):
            runs.append(crawler_provider.search(platform, query, limit, crawler_dir=crawler_dir, save_root=save_root, timeout=max(timeout, 180)))
        else:
            runs.append(ProviderRun(provider="none", platform=platform, query=query, ok=False, note="unsupported platform"))
    return runs
