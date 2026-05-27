from __future__ import annotations

import os
import sys
from pathlib import Path


def _int_env(name: str, fallback: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(fallback))))
    except ValueError:
        return fallback


def _float_env(name: str, fallback: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(fallback))))
    except ValueError:
        return fallback


def main() -> None:
    # The script is launched with cwd=packages/crawler, so make its modules importable.
    sys.path.insert(0, str(Path.cwd()))

    import config  # type: ignore[import-not-found]
    from main import async_cleanup, main as crawler_main  # type: ignore[import-not-found]
    from tools.app_runner import run  # type: ignore[import-not-found]

    config.CRAWLER_MAX_NOTES_COUNT = _int_env("VOXLENS_MC_MAX_NOTES", config.CRAWLER_MAX_NOTES_COUNT)
    config.CRAWLER_MAX_SLEEP_SEC = _float_env("VOXLENS_MC_SLEEP_SEC", config.CRAWLER_MAX_SLEEP_SEC)
    run(crawler_main, async_cleanup, cleanup_timeout_seconds=15.0)


if __name__ == "__main__":
    main()
